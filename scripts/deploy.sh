#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Keep non-interactive deployment output in the terminal instead of opening
# the AWS CLI's `less` pager and stopping at an `(END)` prompt.
export AWS_PAGER=""

# JetBrains integrated terminals do not always inherit Docker Desktop's CLI path.
if ! command -v docker >/dev/null; then
  for docker_dir in "$HOME/.docker/bin" "/Applications/Docker.app/Contents/Resources/bin"; do
    if [[ -x "$docker_dir/docker" ]]; then
      export PATH="$docker_dir:$PATH"
      break
    fi
  done
fi
for command in aws uv docker; do
  if ! command -v "$command" >/dev/null; then
    echo "Missing required command: $command" >&2
    exit 127
  fi
done

# Explicit variables win. Otherwise use the active AWS profile's region and the
# verified Nova Lite default, so the common `bash scripts/deploy.sh` path works.
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
if [[ -z "$AWS_REGION" ]]; then
  echo "No AWS region is configured. Run: aws configure set region us-east-1" >&2
  exit 2
fi
MODEL_ID="${MODEL_ID:-amazon.nova-lite-v1:0}"
MODEL_ARN="${MODEL_ARN:-arn:aws:bedrock:$AWS_REGION::foundation-model/$MODEL_ID}"
STACK="${STACK:-support-agent}"
STAGE="${STAGE:-test}"
BUILD_ID="$(date -u +%Y%m%dT%H%M%SZ)"
export AWS_DEFAULT_REGION="$AWS_REGION"
echo "Deploying stack $STACK to $AWS_REGION with model $MODEL_ID (stage: $STAGE)"
aws sts get-caller-identity --query Arn --output text
aws bedrock get-foundation-model --model-identifier "$MODEL_ID" \
  --query 'modelDetails.modelLifecycle.status' --output text >/dev/null
if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but its daemon is unavailable. Start Docker Desktop." >&2
  exit 1
fi

# A failed CREATE stack cannot be updated. Stop before rebuilding and pushing an
# image, and leave deletion/recovery as an explicit operator action.
existing_status="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || true)"
if [[ "$existing_status" == "ROLLBACK_COMPLETE" || "$existing_status" == "ROLLBACK_FAILED" ]]; then
  echo "Stack $STACK is $existing_status and must be deleted before redeployment." >&2
  echo "After fixing IAM, run:" >&2
  echo "  aws cloudformation delete-stack --stack-name $STACK" >&2
  echo "  aws cloudformation wait stack-delete-complete --stack-name $STACK" >&2
  exit 3
fi

# CloudFormation needs this read action while stabilizing a newly created table.
# ResourceNotFoundException proves authorization; AccessDenied fails before build.
ddb_probe="$(aws dynamodb describe-table --table-name "$STACK-permission-probe" 2>&1 || true)"
if [[ "$ddb_probe" == *"AccessDenied"* || "$ddb_probe" == *"not authorized"* ]]; then
  echo "Deployment identity lacks dynamodb:DescribeTable for $STACK-* tables." >&2
  echo "Ask an administrator to apply infra/deployer-policy.template.json." >&2
  exit 4
fi
uv sync --frozen --extra dev
uv run --frozen python infra/generate.py
uv run --frozen cfn-lint infra/stack.json infra/bootstrap.json
uv run --frozen pytest -q

aws cloudformation deploy --stack-name "$STACK-artifacts" --template-file infra/bootstrap.json
output() {
  aws cloudformation describe-stacks --stack-name "$STACK-artifacts" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}
BUCKET="$(output Bucket)"
REPOSITORY="$(output RepositoryName)"
REPO_URI="$(output RepositoryUri)"
REPO_ARN="$(output RepositoryArn)"
LAMBDA_DIR="build/lambda-$BUILD_ID"
mkdir -p "$LAMBDA_DIR"
uv pip install --target "$LAMBDA_DIR" --python-platform aarch64-manylinux2014 \
  --python-version 3.12 --only-binary :all: -r infra/lambda-requirements.lock.txt
cp -R src/support_agent "$LAMBDA_DIR/"
uv run --frozen python -m zipfile -c "build/tools-$BUILD_ID.zip" "$LAMBDA_DIR"/*
aws s3 cp "build/tools-$BUILD_ID.zip" "s3://$BUCKET/tools-$BUILD_ID.zip"

aws ecr get-login-password | docker login --username AWS --password-stdin "${REPO_URI%%/*}"
docker buildx build --platform linux/arm64 --provenance=false --push -t "$REPO_URI:$BUILD_ID" .
DIGEST="$(aws ecr describe-images --repository-name "$REPOSITORY" --image-ids "imageTag=$BUILD_ID" \
  --query 'imageDetails[0].imageDigest' --output text)"
aws cloudformation deploy --stack-name "$STACK" --template-file infra/stack.json \
  --capabilities CAPABILITY_IAM --parameter-overrides \
  "CodeBucket=$BUCKET" "CodeKey=tools-$BUILD_ID.zip" "RuntimeImage=$REPO_URI@$DIGEST" \
  "RepositoryArn=$REPO_ARN" "ModelId=$MODEL_ID" "ModelArn=$MODEL_ARN" "Stage=$STAGE" "FaultMode=none"
aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].Outputs'
