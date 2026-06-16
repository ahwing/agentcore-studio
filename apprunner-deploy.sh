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

echo ">> 3/4 部署服务"
SVC_ARN=$(aws apprunner list-services --region "$REGION" \
  --query "ServiceSummaryList[?ServiceName=='$NAME'].ServiceArn" --output text 2>/dev/null || true)

if [ -n "$SVC_ARN" ] && [ "$SVC_ARN" != "None" ]; then
  # 服务已存在：直接触发滚动部署拉取新 latest 镜像（无需 CFN，URL 不变、旧版本服务到新版本就绪期间不中断）
  echo "   检测到已存在服务，触发滚动部署：$SVC_ARN"
  OP=$(aws apprunner start-deployment --service-arn "$SVC_ARN" --region "$REGION" --query OperationId --output text)
  echo "   OperationId: $OP，等待部署完成…"
  for i in $(seq 1 40); do
    ST=$(aws apprunner describe-service --service-arn "$SVC_ARN" --region "$REGION" --query "Service.Status" --output text)
    echo "   [$i] status=$ST"
    [ "$ST" = "RUNNING" ] && break
    sleep 15
  done
  URL=$(aws apprunner describe-service --service-arn "$SVC_ARN" --region "$REGION" --query "Service.ServiceUrl" --output text)
  NOTE="（更新现有服务，URL 不变）"
  PWLINE="密码:     （沿用现有服务设置，未改变；如需改密码走下方 CFN 首建或控制台）"
else
  # 首次创建：走 CloudFormation 编排（IAM roles + AppRunner service），规避受管账号的 PassRole SCP 限制
  echo "   未发现现有服务，使用 CloudFormation 首次创建"
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
  URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='ServiceUrl'].OutputValue" --output text)
  NOTE="（CloudFormation 首次创建完成）"
  PWLINE="密码:     $PASSWORD"
fi

echo ">> 4/4 完成 $NOTE"
echo "URL:      $URL"
echo "用户名:    任意"
echo "$PWLINE"
echo
echo "首建若失败提示角色已存在：说明账号里有同名孤儿角色 (agentcore-studio-instance / -ecr-access)，"
echo "  需先删除孤儿角色或改用本脚本的服务更新分支。"
echo "销毁命令： aws apprunner delete-service --service-arn <ARN> --region $REGION"
echo "         aws cloudformation delete-stack --stack-name $STACK --region $REGION  # 若曾用 CFN 首建"
echo "         aws ecr delete-repository --repository-name $NAME --region $REGION --force"
