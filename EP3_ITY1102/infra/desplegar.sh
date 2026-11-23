#!/usr/bin/env bash
# Despliega la pila en AWS Academy: S3 (código) + EC2 t3.medium con Docker Compose + alarma de CloudWatch.
# API y modelo en el puerto 80, frontend (armador, asistente, panel /observabilidad) en el 3000.
# Requisitos: credenciales del lab en el entorno (AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN). Cuesta ~USD 0,05/h. No se destruye al terminar (ver docs/entrega/DEPLOY_DEFENSA.md).
# Secretos de la app, desde el entorno (nunca en el repo): GEMINI_API_KEY, ADMIN_EMAILS y, si quiere fijarlo, AUTH_JWT_SECRET.
# DATABASE_URL (opcional): base Postgres fuera del laboratorio (Supabase, Session pooler). Sin ella, SQLite en la instancia.
# Guía paso a paso: docs/entrega/DEPLOY_DEFENSA.md
set -euo pipefail
cd "$(dirname "$0")/.."          # EP3_ITY1102
RAIZ=$(cd .. && pwd)
REGION=${AWS_DEFAULT_REGION:-us-east-1}; export AWS_DEFAULT_REGION=$REGION AWS_PAGER=""
CUENTA=$(aws sts get-caller-identity --query Account --output text)
BUCKET=todobarato-ep3-$CUENTA
NOMBRE=todobarato-ep3
# varias llaves (el límite de tasa es por llave): para la prueba de carga se generan 40 y cada usuario virtual usa una
ML_API_KEYS=${ML_API_KEYS:-$(for i in $(seq 1 40); do printf "%s," "$(openssl rand -hex 8)"; done | sed "s/,$//")}
mkdir -p infra/.salida
# Secretos: viajan por el bucket privado (cifrado en reposo) y la instancia los borra del bucket al leerlos.
AUTH_JWT_SECRET=${AUTH_JWT_SECRET:-$(openssl rand -hex 32)}   # obligatorio con APP_ENV=production
[ -n "${GEMINI_API_KEY:-}" ] || echo "AVISO: falta GEMINI_API_KEY: el asistente responderá solo con reglas."
[ -n "${ADMIN_EMAILS:-}" ] || echo "AVISO: falta ADMIN_EMAILS: en producción nadie podrá abrir /observabilidad."
# Solo una base Postgres sale hacia la instancia: el .env local suele traer la SQLite de desarrollo, que allá no existe.
case "${DATABASE_URL:-}" in postgres://*|postgresql://*|postgresql+psycopg://*) BASE_EXTERNA=$DATABASE_URL ;; *) BASE_EXTERNA= ;; esac
( umask 077; printf 'GEMINI_API_KEY=%s\nAUTH_JWT_SECRET=%s\nADMIN_EMAILS=%s\n' "${GEMINI_API_KEY:-}" "$AUTH_JWT_SECRET" "${ADMIN_EMAILS:-}" > infra/.salida/secretos.env
  # comillas simples: Compose toma el valor literal (la contraseña puede traer $ u otros símbolos)
  [ -n "$BASE_EXTERNA" ] && printf "DATABASE_URL='%s'\n" "$BASE_EXTERNA" >> infra/.salida/secretos.env || true )
[ -n "$BASE_EXTERNA" ] && echo "Base: la Postgres de DATABASE_URL (fuera del laboratorio)." || echo "AVISO: sin una DATABASE_URL Postgres, la base es SQLite en la instancia y se pierde cuando el laboratorio limpia la cuenta."

echo "1/5 Empaquetando el código (git archive + modelo + datos)…"
git -C "$RAIZ" archive --format=tar.gz -o "$PWD/infra/.salida/fuente.tgz" HEAD app ml alembic alembic.ini pyproject.toml README.md Dockerfile frontend EP3_ITY1102/modelo EP3_ITY1102/infra/docker-compose.aws.yml

echo "2/5 Subiendo a s3://$BUCKET…"
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || aws s3 mb "s3://$BUCKET"
aws s3 cp infra/.salida/fuente.tgz "s3://$BUCKET/fuente.tgz"
aws s3 cp infra/.salida/secretos.env "s3://$BUCKET/secretos.env" --sse AES256 --only-show-errors
[ -f "$RAIZ/ep3_data.db" ] && aws s3 cp "$RAIZ/ep3_data.db" "s3://$BUCKET/ep3.db"

echo "3/5 Grupo de seguridad (puertos 80 y 3000)…"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=$NOMBRE Name=vpc-id,Values="$VPC" --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name $NOMBRE --description "TodoBarato EP3" --vpc-id "$VPC" --query GroupId --output text)
fi
for PUERTO in 80 3000; do   # idempotente: un grupo creado antes solo tenía el 80
  aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port $PUERTO --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
done

echo "4/5 Lanzando la instancia…"
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
cat > infra/.salida/user-data.sh <<UD
#!/bin/bash
set -ex
dnf install -y docker
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
mkdir -p /opt/app && cd /opt/app
aws s3 cp s3://$BUCKET/fuente.tgz . && tar xzf fuente.tgz
cd EP3_ITY1102/infra
export ML_API_KEYS=$ML_API_KEYS
aws s3 cp s3://$BUCKET/secretos.env secretos.env && chmod 600 secretos.env && aws s3 rm s3://$BUCKET/secretos.env || true
ln -sf secretos.env .env   # Compose lee .env para \${DATABASE_URL} del docker-compose
# /health muestra qué instancia respondió (IMDSv2); sin esto no muestra instancia ni zona.
TOKEN=\$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')
meta() { curl -sH "X-aws-ec2-metadata-token: \$TOKEN" "http://169.254.169.254/latest/meta-data/\$1"; }
printf 'INSTANCIA=%s\nZONA=%s\nROL=principal\n' "\$(meta instance-id)" "\$(meta placement/availability-zone)" >> secretos.env
docker compose -f docker-compose.aws.yml up -d --build
# carga el catálogo de ejemplo en el volumen de datos (si se subió)
aws s3 cp s3://$BUCKET/ep3.db /tmp/ep3.db || true
[ -f /tmp/ep3.db ] && docker run --rm -v infra_datos:/data -v /tmp:/src alpine cp /src/ep3.db /data/ep3.db || true
docker compose -f docker-compose.aws.yml restart backend worker
# catálogo del armador de PC (idempotente; el backend también lo siembra al arrancar si la base está vacía)
sleep 15
docker compose -f docker-compose.aws.yml exec -T backend python -c "from app.db import SessionLocal; from app.pcbuilder.catalog import seed_pc_parts; s = SessionLocal(); print('catalogo armador', seed_pc_parts(s)); s.close()" || true
UD
ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type t3.medium --iam-instance-profile Name=myS3Role \
  --security-group-ids "$SG" --user-data file://infra/.salida/user-data.sh \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3}' \
  --metadata-options 'HttpTokens=required,HttpEndpoint=enabled' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NOMBRE}]" --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids "$ID"
IP=$(aws ec2 describe-instances --instance-ids "$ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "5/5 Alarma de CPU en CloudWatch…"
aws cloudwatch put-metric-alarm --alarm-name "$NOMBRE-cpu-alta" --namespace AWS/EC2 --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value="$ID" --statistic Average --period 60 --evaluation-periods 3 --threshold 80 --comparison-operator GreaterThanThreshold

cat > infra/.salida/estado.env <<OUT
INSTANCIA=$ID
IP=$IP
API=http://$IP
WEB=http://$IP:3000
API_KEYS=$ML_API_KEYS
API_KEY=${ML_API_KEYS%%,*}
OUT
echo
echo "Instancia $ID · http://$IP/api/v1/ml/dashboard  (la pila tarda ~10 min en construir las imágenes)"
echo "Frontend:      http://$IP:3000  (/armar/asistente, /mis-pc, /observabilidad)"
echo "Verificar:     bash EP3_ITY1102/infra/verificar_defensa.sh --esperar http://$IP http://$IP:3000"
echo "Docs Swagger:  http://$IP/docs      Llave de API: ${ML_API_KEYS%%,*}  (+ 39 más; también en infra/.salida/estado.env, ignorado por git)"
