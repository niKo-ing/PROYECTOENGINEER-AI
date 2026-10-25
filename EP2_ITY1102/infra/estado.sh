#!/usr/bin/env bash
# Muestra el estado del despliegue y reintenta la suscripción SNS → worker si quedó pendiente.
#   bash EP2_ITY1102/infra/estado.sh
source "$(dirname "$0")/comun.sh"
cargar

echo "== Salud de los destinos del ALB"
for tg in "$TG_FRONT" "$TG_API" "$TG_WORKER"; do
  echo "-- ${tg##*/targetgroup/}"
  $AWS elbv2 describe-target-health --target-group-arn "$tg" \
    --query 'TargetHealthDescriptions[].[Target.Id,TargetHealth.State,TargetHealth.Reason]' --output text
done

echo "== Instancias"
$AWS ec2 describe-instances --filters Name=tag:Proyecto,Values="$P" Name=instance-state-name,Values=pending,running \
  --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Rol`]|[0].Value,Placement.AvailabilityZone,InstanceType,State.Name]' --output text

echo "== RDS"
$AWS rds describe-db-instances --db-instance-identifier "$P-postgres" \
  --query 'DBInstances[0].[DBInstanceStatus,DBInstanceClass,MultiAZ,PubliclyAccessible,AvailabilityZone]' --output text

echo "== Reparto del ALB (6 llamadas a /health)"
for _ in 1 2 3 4 5 6; do curl -s --max-time 5 "http://$ALB_DNS/health"; echo; done

echo "== Suscripción SNS → worker"
SUB=$($AWS sns list-subscriptions-by-topic --topic-arn "$TEMA_EVENTOS" --query 'Subscriptions[0].SubscriptionArn' --output text)
echo "$SUB"
if [ "$SUB" = PendingConfirmation ] || [ "$SUB" = None ]; then
  echo "   reintentando (el worker debe estar sano)…"
  $AWS sns subscribe --topic-arn "$TEMA_EVENTOS" --protocol http --notification-endpoint "http://$ALB_DNS/api/v1/eventos/sns" >/dev/null
fi

echo "== Alarmas"
$AWS cloudwatch describe-alarms --alarm-name-prefix "$P-" --query 'MetricAlarms[].[AlarmName,StateValue]' --output text
echo
echo "App: http://$ALB_DNS/"
