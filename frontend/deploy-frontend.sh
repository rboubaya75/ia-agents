#!/bin/bash
# Deploy WildRydes frontend static assets.
#
# This script deploys the React app to the pre-provisioned S3/CloudFront frontend.
# Runtime calls must go through the application API facade configured by VITE_API_BASE_URL.

set -euo pipefail

STACK_NAME="${STACK_NAME:-combined-infrastructure}"
API_BASE_URL="${API_BASE_URL:-${VITE_API_BASE_URL:-}}"

echo "WildRydes Frontend Deployment"
echo "============================"

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI is required."
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials are not configured."
  exit 1
fi

if [ -z "$API_BASE_URL" ]; then
  echo "API_BASE_URL or VITE_API_BASE_URL is required."
  exit 1
fi

if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" >/dev/null 2>&1; then
  echo "CloudFormation stack '$STACK_NAME' not found."
  exit 1
fi

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`FrontendBucketName`].OutputValue' \
  --output text)

CLOUDFRONT_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
  --output text)

USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolId`].OutputValue' \
  --output text)

CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolClientId`].OutputValue' \
  --output text)

REGION=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].StackId' \
  --output text | cut -d: -f4)

if [ -z "$BUCKET_NAME" ] || [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ] || [ -z "$REGION" ]; then
  echo "Required frontend or Cognito stack outputs are missing."
  exit 1
fi

cat > .env.production <<EOF
VITE_COGNITO_USER_POOL_ID=$USER_POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
VITE_COGNITO_REGION=$REGION
VITE_API_BASE_URL=$API_BASE_URL
EOF

npm install
npm run build
aws s3 sync dist/ "s3://$BUCKET_NAME" --delete

if [ -n "$CLOUDFRONT_ID" ] && [ "$CLOUDFRONT_ID" != "None" ]; then
  aws cloudfront create-invalidation --distribution-id "$CLOUDFRONT_ID" --paths "/*"
fi

echo "Frontend deployment completed."
