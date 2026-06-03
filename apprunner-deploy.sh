#!/usr/bin/env bash
# 一键把 AgentCore Studio 部署到 AWS App Runner（CloudFormation 编排）。
# 前置：Docker 运行中、aws CLI 已配置凭证、有 ECR/IAM/AppRunner/CloudFormation 权限。
#
# 为什么走 CloudFormation 而不是直接 aws iam create-role + aws apprunner create-service?
#   某些受管 AWS 账号（典型如 Isengard 个人非生产账号）有 SCP / RCP 拒绝
#   "由 IAM API 直接创建的角色被 AppRunner CreateService PassRole"，
#   错误形如：AccessDeniedException: Account ... is not authorized pass this role for operation CreateService。
#   这类策略放行经由 CloudFormation/CDK 创建的角色，因此本脚本统一走 CFN。
set -euo pipefail
REGION=${REGION:-us-east-1}
NAME=${NAME:-agentcore-studio}
STACK=${STACK:-$NAME}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com
IMG=$ECR/$NAME:latest
PASSWORD=${STUDIO_PASSWORD:-$(openssl rand -hex 12)}

echo ">> 1/4 ECR 仓库"
aws ecr describe-repositories --repository-names $NAME --region $REGION >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name $NAME --region $REGION >/dev/null
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR

echo ">> 2/4 构建并推送镜像 (linux/amd64)"
docker build --platform linux/amd64 -t $IMG .
docker push $IMG

echo ">> 3/4 CloudFormation 部署 (IAM roles + AppRunner service)"
TEMPLATE=$(dirname "$0")/apprunner.cfn.yaml
PARAMS=$(mktemp)
cat > "$PARAMS" <<EOF
[
  {"ParameterKey":"ServiceName","ParameterValue":"$NAME"},
  {"ParameterKey":"ImageUri","ParameterValue":"$IMG"},
  {"ParameterKey":"StudioPassword","ParameterValue":"$PASSWORD"}
]
EOF
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file "$TEMPLATE" \
  --region "$REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "file://$PARAMS"
rm -f "$PARAMS"

echo ">> 4/4 服务 URL"
URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceUrl'].OutputValue" --output text)
echo "URL:      $URL"
echo "用户名:    任意"
echo "密码:     $PASSWORD"
echo
echo "销毁命令： aws cloudformation delete-stack --stack-name $STACK --region $REGION"
echo "         aws ecr delete-repository --repository-name $NAME --region $REGION --force"
