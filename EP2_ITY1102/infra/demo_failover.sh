#!/usr/bin/env bash
# Demostración de alta disponibilidad: termina una réplica de la API mientras se consulta /health cada 0,5 s.
# Muestra qué instancia/zona responde, cuántas solicitudes fallaron y cuándo el ASG repone la réplica.
#   bash EP2_ITY1102/infra/demo_failover.sh            # caída abrupta (EC2 terminada sin aviso)
#   MODO=planificado bash ...demo_failover.sh          # retiro por el ASG: el ALB drena antes de apagar
source "$(dirname "$0")/comun.sh"
cargar
set +e   # un curl que agota el tiempo no debe cortar la demo
MODO=${MODO:-abrupto}
OUT="$SALIDA/failover-$MODO-$(date +%H%M).txt"
VICTIMA=$($AWS autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$P-api" \
  --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`]|[0].InstanceId' --output text)
ZONA_V=$($AWS ec2 describe-instances --instance-ids "$VICTIMA" --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text)
log "Réplica a terminar: $VICTIMA ($ZONA_V)" | tee "$OUT"

ok=0; fallas=0; inicio=$(date +%s)
sondear() {  # sondear <segundos>
  local fin=$(( $(date +%s) + $1 ))
  while [ "$(date +%s)" -lt "$fin" ]; do
    r=$(curl -s --max-time 3 -o /dev/stdout -w ' %{http_code}' "http://$ALB_DNS/health")
    t=$(( $(date +%s) - inicio ))
    if [[ "$r" == *' 200' ]]; then ok=$((ok+1)); echo "t=${t}s 200 $(echo "$r" | sed 's/ 200$//' | tr -d '\n')" >> "$OUT"
    else fallas=$((fallas+1)); echo "t=${t}s FALLA $r" | tee -a "$OUT"; fi
    sleep 0.5
  done
}
sondear 10
if [ "$MODO" = planificado ]; then
  log "Retirando $VICTIMA por el ASG (drenaje de 30 s en el ALB, luego se apaga)" | tee -a "$OUT"
  $AWS autoscaling terminate-instance-in-auto-scaling-group --instance-id "$VICTIMA" --no-should-decrement-desired-capacity >/dev/null
else
  log "Terminando $VICTIMA sin aviso (simula la caída de una instancia)" | tee -a "$OUT"
  $AWS ec2 terminate-instances --instance-ids "$VICTIMA" >/dev/null
fi
sondear 120
log "Solicitudes OK: $ok · fallidas: $fallas · disponibilidad en la prueba: $(python3 -c "print(f'{100*$ok/($ok+$fallas):.2f} %')")" | tee -a "$OUT"
log "Respuestas por instancia:" | tee -a "$OUT"
grep -o '"instancia":"[^"]*","zona":"[^"]*"' "$OUT" | sort | uniq -c | tee -a "$OUT"
log "Estado del ASG (el reemplazo tarda ~4 min en pasar el health check):" | tee -a "$OUT"
$AWS autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$P-api" \
  --query 'AutoScalingGroups[0].Instances[].[InstanceId,AvailabilityZone,LifecycleState,HealthStatus]' --output text | tee -a "$OUT"
$AWS autoscaling describe-scaling-activities --auto-scaling-group-name "$P-api" --max-items 2 \
  --query 'Activities[].[StartTime,StatusCode,Description]' --output text | tee -a "$OUT"
echo "Registro en $OUT"
