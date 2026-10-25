# Variables y funciones compartidas por desplegar.sh, destruir.sh y estado.sh.
# Cuenta: AWS Academy (rol voclabs). Sin ECS/ECR/SQS/Secrets Manager/IAM: se usa EC2 + ASG + ALB + RDS + S3 + SNS + EventBridge.
set -euo pipefail

AWS=${AWS:-$HOME/.local/bin/aws}
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
REGION=$AWS_DEFAULT_REGION
P=tb-ep2                                   # prefijo de todos los recursos
ETIQUETA="Key=Proyecto,Value=$P"
INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "$INFRA/../.." && pwd)"
SALIDA="$INFRA/.salida"; mkdir -p "$SALIDA"; chmod 700 "$SALIDA"
ESTADO="$SALIDA/estado.env"; touch "$ESTADO"; chmod 600 "$ESTADO"

CUENTA=$($AWS sts get-caller-identity --query Account --output text)
BUCKET="$P-artefactos-$CUENTA"
ZONAS=(us-east-1a us-east-1b)              # dos zonas de disponibilidad
TIPO_APP=t3.small                          # 2 vCPU / 2 GiB (la cuenta permite hasta t3.medium)
TIPO_WORKER=t3.small
CLASE_RDS=db.t4g.micro
PERFIL_EC2=myS3Role                        # único perfil disponible: s3:* (lee imágenes y configuración)

log() { printf '\033[1;32m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
aviso() { printf '\033[1;33m[aviso]\033[0m %s\n' "$*"; }
guardar() { grep -v "^$1=" "$ESTADO" > "$ESTADO.tmp" || true; echo "$1=$2" >> "$ESTADO.tmp"; mv "$ESTADO.tmp" "$ESTADO"; chmod 600 "$ESTADO"; }
# shellcheck disable=SC1090
cargar() { source "$ESTADO"; }
leer_env() { grep -E "^$1=" "$RAIZ/.env" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }

VPC=$($AWS ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBREDES=()
for z in "${ZONAS[@]}"; do
  SUBREDES+=("$($AWS ec2 describe-subnets --filters Name=vpc-id,Values="$VPC" Name=availability-zone,Values="$z" Name=default-for-az,Values=true --query 'Subnets[0].SubnetId' --output text)")
done
