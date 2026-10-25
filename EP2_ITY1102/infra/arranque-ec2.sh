#!/bin/bash
# User data de las EC2 (Amazon Linux 2023). desplegar.sh reemplaza __ROL__ y __BUCKET__.
#   api    → backend (:8000) + frontend (:3000), detrás del ALB, sin scheduler de ingesta.
#   worker → solo backend (:8000) con el scheduler de ingesta y el endpoint de eventos SNS.
set -euxo pipefail
ROL=__ROL__
BUCKET=__BUCKET__

dnf install -y docker
systemctl enable --now docker

TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')
meta() { curl -sH "X-aws-ec2-metadata-token: $TOKEN" "http://169.254.169.254/latest/meta-data/$1"; }
INSTANCIA=$(meta instance-id)
ZONA=$(meta placement/availability-zone)

mkdir -p /opt/todobarato && cd /opt/todobarato
# Configuración cifrada en S3 (SSE): solo el rol de la instancia la puede leer.
aws s3 cp "s3://$BUCKET/config/$ROL.env" app.env
chmod 600 app.env
aws s3 cp "s3://$BUCKET/imagenes/backend.tar.gz" - | docker load

docker network create tb || true
LOGS=(--log-driver json-file --log-opt max-size=20m --log-opt max-file=3)

docker run -d --name backend --network tb --network-alias backend --restart always \
  --env-file app.env -e INSTANCIA="$INSTANCIA" -e ZONA="$ZONA" -e ROL="$ROL" \
  -p 8000:8000 "${LOGS[@]}" todobarato-backend:ep2

if [ "$ROL" = api ]; then
  aws s3 cp "s3://$BUCKET/imagenes/frontend.tar.gz" - | docker load
  docker run -d --name frontend --network tb --restart always \
    -e BACKEND_URL=http://backend:8000 -p 3000:3000 "${LOGS[@]}" todobarato-frontend:ep2
fi

# Logs de los contenedores a S3 cada 5 minutos (el rol no tiene permisos de CloudWatch Logs).
cat > /usr/local/bin/subir-logs.sh <<EOF
#!/bin/bash
for c in \$(docker ps --format '{{.Names}}'); do
  docker logs --since 6m "\$c" 2>&1 | gzip | aws s3 cp - "s3://$BUCKET/logs/\$(date -u +%Y/%m/%d)/$ROL/$INSTANCIA/\$c-\$(date -u +%H%M).log.gz" --quiet
done
EOF
chmod +x /usr/local/bin/subir-logs.sh
cat > /etc/systemd/system/subir-logs.service <<'EOF'
[Service]
Type=oneshot
ExecStart=/usr/local/bin/subir-logs.sh
EOF
cat > /etc/systemd/system/subir-logs.timer <<'EOF'
[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now subir-logs.timer
