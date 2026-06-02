#!/usr/bin/env bash
# 一键把 AgentCore Studio 部署到 AWS App Runner（镜像方式）。
# 前置：Docker 运行中、aws CLI 已配置凭证、有 ECR/IAM/AppRunner 权限。
set -euo pipefail
REGION=${REGION:-us-east-1}
NAME=agentcore-studio
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com
IMG=$ECR/$NAME:latest
PASSWORD=${STUDIO_PASSWORD:-$(openssl rand -hex 12)}

echo ">> 1/5 ECR 仓库"
aws ecr describe-repositories --repository-names $NAME --region $REGION >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name $NAME --region $REGION >/dev/null
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR

echo ">> 2/5 构建并推送镜像 (linux/amd64)"
docker build --platform linux/amd64 -t $IMG .
docker push $IMG

echo ">> 3/5 IAM 角色"
cat > /tmp/trust-tasks.json <<'J'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}
J
cat > /tmp/trust-build.json <<'J'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}
J
# 实例角色权限：调用 + 部署 AgentCore（较广，建议放独立演示账号；如只做 invoke 验证可删掉 DeployInfra/IamForDeploy 两段）
cat > /tmp/studio-policy.json <<'J'
{"Version":"2012-10-17","Statement":[
 {"Sid":"AgentCore","Effect":"Allow","Action":["bedrock-agentcore:*","bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],"Resource":"*"},
 {"Sid":"DeployInfra","Effect":"Allow","Action":["ecr:*","s3:*","codebuild:*","logs:*","cloudformation:*","cloudwatch:*","xray:*"],"Resource":"*"},
 {"Sid":"IamForDeploy","Effect":"Allow","Action":["iam:CreateRole","iam:DeleteRole","iam:AttachRolePolicy","iam:DetachRolePolicy","iam:PutRolePolicy","iam:DeleteRolePolicy","iam:GetRole","iam:PassRole","iam:CreatePolicy","iam:TagRole","iam:ListRolePolicies","iam:ListAttachedRolePolicies"],"Resource":"*"}
]}
J
aws iam create-role --role-name $NAME-instance --assume-role-policy-document file:///tmp/trust-tasks.json >/dev/null 2>&1 || true
aws iam put-role-policy --role-name $NAME-instance --policy-name studio --policy-document file:///tmp/studio-policy.json
aws iam create-role --role-name $NAME-ecr-access --assume-role-policy-document file:///tmp/trust-build.json >/dev/null 2>&1 || true
aws iam attach-role-policy --role-name $NAME-ecr-access --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
INSTANCE_ARN=arn:aws:iam::$ACCOUNT:role/$NAME-instance
ACCESS_ARN=arn:aws:iam::$ACCOUNT:role/$NAME-ecr-access
sleep 12  # 等 IAM 传播

echo ">> 4/5 创建 App Runner 服务"
aws apprunner create-service --service-name $NAME --region $REGION \
 --source-configuration "{\"ImageRepository\":{\"ImageIdentifier\":\"$IMG\",\"ImageRepositoryType\":\"ECR\",\"ImageConfiguration\":{\"Port\":\"8080\",\"RuntimeEnvironmentVariables\":{\"STUDIO_PASSWORD\":\"$PASSWORD\"}}},\"AuthenticationConfiguration\":{\"AccessRoleArn\":\"$ACCESS_ARN\"},\"AutoDeploymentsEnabled\":false}" \
 --instance-configuration "{\"Cpu\":\"1 vCPU\",\"Memory\":\"2 GB\",\"InstanceRoleArn\":\"$INSTANCE_ARN\"}" \
 --health-check-configuration "{\"Protocol\":\"TCP\",\"Interval\":10,\"Timeout\":5,\"HealthyThreshold\":1,\"UnhealthyThreshold\":5}" >/dev/null

echo ">> 5/5 服务 URL（首次构建约 3-5 分钟就绪）"
aws apprunner list-services --region $REGION --query "ServiceSummaryList[?ServiceName=='$NAME'].ServiceUrl" --output text
echo "登录用户名: 任意    密码: $PASSWORD"
