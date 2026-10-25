#!/usr/bin/env bash
# Pone CloudFront delante del ALB para servir la app por HTTPS (certificado *.cloudfront.net, sin dominio propio).
# Sin HTTPS el navegador no es un «contexto seguro» y APIs como crypto.randomUUID no existen.
#   bash EP2_ITY1102/infra/https_cloudfront.sh      # crea (o muestra) la distribución; tarda ~5-10 min en propagar
source "$(dirname "$0")/comun.sh"
cargar

if [ -n "${CF_ID:-}" ] && $AWS cloudfront get-distribution --id "$CF_ID" >/dev/null 2>&1; then
  log "La distribución ya existe: https://$CF_DOMINIO/"
  exit 0
fi
[ -n "${CF_SECRETO:-}" ] || { CF_SECRETO=$(openssl rand -hex 16); guardar CF_SECRETO "$CF_SECRETO"; }
sed -e "s/__REF__/$P-$(date +%s)/" -e "s/__ALB_DNS__/$ALB_DNS/" -e "s/__SECRETO__/$CF_SECRETO/" \
  "$INFRA/cloudfront.json" > "$SALIDA/cloudfront.json"
read -r CF_ID CF_DOMINIO < <($AWS cloudfront create-distribution --distribution-config "file://$SALIDA/cloudfront.json" \
  --query 'Distribution.[Id,DomainName]' --output text)
guardar CF_ID "$CF_ID"; guardar CF_DOMINIO "$CF_DOMINIO"
log "Distribución $CF_ID creada. En ~5-10 min: https://$CF_DOMINIO/"
