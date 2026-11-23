#!/usr/bin/env bash
# Intenta crear el modelo en SageMaker y deja el resultado como evidencia. En AWS Academy suele fallar por IAM
# (no existe LabRole y no se pueden crear roles); el despliegue efectivo es el contenedor en EC2 (desplegar.sh), que
# habla el mismo contrato (/ping, /invocations) que un endpoint de SageMaker.
set -uo pipefail
export AWS_PAGER="" AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
CUENTA=$(aws sts get-caller-identity --query Account --output text)
SALIDA="$(dirname "$0")/../evidencia/sagemaker-intento.txt"; mkdir -p "$(dirname "$SALIDA")"
{
  echo "== $(date -u +%FT%TZ) · cuenta $CUENTA"
  echo "-- roles utilizables por SageMaker (confianza sagemaker.amazonaws.com):"
  aws iam list-roles --query "Roles[?contains(to_string(AssumeRolePolicyDocument),'sagemaker.amazonaws.com')].RoleName" --output text
  echo "-- create-model con el único rol disponible (myS3Role):"
  aws sagemaker create-model --model-name todobarato-match --execution-role-arn "arn:aws:iam::$CUENTA:role/myS3Role" \
    --primary-container "Image=683313688378.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3" 2>&1
  echo "-- cuotas de endpoints ml.m5.large:"
  aws service-quotas list-service-quotas --service-code sagemaker --query "Quotas[?QuotaName=='ml.m5.large for endpoint usage'].[QuotaName,Value]" --output text
  # Simulación de IAM: pregunta a AWS qué permite el rol de esta sesión, sin crear nada.
  ROL=$(aws sts get-caller-identity --query Arn --output text | sed -E 's#^arn:aws:sts::([0-9]+):assumed-role/([^/]+)/.*#arn:aws:iam::\1:role/\2#')
  echo "-- permisos del rol $ROL (simulación de IAM; allowed = permitido, implicitDeny/explicitDeny = denegado):"
  aws iam simulate-principal-policy --policy-source-arn "$ROL" --action-names \
    sagemaker:CreateModel sagemaker:CreateEndpointConfig sagemaker:CreateEndpoint sagemaker:InvokeEndpoint \
    iam:PassRole iam:CreateRole ecr:CreateRepository application-autoscaling:RegisterScalableTarget \
    --query 'EvaluationResults[].[EvalActionName,EvalDecision]' --output text | tee "$SALIDA.sim"
  if grep -qE "sagemaker:Create(Model|Endpoint)[[:space:]]+allowed" "$SALIDA.sim" && grep -qE "iam:PassRole[[:space:]]+allowed" "$SALIDA.sim"; then
    echo "VEREDICTO: este laboratorio SÍ permite desplegar en SageMaker."
  else
    echo "VEREDICTO: este laboratorio NO permite desplegar en SageMaker (faltan CreateModel/CreateEndpoint o PassRole)."
  fi
  rm -f "$SALIDA.sim"
  echo
} | tee -a "$SALIDA"
