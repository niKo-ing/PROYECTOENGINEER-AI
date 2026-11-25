#!/usr/bin/env bash
# Evidencia de la pila desplegada en AWS, para el informe y la defensa. Ejecutar después de desplegar_asg.sh (o con la URL
# de desplegar.sh), con las credenciales del laboratorio en el entorno:
#
#   bash EP3_ITY1102/infra/capturar_evidencia.sh [URL] [minutos hacia atrás para CloudWatch, 60 por defecto]
#
# 1. Capturas del dashboard y de Swagger con la URL, la hora y la instancia visibles (capturar_evidencia.py).
# 2. Gráficos de CloudWatch como PNG (GetMetricWidgetImage): CPU del Auto Scaling Group, réplicas en servicio,
#    solicitudes y errores del ALB y latencia p50/p95/p99. Sin entrar a la consola.
# Todo queda en EP3_ITY1102/evidencia/. Luego: python EP3_ITY1102/documento/generar.py (el informe toma las capturas nuevas).
set -euo pipefail
export AWS_PAGER="" AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
DIR=$(cd "$(dirname "$0")" && pwd); EVI="$DIR/../evidencia"; ENV="$DIR/.salida/asg.env"
[ -f "$ENV" ] && source "$ENV"
URL=${1:-${CF_DOMINIO:+https://$CF_DOMINIO}}
URL=${URL:?Indique la URL (p. ej. https://xxxx.cloudfront.net o http://IP), o despliegue antes con desplegar_asg.sh}
MIN=${2:-60}
PY=$(command -v "$DIR/../../.venv/bin/python" || command -v python3)

echo "== Capturas de $URL"
"$PY" "$DIR/capturar_evidencia.py" "$URL" "$EVI"

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Sin credenciales de AWS en el entorno: se omiten los gráficos de CloudWatch."; exit 0
fi
P=tb-ep3
grafico() {  # grafico <archivo> <métricas JSON> <título> <estadística>
  local w; w=$(printf '{"title":"%s","width":900,"height":360,"start":"-PT%sM","end":"P0D","period":60,"stat":"%s","region":"%s","timezone":"-0300","metrics":%s}' \
    "$3" "$MIN" "$4" "$AWS_DEFAULT_REGION" "$2")
  aws cloudwatch get-metric-widget-image --metric-widget "$w" --output text --query MetricWidgetImage | base64 -d > "$EVI/$1"
  echo "✔ $EVI/$1"
}
echo "== CloudWatch (últimos $MIN min)"
grafico cw-cpu-asg.png "[[\"AWS/EC2\",\"CPUUtilization\",\"AutoScalingGroupName\",\"$P-api\",{\"label\":\"CPU de la API (promedio del ASG)\"}]]" "CPU del Auto Scaling Group (%)" Average
grafico cw-replicas-asg.png "[[\"AWS/AutoScaling\",\"GroupInServiceInstances\",\"AutoScalingGroupName\",\"$P-api\",{\"label\":\"En servicio\"}],[\"AWS/AutoScaling\",\"GroupDesiredCapacity\",\"AutoScalingGroupName\",\"$P-api\",{\"label\":\"Deseadas\"}]]" "Réplicas de la API" Maximum
if [ -n "${ALB_DNS:-}" ]; then
  ALB_ARN=$(aws elbv2 describe-load-balancers --query "LoadBalancers[?DNSName=='$ALB_DNS'].LoadBalancerArn | [0]" --output text)
  if [ "$ALB_ARN" != "None" ] && [ -n "$ALB_ARN" ]; then
    ALB_S=${ALB_ARN#*:loadbalancer/}
    grafico cw-solicitudes-alb.png "[[\"AWS/ApplicationELB\",\"RequestCount\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"Solicitudes por minuto\"}],[\"AWS/ApplicationELB\",\"HTTPCode_Target_5XX_Count\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"5xx de la API\"}],[\"AWS/ApplicationELB\",\"HTTPCode_Target_4XX_Count\",\"LoadBalancer\",\"$ALB_S\",{\"label\":\"4xx (incluye 429)\"}]]" "ALB: solicitudes y errores por minuto" Sum
    grafico cw-latencia-alb.png "[[\"AWS/ApplicationELB\",\"TargetResponseTime\",\"LoadBalancer\",\"$ALB_S\",{\"stat\":\"p50\",\"label\":\"p50\"}],[\"...\",{\"stat\":\"p95\",\"label\":\"p95\"}],[\"...\",{\"stat\":\"p99\",\"label\":\"p99\"}]]" "Latencia de la API en el ALB (s)" p95
  fi
fi
echo "Listo. Regenere el informe: python EP3_ITY1102/documento/generar.py && bash EP3_ITY1102/documento/pdf.sh"
