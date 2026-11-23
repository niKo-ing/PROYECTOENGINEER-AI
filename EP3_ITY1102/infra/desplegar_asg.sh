#!/usr/bin/env bash
# Despliegue ESCALABLE en AWS Academy: ALB + Auto Scaling Group (2-4 réplicas t3.medium, CPU objetivo 50 %) + RDS PostgreSQL
# + instancia de servicios (RabbitMQ + worker) + CloudFront (HTTPS). Tarda ~15 min (RDS ~8 y CloudFront ~8 en paralelo).
# Requisitos: credenciales del lab en el entorno. Cuesta ~USD 0,15/h. No se destruye al terminar (ver docs/entrega/DEPLOY_DEFENSA.md).
set -euo pipefail
cd "$(dirname "$0")/.."                      # EP3_ITY1102
RAIZ=$(cd .. && pwd); INFRA=$PWD/infra; SALIDA=$INFRA/.salida; mkdir -p "$SALIDA"
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1} AWS_PAGER=""
P=tb-ep3; ETIQUETA="Key=Proyecto,Value=$P"
log() { echo "[$(date +%H:%M:%S)] $*"; }
CUENTA=$(aws sts get-caller-identity --query Account --output text); BUCKET=todobarato-ep3-$CUENTA
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
# dos subredes en zonas distintas
mapfile -t SUBREDES < <(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC" Name=default-for-az,Values=true --query 'sort_by(Subnets,&AvailabilityZone)[].[SubnetId]' --output text | awk 'NR<=2')
[ "${#SUBREDES[@]}" -ge 2 ] || { echo "Se necesitan 2 subredes"; exit 1; }
ENV=$SALIDA/asg.env; touch "$ENV"; source "$ENV"
guardar() { grep -v "^$1=" "$ENV" > "$ENV.tmp" || true; echo "$1=$2" >> "$ENV.tmp"; mv "$ENV.tmp" "$ENV"; }
CLAVES=${ML_API_KEYS:-$(for i in $(seq 1 40); do printf "%s," "$(openssl rand -hex 8)"; done | sed "s/,$//")}
RABBIT_PASS=${RABBIT_PASS:-$(openssl rand -hex 12)}; DB_CLAVE=${DB_CLAVE:-$(openssl rand -hex 14)}

log "1/9 Código a S3"
git -C "$RAIZ" archive --format=tar.gz -o "$SALIDA/fuente.tgz" HEAD app ml alembic alembic.ini pyproject.toml README.md Dockerfile EP3_ITY1102/modelo
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || aws s3 mb "s3://$BUCKET" >/dev/null
aws s3 cp "$SALIDA/fuente.tgz" "s3://$BUCKET/fuente.tgz" --only-show-errors
aws s3 rm "s3://$BUCKET/images/stack.tar.gz" 2>/dev/null || true

log "2/9 Grupos de seguridad"
sg() { local id; id=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC" Name=group-name,Values="$1" --query 'SecurityGroups[0].GroupId' --output text)
  [ "$id" != None ] || id=$(aws ec2 create-security-group --vpc-id "$VPC" --group-name "$1" --description "$2" --query GroupId --output text); echo "$id"; }
permitir() { aws ec2 authorize-security-group-ingress "$@" >/dev/null 2>&1 || true; }
SG_ALB=$(sg $P-alb "ALB publico"); SG_APP=$(sg $P-app "Replicas API"); SG_SVC=$(sg $P-svc "RabbitMQ y worker"); SG_DB=$(sg $P-db "RDS")
permitir --group-id "$SG_ALB" --protocol tcp --port 80 --cidr 0.0.0.0/0
permitir --group-id "$SG_APP" --protocol tcp --port 80 --source-group "$SG_ALB"
permitir --group-id "$SG_SVC" --protocol tcp --port 5672 --source-group "$SG_APP"
permitir --group-id "$SG_DB" --protocol tcp --port 5432 --source-group "$SG_APP"
permitir --group-id "$SG_DB" --protocol tcp --port 5432 --source-group "$SG_SVC"

log "3/9 RDS PostgreSQL (db.t3.micro)"
if ! aws rds describe-db-instances --db-instance-identifier $P-pg >/dev/null 2>&1; then
  aws rds create-db-subnet-group --db-subnet-group-name $P-db --db-subnet-group-description $P --subnet-ids "${SUBREDES[@]}" >/dev/null 2>&1 || true
  VER=$(aws rds describe-db-engine-versions --engine postgres --query "DBEngineVersions[?starts_with(EngineVersion,'17.')].EngineVersion | [-1]" --output text)
  aws rds create-db-instance --db-instance-identifier $P-pg --engine postgres --engine-version "$VER" --db-instance-class db.t3.micro \
    --allocated-storage 20 --storage-type gp3 --storage-encrypted --master-username tb --master-user-password "$DB_CLAVE" --db-name tb \
    --vpc-security-group-ids "$SG_DB" --db-subnet-group-name $P-db --no-publicly-accessible --backup-retention-period 0 --no-multi-az --no-deletion-protection \
    --tags "$ETIQUETA" >/dev/null
fi
aws rds wait db-instance-available --db-instance-identifier $P-pg
DB_HOST=$(aws rds describe-db-instances --db-instance-identifier $P-pg --query 'DBInstances[0].Endpoint.Address' --output text)
DB_URL="postgresql://tb:$DB_CLAVE@$DB_HOST:5432/tb?sslmode=require"
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
subst() { sed -e "s|__BUCKET__|$BUCKET|g" -e "s|__DB_URL__|$DB_URL|g" -e "s|__RABBIT_PASS__|$RABBIT_PASS|g" -e "s|__SVC_IP__|${SVC_IP:-}|g" -e "s|__API_KEYS__|$CLAVES|g" "$1"; }

log "4/9 Instancia de servicios (construye imágenes, RabbitMQ, worker)"
subst "$INFRA/arranque-servicios.sh" > "$SALIDA/ud-servicios.sh"
SVC_ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type t3.medium --iam-instance-profile Name=myS3Role --security-group-ids "$SG_SVC" \
  --user-data "file://$SALIDA/ud-servicios.sh" --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --metadata-options 'HttpTokens=required,HttpEndpoint=enabled' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$P-servicios},{$ETIQUETA}]" --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids "$SVC_ID"
SVC_IP=$(aws ec2 describe-instances --instance-ids "$SVC_ID" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)
guardar SVC_ID "$SVC_ID"

log "5/9 Launch template de las réplicas"
subst "$INFRA/arranque-replica.sh" > "$SALIDA/ud-replica.sh"
UD=$(base64 -w0 "$SALIDA/ud-replica.sh")
DATOS=$(cat <<JSON
{"ImageId":"$AMI","InstanceType":"t3.medium","IamInstanceProfile":{"Name":"myS3Role"},"SecurityGroupIds":["$SG_APP"],"UserData":"$UD",
 "MetadataOptions":{"HttpTokens":"required","HttpEndpoint":"enabled"},"Monitoring":{"Enabled":true},
 "BlockDeviceMappings":[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3","DeleteOnTermination":true}}],
 "TagSpecifications":[{"ResourceType":"instance","Tags":[{"Key":"Name","Value":"$P-api"},{"Key":"Proyecto","Value":"$P"}]}]}
JSON
)
aws ec2 create-launch-template --launch-template-name $P-api --launch-template-data "$DATOS" >/dev/null 2>&1 \
  || { aws ec2 create-launch-template-version --launch-template-name $P-api --launch-template-data "$DATOS" >/dev/null; aws ec2 modify-launch-template --launch-template-name $P-api --default-version '$Latest' >/dev/null; }

log "6/9 ALB y target group"
TG=$(aws elbv2 describe-target-groups --names $P-api --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)
if [ -z "$TG" ] || [ "$TG" = None ]; then
  TG=$(aws elbv2 create-target-group --name $P-api --protocol HTTP --port 80 --vpc-id "$VPC" --target-type instance --health-check-path /api/v1/ml/health \
    --health-check-interval-seconds 10 --health-check-timeout-seconds 5 --healthy-threshold-count 2 --unhealthy-threshold-count 3 --matcher HttpCode=200 --query 'TargetGroups[0].TargetGroupArn' --output text)
  aws elbv2 modify-target-group-attributes --target-group-arn "$TG" --attributes Key=deregistration_delay.timeout_seconds,Value=30 Key=load_balancing.algorithm.type,Value=least_outstanding_requests >/dev/null
fi
ALB=$(aws elbv2 describe-load-balancers --names $P-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)
if [ -z "$ALB" ] || [ "$ALB" = None ]; then
  ALB=$(aws elbv2 create-load-balancer --name $P-alb --type application --scheme internet-facing --subnets "${SUBREDES[@]}" --security-groups "$SG_ALB" --query 'LoadBalancers[0].LoadBalancerArn' --output text)
  aws elbv2 create-listener --load-balancer-arn "$ALB" --protocol HTTP --port 80 --default-actions Type=forward,TargetGroupArn="$TG" >/dev/null
fi
ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns "$ALB" --query 'LoadBalancers[0].DNSName' --output text)

log "7/9 Auto Scaling Group (2-4 réplicas, CPU objetivo 50 %)"
SUB_CSV=$(IFS=,; echo "${SUBREDES[*]}")
aws autoscaling create-auto-scaling-group --auto-scaling-group-name $P-api --launch-template LaunchTemplateName=$P-api,Version='$Latest' \
  --min-size 2 --max-size 4 --desired-capacity 2 --vpc-zone-identifier "$SUB_CSV" --target-group-arns "$TG" \
  --health-check-type ELB --health-check-grace-period 900 --default-instance-warmup 180 \
  --tags "ResourceId=$P-api,ResourceType=auto-scaling-group,Key=Proyecto,Value=$P,PropagateAtLaunch=true"
aws autoscaling enable-metrics-collection --auto-scaling-group-name $P-api --granularity 1Minute
aws autoscaling put-scaling-policy --auto-scaling-group-name $P-api --policy-name $P-cpu-50 --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"},"TargetValue":50.0}' >/dev/null
ALB_SUF=$(echo "$ALB" | sed 's#.*:loadbalancer/##'); TG_SUF=${TG##*:}
aws cloudwatch put-metric-alarm --alarm-name $P-replica-caida --namespace AWS/ApplicationELB --metric-name UnHealthyHostCount --statistic Maximum --period 60 \
  --evaluation-periods 3 --threshold 0 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching \
  --dimensions Name=TargetGroup,Value="$TG_SUF" Name=LoadBalancer,Value="$ALB_SUF"

log "8/9 CloudFront (HTTPS)"
if [ -z "${CF_ID:-}" ]; then
  sed -e "s/__REF__/$P-$(date +%s)/" -e "s/__ALB_DNS__/$ALB_DNS/" -e "s/__SECRETO__/$(openssl rand -hex 16)/" "$INFRA/cloudfront.json" > "$SALIDA/cloudfront.json"
  read -r CF_ID CF_DOMINIO < <(aws cloudfront create-distribution --distribution-config "file://$SALIDA/cloudfront.json" --query 'Distribution.[Id,DomainName]' --output text)
  guardar CF_ID "$CF_ID"; guardar CF_DOMINIO "$CF_DOMINIO"
fi
guardar ALB_DNS "$ALB_DNS"; guardar API_KEYS "$CLAVES"; guardar API_KEY "${CLAVES%%,*}"; guardar DB_HOST "$DB_HOST"; guardar SVC_IP "$SVC_IP"; guardar RABBIT_PASS "$RABBIT_PASS"; guardar DB_CLAVE "$DB_CLAVE"
log "9/9 Listo (las réplicas tardan ~8 min en estar sanas; CloudFront ~8 min)"
echo "ALB:        http://$ALB_DNS/api/v1/ml/dashboard"
echo "HTTPS:      https://${CF_DOMINIO:-$(grep CF_DOMINIO "$ENV" | cut -d= -f2)}/api/v1/ml/dashboard"
echo "Estado en:  $ENV (ignorado por git)"
