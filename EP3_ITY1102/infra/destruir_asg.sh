#!/usr/bin/env bash
# Borra TODO lo de desplegar_asg.sh: CloudFront, ASG, ALB, plantilla, servicios, RDS, grupos de seguridad y bucket.
# No borrar nada sin una decisión explícita del equipo (23-11-2026): este script elimina la infraestructura y sus
# datos sin respaldo. Además, la plataforma del laboratorio ya limpia la cuenta sola (EP3_ITY1102/evidencia/limpieza-laboratorio.txt).
if [ "${CONFIRMO_BORRAR:-}" != "si" ]; then
  echo "No se borró nada. Solo si el equipo lo decidió: CONFIRMO_BORRAR=si bash $0" >&2
  exit 1
fi
set -uo pipefail
export AWS_PAGER="" AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
cd "$(dirname "$0")"; ENV=.salida/asg.env; [ -f "$ENV" ] && source "$ENV"
P=tb-ep3; CUENTA=$(aws sts get-caller-identity --query Account --output text)
if [ -n "${CF_ID:-}" ]; then
  ETAG=$(aws cloudfront get-distribution-config --id "$CF_ID" --query ETag --output text 2>/dev/null)
  if [ -n "$ETAG" ]; then
    aws cloudfront get-distribution-config --id "$CF_ID" --query DistributionConfig | python3 -c "import json,sys;c=json.load(sys.stdin);c['Enabled']=False;print(json.dumps(c))" > .salida/cf-off.json
    aws cloudfront update-distribution --id "$CF_ID" --if-match "$ETAG" --distribution-config file://.salida/cf-off.json >/dev/null
    echo "CloudFront deshabilitada: bórrela luego con 'aws cloudfront delete-distribution --id $CF_ID --if-match <ETag>' cuando termine de propagar (~10 min)"
  fi
fi
aws autoscaling delete-auto-scaling-group --auto-scaling-group-name $P-api --force-delete 2>/dev/null
aws cloudwatch delete-alarms --alarm-names $P-replica-caida 2>/dev/null
ALB=$(aws elbv2 describe-load-balancers --names $P-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null); [ -n "$ALB" ] && [ "$ALB" != None ] && aws elbv2 delete-load-balancer --load-balancer-arn "$ALB"
[ -n "${SVC_ID:-}" ] && aws ec2 terminate-instances --instance-ids "$SVC_ID" >/dev/null
aws rds delete-db-instance --db-instance-identifier $P-pg --skip-final-snapshot --delete-automated-backups >/dev/null 2>&1
echo "Esperando a que terminen las instancias y el ALB (~3 min)…"; sleep 180
TG=$(aws elbv2 describe-target-groups --names $P-api --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null); [ -n "$TG" ] && [ "$TG" != None ] && aws elbv2 delete-target-group --target-group-arn "$TG"
aws ec2 delete-launch-template --launch-template-name $P-api >/dev/null 2>&1
aws rds wait db-instance-deleted --db-instance-identifier $P-pg 2>/dev/null; aws rds delete-db-subnet-group --db-subnet-group-name $P-db 2>/dev/null
for g in $P-alb $P-app $P-svc $P-db; do aws ec2 delete-security-group --group-name $g 2>/dev/null; done
aws s3 rb "s3://todobarato-ep3-$CUENTA" --force >/dev/null 2>&1
echo "Listo (revise que CloudFront quede borrada)."
