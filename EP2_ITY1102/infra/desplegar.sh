#!/usr/bin/env bash
# Despliega TodoBarato AI en AWS Academy. Idempotente: si un recurso ya existe, lo reutiliza.
#   bash EP2_ITY1102/infra/desplegar.sh            # todo
#   ALERTA_EMAIL=correo@x.cl bash ...desplegar.sh  # además suscribe ese correo a las alarmas
# Al terminar las pruebas: bash EP2_ITY1102/infra/destruir.sh  (el ALB y RDS cobran por hora)
source "$(dirname "$0")/comun.sh"
cargar

existe() { [ -n "${1:-}" ] && [ "$1" != None ] && [ "$1" != null ]; }

# ---------------------------------------------------------------- 1. S3 (artefactos, configuración, logs)
log "1/11 Bucket S3 $BUCKET"
if ! $AWS s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  $AWS s3api create-bucket --bucket "$BUCKET" >/dev/null
  $AWS s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  $AWS s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
  $AWS s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
  $AWS s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
    '{"Rules":[{"ID":"logs-30-dias","Status":"Enabled","Filter":{"Prefix":"logs/"},"Expiration":{"Days":30}},{"ID":"versiones-viejas","Status":"Enabled","Filter":{},"NoncurrentVersionExpiration":{"NoncurrentDays":7}}]}'
  $AWS s3api put-bucket-tagging --bucket "$BUCKET" --tagging "TagSet=[{$ETIQUETA}]"
fi

# ---------------------------------------------------------------- 2. Imágenes Docker → S3 (sin ECR en esta cuenta)
# Etapa de build dentro de AWS: se sube solo el código (~350 KB) y una EC2 temporal construye y publica las imágenes.
log "2/11 Imágenes Docker (constructor remoto)"
if [ "${SALTAR_IMAGENES:-0}" != 1 ]; then
  bash "$INFRA/empaquetar_fuente.sh" >/dev/null
  $AWS s3 cp "$SALIDA/fuente.tar.gz" "s3://$BUCKET/fuente/fuente.tar.gz" --only-show-errors
  printf 'NEXT_PUBLIC_SUPABASE_URL=%s\nNEXT_PUBLIC_SUPABASE_ANON_KEY=%s\n' \
    "$(leer_env NEXT_PUBLIC_SUPABASE_URL)" "$(leer_env NEXT_PUBLIC_SUPABASE_ANON_KEY)" |
    $AWS s3 cp - "s3://$BUCKET/fuente/build.env" --sse AES256 --only-show-errors
  $AWS s3 rm "s3://$BUCKET/imagenes/LISTO" --quiet || true
  $AWS s3 rm "s3://$BUCKET/imagenes/ERROR" --quiet || true
  AMI_BUILD=$($AWS ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
  sed "s/__BUCKET__/$BUCKET/" "$INFRA/arranque-constructor.sh" > "$SALIDA/constructor-ud.sh"
  CONSTRUCTOR=$($AWS ec2 run-instances --image-id "$AMI_BUILD" --instance-type t3.medium \
    --iam-instance-profile Name="$PERFIL_EC2" --subnet-id "${SUBREDES[0]}" \
    --instance-initiated-shutdown-behavior terminate --metadata-options HttpTokens=required,HttpEndpoint=enabled \
    --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
    --user-data "file://$SALIDA/constructor-ud.sh" \
    --tag-specifications "ResourceType=instance,Tags=[{$ETIQUETA},{Key=Name,Value=$P-constructor},{Key=Rol,Value=constructor}]" \
    --query 'Instances[0].InstanceId' --output text)
  log "   constructor $CONSTRUCTOR construyendo en paralelo (~6-10 min)…"
fi
esperar_imagenes() {
  [ "${SALTAR_IMAGENES:-0}" = 1 ] && return 0
  for i in $(seq 1 90); do
    if $AWS s3 ls "s3://$BUCKET/imagenes/LISTO" >/dev/null 2>&1; then log "   imágenes publicadas en S3"; break; fi
    if $AWS s3 ls "s3://$BUCKET/imagenes/ERROR" >/dev/null 2>&1; then
      $AWS s3 cp "s3://$BUCKET/imagenes/ERROR" - | tail -30; echo "Falló la construcción de imágenes"; exit 1
    fi
    [ "$i" = 90 ] && { echo "El constructor no terminó en 30 min"; exit 1; }
    sleep 20
  done
}

# ---------------------------------------------------------------- 3. Security groups (mínimo privilegio)
log "3/11 Security groups"
sg() {  # sg <nombre> <descripción>
  local id
  id=$($AWS ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC" Name=group-name,Values="$1" --query 'SecurityGroups[0].GroupId' --output text)
  if ! existe "$id"; then
    id=$($AWS ec2 create-security-group --vpc-id "$VPC" --group-name "$1" --description "$2" \
      --tag-specifications "ResourceType=security-group,Tags=[{$ETIQUETA},{Key=Name,Value=$1}]" --query GroupId --output text)
  fi
  echo "$id"
}
permitir() { $AWS ec2 authorize-security-group-ingress "$@" >/dev/null 2>&1 || true; }
SG_ALB=$(sg "$P-alb" "ALB publico: HTTP 80")
SG_APP=$(sg "$P-app" "EC2 de la app: solo desde el ALB")
SG_DB=$(sg "$P-db" "RDS: solo desde la app")
permitir --group-id "$SG_ALB" --protocol tcp --port 80 --cidr 0.0.0.0/0
permitir --group-id "$SG_APP" --protocol tcp --port 8000 --source-group "$SG_ALB"
permitir --group-id "$SG_APP" --protocol tcp --port 3000 --source-group "$SG_ALB"
permitir --group-id "$SG_DB" --protocol tcp --port 5432 --source-group "$SG_APP"
guardar SG_ALB "$SG_ALB"; guardar SG_APP "$SG_APP"; guardar SG_DB "$SG_DB"

# ---------------------------------------------------------------- 4. RDS PostgreSQL
log "4/11 RDS PostgreSQL ($CLASE_RDS)"
DB_ID="$P-postgres"
if ! existe "${DB_CLAVE:-}"; then DB_CLAVE=$(openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | head -c 28); guardar DB_CLAVE "$DB_CLAVE"; fi
if ! $AWS rds describe-db-instances --db-instance-identifier "$DB_ID" >/dev/null 2>&1; then
  $AWS rds create-db-subnet-group --db-subnet-group-name "$P-db" --db-subnet-group-description "$P" \
    --subnet-ids "${SUBREDES[@]}" --tags "$ETIQUETA" >/dev/null 2>&1 || true
  VERSION_PG=$($AWS rds describe-db-engine-versions --engine postgres --query "DBEngineVersions[?starts_with(EngineVersion,'17.')].EngineVersion | [-1]" --output text)
  # Público SOLO durante la carga inicial de datos (desde la IP de quien despliega); luego se cierra.
  $AWS rds create-db-instance --db-instance-identifier "$DB_ID" --engine postgres --engine-version "$VERSION_PG" \
    --db-instance-class "$CLASE_RDS" --allocated-storage 20 --storage-type gp3 --storage-encrypted \
    --master-username todobarato --master-user-password "$DB_CLAVE" --db-name todobarato \
    --vpc-security-group-ids "$SG_DB" --db-subnet-group-name "$P-db" --publicly-accessible \
    --backup-retention-period 1 --no-multi-az --no-deletion-protection \
    --enable-cloudwatch-logs-exports postgresql --tags "$ETIQUETA" >/dev/null
  log "   esperando a que RDS quede disponible (~5-8 min)…"
fi
$AWS rds wait db-instance-available --db-instance-identifier "$DB_ID"
DB_HOST=$($AWS rds describe-db-instances --db-instance-identifier "$DB_ID" --query 'DBInstances[0].Endpoint.Address' --output text)
guardar DB_HOST "$DB_HOST"
DB_URL="postgresql://todobarato:$DB_CLAVE@$DB_HOST:5432/todobarato?sslmode=require"

# ---------------------------------------------------------------- 5. Datos: Supabase → RDS (una vez)
if [ "${DATOS_CARGADOS:-0}" != 1 ]; then
  log "5/11 Copiando datos de Supabase a RDS"
  MI_IP=$(curl -s https://checkip.amazonaws.com)/32
  permitir --group-id "$SG_DB" --protocol tcp --port 5432 --cidr "$MI_IP"
  printf 'ORIGEN=%s\nDESTINO=%s\n' "$(leer_env DATABASE_URL)" "$DB_URL" > "$SALIDA/migrar.env"; chmod 600 "$SALIDA/migrar.env"
  docker run --rm --env-file "$SALIDA/migrar.env" -v "$SALIDA:/salida" postgres:17 bash -c '
    set -e
    pg_dump "$ORIGEN" --schema=public --no-owner --no-privileges --format=custom -f /salida/supabase.dump
    psql "$DESTINO" -qc "create extension if not exists \"uuid-ossp\"; create extension if not exists pgcrypto;"
    pg_restore -d "$DESTINO" --no-owner --no-privileges /salida/supabase.dump 2> /salida/restore.log || true
    echo "tablas restauradas: $(psql "$DESTINO" -Atc "select count(*) from pg_tables where schemaname='"'"'public'"'"'")"'
  rm -f "$SALIDA/migrar.env"
  aviso "errores de pg_restore (políticas propias de Supabase, se ignoran): $(grep -c 'error:' "$SALIDA/restore.log" || true)"
  $AWS ec2 revoke-security-group-ingress --group-id "$SG_DB" --protocol tcp --port 5432 --cidr "$MI_IP" >/dev/null || true
  guardar DATOS_CARGADOS 1
  # AWS Academy niega rds:ModifyDBInstance: si no se puede quitar el acceso público, el SG ya lo bloquea
  # (solo acepta 5432 desde tb-ep2-app; la regla de la IP de despliegue se acaba de revocar).
  $AWS rds modify-db-instance --db-instance-identifier "$DB_ID" --no-publicly-accessible --apply-immediately >/dev/null 2>&1 \
    || aviso "la cuenta no permite quitar el acceso público de RDS: queda cerrado por el security group"
else
  log "5/11 Datos ya cargados (DATOS_CARGADOS=1)"
fi

# ---------------------------------------------------------------- 6. SNS: alarmas y eventos de ingesta
log "6/11 Temas SNS"
TEMA_ALARMAS=$($AWS sns create-topic --name "$P-alarmas" --tags "$ETIQUETA" --query TopicArn --output text)
TEMA_EVENTOS=$($AWS sns create-topic --name "$P-eventos-ingesta" --tags "$ETIQUETA" --query TopicArn --output text)
guardar TEMA_ALARMAS "$TEMA_ALARMAS"; guardar TEMA_EVENTOS "$TEMA_EVENTOS"
# EventBridge y CloudWatch pueden publicar en los temas.
for t in "$TEMA_ALARMAS" "$TEMA_EVENTOS"; do
  $AWS sns set-topic-attributes --topic-arn "$t" --attribute-name Policy --attribute-value "$(cat <<JSON
{"Version":"2012-10-17","Statement":[
 {"Sid":"Cuenta","Effect":"Allow","Principal":{"AWS":"*"},"Action":["SNS:Publish","SNS:Subscribe","SNS:GetTopicAttributes"],"Resource":"$t","Condition":{"StringEquals":{"AWS:SourceOwner":"$CUENTA"}}},
 {"Sid":"Servicios","Effect":"Allow","Principal":{"Service":["events.amazonaws.com","cloudwatch.amazonaws.com"]},"Action":"SNS:Publish","Resource":"$t"}]}
JSON
)"
done
if [ -n "${ALERTA_EMAIL:-}" ]; then
  $AWS sns subscribe --topic-arn "$TEMA_ALARMAS" --protocol email --notification-endpoint "$ALERTA_EMAIL" >/dev/null
  aviso "revise $ALERTA_EMAIL y confirme la suscripción a las alarmas"
fi

# ---------------------------------------------------------------- 7. Configuración de la app (cifrada en S3)
log "7/11 Configuración de la app"
base_env() {
  cat <<EOF
APP_ENV=production
DATABASE_URL=$DB_URL
SUPABASE_URL=$(leer_env SUPABASE_URL)
SUPABASE_JWT_AUDIENCE=$(leer_env SUPABASE_JWT_AUDIENCE)
LLM_PROVIDER=$(leer_env LLM_PROVIDER)
GEMINI_API_KEY=$(leer_env GEMINI_API_KEY)
GEMINI_MODEL=$(leer_env GEMINI_MODEL)
LLM_TIMEOUT_SECONDS=$(leer_env LLM_TIMEOUT_SECONDS)
AI_MAX_TOOL_CALLS=$(leer_env AI_MAX_TOOL_CALLS)
INGESTION_MAX_CATEGORIES=$(leer_env INGESTION_MAX_CATEGORIES)
INGESTION_MAX_URLS_PER_CATEGORY=$(leer_env INGESTION_MAX_URLS_PER_CATEGORY)
INGESTION_MAX_PRODUCTS=$(leer_env INGESTION_MAX_PRODUCTS)
AGENT_DEMO_ENABLED=false
EOF
}
{ base_env; echo "INGESTION_SCHEDULER_ENABLED=false"; echo "UVICORN_WORKERS=2"; } | $AWS s3 cp - "s3://$BUCKET/config/api.env" --sse AES256 --only-show-errors
{ base_env; echo "INGESTION_SCHEDULER_ENABLED=true"; echo "UVICORN_WORKERS=1"; echo "SNS_TOPIC_ARN_EVENTOS=$TEMA_EVENTOS"; } | $AWS s3 cp - "s3://$BUCKET/config/worker.env" --sse AES256 --only-show-errors

# ---------------------------------------------------------------- 8. Launch templates
log "8/11 Launch templates (esperando las imágenes del constructor)"
esperar_imagenes
AMI=$($AWS ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
plantilla() {  # plantilla <rol> <tipo>
  local nombre="$P-$1" datos ud
  ud=$(sed -e "s/__ROL__/$1/" -e "s/__BUCKET__/$BUCKET/" "$INFRA/arranque-ec2.sh" | base64 -w0)
  datos=$(cat <<JSON
{"ImageId":"$AMI","InstanceType":"$2","IamInstanceProfile":{"Name":"$PERFIL_EC2"},
 "SecurityGroupIds":["$SG_APP"],"UserData":"$ud",
 "MetadataOptions":{"HttpTokens":"required","HttpEndpoint":"enabled"},
 "Monitoring":{"Enabled":true},
 "BlockDeviceMappings":[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3","Encrypted":true,"DeleteOnTermination":true}}],
 "TagSpecifications":[{"ResourceType":"instance","Tags":[{"Key":"Proyecto","Value":"$P"},{"Key":"Name","Value":"$nombre"},{"Key":"Rol","Value":"$1"}]}]}
JSON
)
  if $AWS ec2 describe-launch-templates --launch-template-names "$nombre" >/dev/null 2>&1; then
    $AWS ec2 create-launch-template-version --launch-template-name "$nombre" --launch-template-data "$datos" --query LaunchTemplateVersion.VersionNumber --output text >/dev/null
    $AWS ec2 modify-launch-template --launch-template-name "$nombre" --default-version '$Latest' >/dev/null
  else
    $AWS ec2 create-launch-template --launch-template-name "$nombre" --launch-template-data "$datos" \
      --tag-specifications "ResourceType=launch-template,Tags=[{$ETIQUETA}]" >/dev/null
  fi
}
plantilla api "$TIPO_APP"
plantilla worker "$TIPO_WORKER"

# ---------------------------------------------------------------- 9. ALB + target groups + reglas
log "9/11 Balanceador (ALB)"
tg() {  # tg <nombre> <puerto> <ruta-salud>
  local arn
  arn=$($AWS elbv2 describe-target-groups --names "$1" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)
  if ! existe "$arn"; then
    arn=$($AWS elbv2 create-target-group --name "$1" --protocol HTTP --port "$2" --vpc-id "$VPC" --target-type instance \
      --health-check-path "$3" --health-check-interval-seconds 5 --health-check-timeout-seconds 3 \
      --healthy-threshold-count 2 --unhealthy-threshold-count 2 --matcher HttpCode=200 --tags "$ETIQUETA" \
      --query 'TargetGroups[0].TargetGroupArn' --output text)
    # Drenaje corto y reparto por menos solicitudes pendientes (las llamadas al agente tardan distinto).
    $AWS elbv2 modify-target-group-attributes --target-group-arn "$arn" --attributes \
      Key=deregistration_delay.timeout_seconds,Value=30 Key=load_balancing.algorithm.type,Value=least_outstanding_requests >/dev/null
  fi
  echo "$arn"
}
TG_FRONT=$(tg "$P-front" 3000 /)
TG_API=$(tg "$P-api" 8000 /health)
TG_WORKER=$(tg "$P-worker" 8000 /health)
guardar TG_FRONT "$TG_FRONT"; guardar TG_API "$TG_API"; guardar TG_WORKER "$TG_WORKER"

ALB=$($AWS elbv2 describe-load-balancers --names "$P-alb" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)
if ! existe "$ALB"; then
  ALB=$($AWS elbv2 create-load-balancer --name "$P-alb" --type application --scheme internet-facing \
    --subnets "${SUBREDES[@]}" --security-groups "$SG_ALB" --tags "$ETIQUETA" --query 'LoadBalancers[0].LoadBalancerArn' --output text)
  # El agente puede tardar hasta ~3 min (varias llamadas a Gemini): timeout de inactividad 180 s.
  $AWS elbv2 modify-load-balancer-attributes --load-balancer-arn "$ALB" --attributes \
    Key=idle_timeout.timeout_seconds,Value=180 Key=routing.http.drop_invalid_header_fields.enabled,Value=true >/dev/null
fi
guardar ALB "$ALB"
LISTENER=$($AWS elbv2 describe-listeners --load-balancer-arn "$ALB" --query 'Listeners[0].ListenerArn' --output text 2>/dev/null || true)
if ! existe "$LISTENER"; then
  LISTENER=$($AWS elbv2 create-listener --load-balancer-arn "$ALB" --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_FRONT" --query 'Listeners[0].ListenerArn' --output text)
  # Más específica primero: eventos → worker; API y salud → backend; todo lo demás → frontend.
  $AWS elbv2 create-rule --listener-arn "$LISTENER" --priority 10 \
    --conditions Field=path-pattern,Values='/api/v1/eventos/*' --actions Type=forward,TargetGroupArn="$TG_WORKER" >/dev/null
  $AWS elbv2 create-rule --listener-arn "$LISTENER" --priority 20 \
    --conditions Field=path-pattern,Values='/api/*','/health' --actions Type=forward,TargetGroupArn="$TG_API" >/dev/null
fi
ALB_DNS=$($AWS elbv2 describe-load-balancers --load-balancer-arns "$ALB" --query 'LoadBalancers[0].DNSName' --output text)
ALB_SUFIJO=$($AWS elbv2 describe-load-balancers --load-balancer-arns "$ALB" --query 'LoadBalancers[0].LoadBalancerArn' --output text | sed 's#.*:loadbalancer/##')
guardar ALB_DNS "$ALB_DNS"

# ---------------------------------------------------------------- 10. Auto Scaling Groups (réplicas en 2 zonas)
log "10/11 Auto Scaling (api: 2-4 réplicas en ${ZONAS[*]}; worker: 1)"
SUBREDES_CSV=$(IFS=,; echo "${SUBREDES[*]}")
ACTUALIZAR=()
asg() {  # asg <rol> <min> <max> <deseado> <tg...>
  local nombre="$P-$1" rol=$1 min=$2 max=$3 des=$4; shift 4
  if $AWS autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$nombre" --query 'AutoScalingGroups[0].AutoScalingGroupName' --output text | grep -q "$nombre"; then
    $AWS autoscaling update-auto-scaling-group --auto-scaling-group-name "$nombre" \
      --launch-template "LaunchTemplateName=$nombre,Version=\$Latest" --min-size "$min" --max-size "$max" --desired-capacity "$des"
    # Las réplicas existentes se reemplazan al final con actualizacion_gradual.sh (instance refresh está bloqueado).
    ACTUALIZAR+=("$rol")
  else
    $AWS autoscaling create-auto-scaling-group --auto-scaling-group-name "$nombre" \
      --launch-template "LaunchTemplateName=$nombre,Version=\$Latest" \
      --min-size "$min" --max-size "$max" --desired-capacity "$des" \
      --vpc-zone-identifier "$SUBREDES_CSV" --target-group-arns "$@" \
      --health-check-type ELB --health-check-grace-period 300 --default-instance-warmup 240 \
      --tags "ResourceId=$nombre,ResourceType=auto-scaling-group,Key=Proyecto,Value=$P,PropagateAtLaunch=true" \
             "ResourceId=$nombre,ResourceType=auto-scaling-group,Key=Rol,Value=$rol,PropagateAtLaunch=true"
    $AWS autoscaling enable-metrics-collection --auto-scaling-group-name "$nombre" --granularity 1Minute
  fi
}
asg api 2 4 2 "$TG_FRONT" "$TG_API"
asg worker 1 1 1 "$TG_WORKER"
# Escalado por objetivo: CPU media del grupo en 60 %.
$AWS autoscaling put-scaling-policy --auto-scaling-group-name "$P-api" --policy-name "$P-cpu-60" \
  --policy-type TargetTrackingScaling --target-tracking-configuration \
  '{"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"},"TargetValue":60.0}' >/dev/null

# ---------------------------------------------------------------- 11. Observabilidad + eventos programados
log "11/11 CloudWatch (dashboard + alarmas) y EventBridge"
TG_API_SUF=${TG_API##*:}; TG_FRONT_SUF=${TG_FRONT##*:}
alarma() {  # alarma <nombre> <namespace> <métrica> <estadística> <umbral> <operador> <dimensiones...>
  local n=$1 ns=$2 m=$3 e=$4 u=$5 op=$6; shift 6
  $AWS cloudwatch put-metric-alarm --alarm-name "$P-$n" --namespace "$ns" --metric-name "$m" --statistic "$e" \
    --period 60 --evaluation-periods 3 --datapoints-to-alarm 2 --threshold "$u" --comparison-operator "$op" \
    --treat-missing-data notBreaching --alarm-actions "$TEMA_ALARMAS" --ok-actions "$TEMA_ALARMAS" --dimensions "$@"
}
alarma api-replica-caida AWS/ApplicationELB UnHealthyHostCount Maximum 0 GreaterThanThreshold \
  Name=TargetGroup,Value="$TG_API_SUF" Name=LoadBalancer,Value="$ALB_SUFIJO"
alarma alb-errores-5xx AWS/ApplicationELB HTTPCode_Target_5XX_Count Sum 10 GreaterThanThreshold Name=LoadBalancer,Value="$ALB_SUFIJO"
alarma alb-latencia AWS/ApplicationELB TargetResponseTime Average 5 GreaterThanThreshold Name=LoadBalancer,Value="$ALB_SUFIJO"
alarma rds-cpu AWS/RDS CPUUtilization Average 80 GreaterThanThreshold Name=DBInstanceIdentifier,Value="$DB_ID"
alarma rds-memoria AWS/RDS FreeableMemory Minimum 100000000 LessThanThreshold Name=DBInstanceIdentifier,Value="$DB_ID"

sed -e "s#__ALB__#$ALB_SUFIJO#g" -e "s#__TGAPI__#$TG_API_SUF#g" -e "s#__TGFRONT__#$TG_FRONT_SUF#g" \
    -e "s#__DB__#$DB_ID#g" -e "s#__ASG__#$P-api#g" -e "s#__REGION__#$REGION#g" -e "s#CUENTA#$CUENTA#g" "$INFRA/dashboard.json" > "$SALIDA/dashboard.json"
$AWS cloudwatch put-dashboard --dashboard-name "$P" --dashboard-body "file://$SALIDA/dashboard.json" >/dev/null

# EventBridge → SNS → (HTTP, por el ALB) → worker: ingesta programada cada 6 horas.
$AWS events put-rule --name "$P-ingesta-programada" --schedule-expression 'rate(6 hours)' --state ENABLED \
  --description "Dispara la sincronizacion de tiendas en el worker" --tags "$ETIQUETA" >/dev/null
printf '[{"Id":"sns-eventos","Arn":"%s","Input":"{\\"tipo\\":\\"ingesta_programada\\"}"}]' "$TEMA_EVENTOS" > "$SALIDA/destinos.json"
$AWS events put-targets --rule "$P-ingesta-programada" --targets "file://$SALIDA/destinos.json" >/dev/null
# SNS prueba el endpoint al suscribir: recién creado el worker aún no responde, y estado.sh reintenta.
$AWS sns subscribe --topic-arn "$TEMA_EVENTOS" --protocol http \
  --notification-endpoint "http://$ALB_DNS/api/v1/eventos/sns" >/dev/null 2>&1 \
  || aviso "el worker aún no responde: la suscripción SNS se completa con estado.sh en ~5 min"

bash "$INFRA/https_cloudfront.sh"
cargar
# Redespliegue: reemplazo gradual de las réplicas con la versión nueva (sin caída).
for rol in "${ACTUALIZAR[@]}"; do bash "$INFRA/actualizacion_gradual.sh" "$rol"; done
log "Listo. Las instancias tardan ~4 min en arrancar y pasar el health check."
echo "  App (HTTPS): https://${CF_DOMINIO:-<propagando>}/"
echo
echo "  App:        http://$ALB_DNS/"
echo "  Salud:      http://$ALB_DNS/health"
echo "  Dashboard:  https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#dashboards/dashboard/$P"
echo "  Estado:     bash EP2_ITY1102/infra/estado.sh"
echo "  Al terminar: bash EP2_ITY1102/infra/destruir.sh"
