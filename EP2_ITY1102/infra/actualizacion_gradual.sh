#!/usr/bin/env bash
# Actualización gradual (rolling) sin caída: reemplaza las réplicas de un ASG de a una.
# AWS Academy niega autoscaling:StartInstanceRefresh, así que se hace lo mismo a mano:
#   1) retirar una instancia vieja por el ASG (el ALB la drena 30 s, sin perder solicitudes)
#   2) esperar a que su reemplazo (con la imagen nueva) esté sano en el ALB
#   3) seguir con la siguiente
#   bash EP2_ITY1102/infra/actualizacion_gradual.sh [api|worker]
source "$(dirname "$0")/comun.sh"
cargar
ROL=${1:-api}
ASG="$P-$ROL"
case "$ROL" in api) TG="$TG_API" ;; worker) TG="$TG_WORKER" ;; *) echo "rol desconocido: $ROL"; exit 1 ;; esac
DESEADO=$($AWS autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG" --query 'AutoScalingGroups[0].DesiredCapacity' --output text)
VIEJAS=$($AWS autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG" --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId' --output text)

sanas() { $AWS elbv2 describe-target-health --target-group-arn "$TG" --query 'length(TargetHealthDescriptions[?TargetHealth.State==`healthy`])' --output text; }

for vieja in $VIEJAS; do
  log "Retirando $vieja de $ASG (drenaje en el ALB)"
  $AWS autoscaling terminate-instance-in-auto-scaling-group --instance-id "$vieja" --no-should-decrement-desired-capacity >/dev/null
  log "   esperando su reemplazo sano (~4 min)…"
  sleep 60
  for _ in $(seq 1 40); do
    n=$(sanas)
    quedan=$($AWS elbv2 describe-target-health --target-group-arn "$TG" --query "length(TargetHealthDescriptions[?Target.Id=='$vieja'])" --output text)
    if [ "$n" -ge "$DESEADO" ] && [ "$quedan" = 0 ]; then log "   $DESEADO réplicas sanas"; break; fi
    sleep 15
  done
done
log "Actualización gradual de $ASG terminada"
