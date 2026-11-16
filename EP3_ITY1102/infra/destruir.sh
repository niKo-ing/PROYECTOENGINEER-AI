#!/usr/bin/env bash
# Borra TODO lo que creó desplegar.sh (instancia, alarma, grupo de seguridad y bucket).
set -uo pipefail
export AWS_PAGER="" AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
CUENTA=$(aws sts get-caller-identity --query Account --output text); NOMBRE=todobarato-ep3
IDS=$(aws ec2 describe-instances --filters Name=tag:Name,Values=$NOMBRE Name=instance-state-name,Values=pending,running,stopped --query 'Reservations[].Instances[].InstanceId' --output text)
[ -n "$IDS" ] && aws ec2 terminate-instances --instance-ids $IDS >/dev/null && aws ec2 wait instance-terminated --instance-ids $IDS
aws cloudwatch delete-alarms --alarm-names "$NOMBRE-cpu-alta" 2>/dev/null
aws ec2 delete-security-group --group-name $NOMBRE 2>/dev/null
aws s3 rb "s3://todobarato-ep3-$CUENTA" --force 2>/dev/null
echo "Listo: instancia, alarma, grupo de seguridad y bucket eliminados."
