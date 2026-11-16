#!/usr/bin/env bash
# Despliega la pila en AWS Academy: S3 (código) + EC2 t3.medium con Docker Compose + alarma de CloudWatch.
# Requisitos: credenciales del lab en el entorno (AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN). Cuesta ~USD 0,05/h: usar destruir.sh al terminar.
set -euo pipefail
cd "$(dirname "$0")/../.."          # EP3_ITY1102
RAIZ=$(cd .. && pwd)
REGION=${AWS_DEFAULT_REGION:-us-east-1}; export AWS_DEFAULT_REGION=$REGION AWS_PAGER=""
CUENTA=$(aws sts get-caller-identity --query Account --output text)
BUCKET=todobarato-ep3-$CUENTA
NOMBRE=todobarato-ep3
ML_API_KEYS=${ML_API_KEYS:-$(openssl rand -hex 12)}
mkdir -p infra/.salida

echo "1/5 Empaquetando el código (git archive + modelo + datos)…"
git -C "$RAIZ" archive --format=tar.gz -o "$PWD/infra/.salida/fuente.tgz" HEAD app ml alembic alembic.ini pyproject.toml README.md Dockerfile EP3_ITY1102/modelo EP3_ITY1102/infra/docker-compose.aws.yml

echo "2/5 Subiendo a s3://$BUCKET…"
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || aws s3 mb "s3://$BUCKET"
aws s3 cp infra/.salida/fuente.tgz "s3://$BUCKET/fuente.tgz"
[ -f "$RAIZ/ep3_data.db" ] && aws s3 cp "$RAIZ/ep3_data.db" "s3://$BUCKET/ep3.db"

echo "3/5 Grupo de seguridad (solo el puerto 80)…"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=$NOMBRE Name=vpc-id,Values="$VPC" --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name $NOMBRE --description "TodoBarato EP3" --vpc-id "$VPC" --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null
fi

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
docker compose -f docker-compose.aws.yml up -d --build
# carga el catálogo de ejemplo en el volumen de datos (si se subió)
aws s3 cp s3://$BUCKET/ep3.db /tmp/ep3.db || true
[ -f /tmp/ep3.db ] && docker run --rm -v infra_datos:/data -v /tmp:/src alpine cp /src/ep3.db /data/ep3.db || true
docker compose -f docker-compose.aws.yml restart backend worker
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
API_KEY=$ML_API_KEYS
OUT
echo
echo "Instancia $ID · http://$IP/api/v1/ml/dashboard  (la pila tarda ~6 min en construir las imágenes)"
echo "Docs Swagger:  http://$IP/docs      Llave de API: $ML_API_KEYS  (también en infra/.salida/estado.env, ignorado por git)"
