#!/usr/bin/env bash
# Exporta gráficos de CloudWatch como PNG (GetMetricWidgetImage) a EP2_ITY1102/evidencia/, sin entrar a la consola.
#   bash EP2_ITY1102/infra/exportar_graficos.sh [minutos hacia atrás]
source "$(dirname "$0")/comun.sh"
cargar
MIN=${1:-40}
EVI="$INFRA/../evidencia"; mkdir -p "$EVI"
ALB_S=$(echo "$ALB" | sed 's#.*:loadbalancer/##'); TGA=${TG_API##*:}; TGF=${TG_FRONT##*:}
grafico() {  # grafico <archivo> <json de métricas> <título> [estadística]
  local w
  w=$(cat <<JSON
{"title":"$3","width":900,"height":360,"start":"-PT${MIN}M","end":"P0D","period":60,"stat":"${4:-Sum}","region":"$REGION",
 "timezone":"-0300","metrics":$2}
JSON
)
  $AWS cloudwatch get-metric-widget-image --metric-widget "$w" --output text --query MetricWidgetImage | base64 -d > "$EVI/$1"
  echo "$EVI/$1"
}
grafico cw-solicitudes.png "[[\"AWS/ApplicationELB\",\"RequestCount\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"Solicitudes por minuto\"}],[\"AWS/ApplicationELB\",\"HTTPCode_Target_5XX_Count\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"5xx del backend\"}],[\"AWS/ApplicationELB\",\"HTTPCode_ELB_5XX_Count\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"5xx del ALB\"}]]" "ALB: solicitudes y errores por minuto"
grafico cw-latencia.png "[[\"AWS/ApplicationELB\",\"TargetResponseTime\",\"TargetGroup\",\"$TGA\",\"LoadBalancer\",\"$ALB_S\",{\"stat\":\"p50\",\"label\":\"p50\"}],[\"...\",{\"stat\":\"p95\",\"label\":\"p95\"}],[\"...\",{\"stat\":\"p99\",\"label\":\"p99\"}]]" "Latencia del backend (s)" p95
grafico cw-replicas.png "[[\"AWS/ApplicationELB\",\"HealthyHostCount\",\"TargetGroup\",\"$TGA\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"API sanas\"}],[\"AWS/ApplicationELB\",\"UnHealthyHostCount\",\"TargetGroup\",\"$TGA\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"API no sanas\"}]]" "Réplicas de la API (failover y reposición)" Maximum
grafico cw-cpu.png "[[\"AWS/EC2\",\"CPUUtilization\",\"AutoScalingGroupName\",\"$P-api\",{\"label\":\"CPU API (ASG)\"}],[\"AWS/RDS\",\"CPUUtilization\",\"DBInstanceIdentifier\",\"$P-postgres\",{\"label\":\"CPU RDS\"}]]" "CPU durante la prueba de carga (%)" Average
