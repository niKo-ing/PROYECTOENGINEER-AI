#!/usr/bin/env bash
# Borra todo lo que creó desplegar.sh (todos los recursos llevan el prefijo tb-ep2 / etiqueta Proyecto=tb-ep2).
#   bash EP2_ITY1102/infra/destruir.sh            # borra todo, menos el bucket S3 (imágenes y logs, céntimos)
#   BORRAR_BUCKET=1 bash ...destruir.sh           # también vacía y borra el bucket
source "$(dirname "$0")/comun.sh"
set +e   # seguir aunque algún recurso ya no exista

cargar
if [ -n "${CF_ID:-}" ] && $AWS cloudfront get-distribution --id "$CF_ID" >/dev/null 2>&1; then
  log "CloudFront $CF_ID (se desactiva y se borra; tarda ~5-15 min)"
  ETAG=$($AWS cloudfront get-distribution-config --id "$CF_ID" --query ETag --output text)
  $AWS cloudfront get-distribution-config --id "$CF_ID" --query DistributionConfig --output json \
    | python3 -I -c 'import json,sys; c=json.load(sys.stdin); c["Enabled"]=False; print(json.dumps(c))' > "$SALIDA/cf-off.json"
  $AWS cloudfront update-distribution --id "$CF_ID" --if-match "$ETAG" --distribution-config "file://$SALIDA/cf-off.json" >/dev/null
  $AWS cloudfront wait distribution-deployed --id "$CF_ID"
  ETAG=$($AWS cloudfront get-distribution-config --id "$CF_ID" --query ETag --output text)
  $AWS cloudfront delete-distribution --id "$CF_ID" --if-match "$ETAG" && sed -i '/^CF_ID=/d;/^CF_DOMINIO=/d' "$ESTADO"
fi

log "Reglas de EventBridge"
$AWS events remove-targets --rule "$P-ingesta-programada" --ids sns-eventos >/dev/null 2>&1
$AWS events delete-rule --name "$P-ingesta-programada" 2>/dev/null

log "Auto Scaling Groups (termina las EC2)"
for r in api worker; do
  $AWS autoscaling delete-auto-scaling-group --auto-scaling-group-name "$P-$r" --force-delete 2>/dev/null
done

log "ALB"
ALB=$($AWS elbv2 describe-load-balancers --names "$P-alb" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null)
[ -n "$ALB" ] && [ "$ALB" != None ] && $AWS elbv2 delete-load-balancer --load-balancer-arn "$ALB" && \
  $AWS elbv2 wait load-balancers-deleted --load-balancer-arns "$ALB"

log "RDS (sin snapshot final: los datos de origen siguen en Supabase)"
$AWS rds delete-db-instance --db-instance-identifier "$P-postgres" --skip-final-snapshot --delete-automated-backups >/dev/null 2>&1

log "Esperando a que terminen las EC2…"
for _ in $(seq 1 40); do
  n=$($AWS ec2 describe-instances --filters Name=tag:Proyecto,Values="$P" Name=instance-state-name,Values=pending,running,shutting-down,stopping \
      --query 'length(Reservations[].Instances[])' --output text)
  [ "$n" = 0 ] && break; sleep 10
done

log "Target groups, launch templates, alarmas, dashboard, temas SNS"
for t in front api worker; do
  arn=$($AWS elbv2 describe-target-groups --names "$P-$t" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null)
  [ -n "$arn" ] && [ "$arn" != None ] && $AWS elbv2 delete-target-group --target-group-arn "$arn"
done
for r in api worker; do $AWS ec2 delete-launch-template --launch-template-name "$P-$r" >/dev/null 2>&1; done
$AWS cloudwatch delete-alarms --alarm-names $($AWS cloudwatch describe-alarms --alarm-name-prefix "$P-" --query 'MetricAlarms[].AlarmName' --output text) 2>/dev/null
$AWS cloudwatch delete-dashboards --dashboard-names "$P" 2>/dev/null
for t in alarmas eventos-ingesta; do $AWS sns delete-topic --topic-arn "arn:aws:sns:$REGION:$CUENTA:$P-$t" 2>/dev/null; done

log "Esperando a que se borre RDS (~5 min) para soltar los security groups…"
$AWS rds wait db-instance-deleted --db-instance-identifier "$P-postgres" 2>/dev/null
$AWS rds delete-db-subnet-group --db-subnet-group-name "$P-db" 2>/dev/null

log "Security groups"
for s in db app alb; do
  id=$($AWS ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC" Name=group-name,Values="$P-$s" --query 'SecurityGroups[0].GroupId' --output text)
  [ -n "$id" ] && [ "$id" != None ] && $AWS ec2 delete-security-group --group-id "$id"
done

if [ "${BORRAR_BUCKET:-0}" = 1 ]; then
  log "Bucket $BUCKET (con todas sus versiones)"
  python3 -I - "$BUCKET" <<'PY'
import json, subprocess, sys, os
aws = os.path.expanduser("~/.local/bin/aws"); b = sys.argv[1]
while True:
    r = json.loads(subprocess.run([aws, "s3api", "list-object-versions", "--bucket", b, "--max-items", "500", "--output", "json"], capture_output=True, text=True).stdout or "{}")
    objs = [{"Key": o["Key"], "VersionId": o["VersionId"]} for o in r.get("Versions", []) + r.get("DeleteMarkers", [])]
    if not objs: break
    subprocess.run([aws, "s3api", "delete-objects", "--bucket", b, "--delete", json.dumps({"Objects": objs, "Quiet": True})], check=True)
PY
  $AWS s3api delete-bucket --bucket "$BUCKET"
  : > "$ESTADO"
else
  # Sin RDS los datos hay que volver a cargarlos en el próximo despliegue.
  sed -i '/^DATOS_CARGADOS=/d;/^DB_HOST=/d' "$ESTADO"
fi

log "Recursos con la etiqueta Proyecto=$P que quedan:"
$AWS resourcegroupstaggingapi get-resources --tag-filters Key=Proyecto,Values="$P" --query 'ResourceTagMappingList[].ResourceARN' --output text 2>/dev/null
log "Listo."
