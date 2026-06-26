#!/bin/bash
# deploy.sh - Deploy Wildrydes frontend to pre-provisioned AWS infrastructure
#
# This script automates the deployment of the Wildrydes React frontend to AWS.
# It retrieves configuration from CloudFormation and Secrets Manager, builds the
# application, and deploys it to S3 with CloudFront cache invalidation.
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - CloudFormation stack deployed (frontend.yaml → WildrydesFrontendStack)
#   - AgentCore resources deployed (deploy-agentcore/deploy-agentcore.py)
#   - AgentCore runtime deployed (deploy-agentcore/deploy-runtime.py)
#   - Node.js and npm installed
#
# Workshop Deployment Flow:
#   1. Deploy frontend.yaml CloudFormation stack (S3, CloudFront, Cognito)
#   2. Run deploy-agentcore/deploy-agentcore.py (Gateway, Memory, Secrets)
#   3. Run deploy-agentcore/deploy-runtime.py (AgentCore Runtime → Secrets Manager)
#   4. Run this script (frontend/deploy.sh) to deploy the React app
#
# Usage:
#   ./deploy.sh                           # Uses default stack name
#   STACK_NAME=MyStack ./deploy.sh        # Uses custom stack name
#
# The script will:
#   1. Retrieve S3 bucket, CloudFront, and Cognito config from CloudFormation
#   2. Retrieve AgentCore Runtime ARN from Secrets Manager (wildrydes-secrets)
#   3. Generate .env.production file with all configuration
#   4. Install dependencies and build the React application
#   5. Deploy built files to S3
#   6. Invalidate CloudFront cache for immediate updates

set -e

echo "🦄 Wildrydes Frontend Deployment"
echo "================================"
echo ""

# Configuration
STACK_NAME="${STACK_NAME:-combined-infrastructure}"

# Check AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ Error: AWS CLI is not installed"
    echo "Please install AWS CLI: https://aws.amazon.com/cli/"
    exit 1
fi

# Check AWS credentials are configured
echo "Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ Error: AWS credentials not configured"
    echo "Please run 'aws configure' or set AWS environment variables"
    exit 1
fi

echo "✅ AWS credentials configured"
echo ""

# Get CloudFormation stack outputs
echo "Fetching CloudFormation stack outputs from '$STACK_NAME'..."

# Check if stack exists
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
    echo "❌ Error: CloudFormation stack '$STACK_NAME' not found"
    echo "Please ensure the stack exists or set STACK_NAME environment variable"
    echo "Example: STACK_NAME=MyStackName ./deploy.sh"
    exit 1
fi

# Retrieve stack outputs
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

# Get region from stack location
REGION=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].StackId' \
    --output text | cut -d: -f4)

# Get AgentCore Runtime ARN from Secrets Manager
# The deploy-runtime.py script stores the runtime ARN in 'wildrydes-secrets'
SECRETS_NAME="wildrydes-secrets"

echo "Retrieving AgentCore Runtime ARN from Secrets Manager..."
if aws secretsmanager describe-secret --secret-id "$SECRETS_NAME" &> /dev/null; then
    SECRET_JSON=$(aws secretsmanager get-secret-value \
        --secret-id "$SECRETS_NAME" \
        --query 'SecretString' \
        --output text)
    
    # Extract RUNTIME_ARN from the JSON using jq if available, otherwise use grep
    if command -v jq &> /dev/null; then
        AGENT_ARN=$(echo "$SECRET_JSON" | jq -r '.RUNTIME_ARN // empty')
    else
        # Fallback to grep/sed if jq is not available
        AGENT_ARN=$(echo "$SECRET_JSON" | sed -n 's/.*"RUNTIME_ARN"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    fi
    
    if [ -n "$AGENT_ARN" ] && [ "$AGENT_ARN" != "null" ] && [ "$AGENT_ARN" != "" ]; then
        echo "✅ AgentCore Runtime ARN retrieved from Secrets Manager"
    else
        echo "⚠️  Warning: RUNTIME_ARN not found in Secrets Manager"
        echo "Please run deploy-agentcore/deploy-agentcore.py to deploy the AgentCore runtime"
        AGENT_ARN=""
    fi
else
    echo "⚠️  Warning: Secrets Manager secret '$SECRETS_NAME' not found"
    echo "Please run deploy-agentcore/deploy-agentcore.py to create the secret first"
    AGENT_ARN=""
fi

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
    --output text)

# Validate required outputs
if [ -z "$BUCKET_NAME" ]; then
    echo "❌ Error: Failed to retrieve FrontendBucketName from CloudFormation stack"
    echo "Please ensure the stack has the required outputs"
    exit 1
fi

if [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ]; then
    echo "❌ Error: Failed to retrieve Cognito configuration from CloudFormation stack"
    echo "Please ensure the stack has CognitoUserPoolId and CognitoUserPoolClientId outputs"
    exit 1
fi

if [ -z "$CLOUDFRONT_ID" ]; then
    echo "⚠️  Warning: CloudFront Distribution ID not found, skipping cache invalidation"
fi

# Validate region
if [ -z "$REGION" ]; then
    REGION=$(aws configure get region)
    if [ -z "$REGION" ]; then
        REGION="us-east-1"
        echo "⚠️  Warning: Could not determine region, defaulting to us-east-1"
    fi
fi

# Validate AgentCore ARN
if [ -z "$AGENT_ARN" ] || [ "$AGENT_ARN" = "PLACEHOLDER_AGENT_CORE_ARN" ]; then
    echo "⚠️  Warning: AgentCore ARN not configured in Secrets Manager"
    echo "The application will be deployed, but you need to update the AgentCore ARN"
    echo "in Secrets Manager: $SECRETS_NAME"
    echo ""
    read -p "Do you want to enter the AgentCore ARN now? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter AgentCore ARN (e.g., arn:aws:bedrock-agentcore:region:account:runtime/agentId): " AGENT_ARN
        if [ -z "$AGENT_ARN" ]; then
            echo "❌ Error: AgentCore ARN cannot be empty"
            exit 1
        fi
    else
        echo "⚠️  Proceeding with placeholder ARN. Update Secrets Manager before using the app."
        AGENT_ARN="arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/placeholder"
    fi
fi

echo "✅ Configuration retrieved from CloudFormation"
echo ""
echo "Configuration:"
echo "  Stack Name: $STACK_NAME"
echo "  S3 Bucket: $BUCKET_NAME"
echo "  CloudFront ID: ${CLOUDFRONT_ID:-N/A}"
echo "  User Pool ID: $USER_POOL_ID"
echo "  Client ID: $CLIENT_ID"
echo "  Region: $REGION"
echo "  AgentCore ARN: $AGENT_ARN"
echo ""

# Create .env.production file with configuration
echo "Creating environment configuration (.env.production)..."
cat > .env.production << EOF
VITE_COGNITO_USER_POOL_ID=$USER_POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
VITE_COGNITO_REGION=$REGION
VITE_AGENT_ARN=$AGENT_ARN
EOF

echo "✅ Environment configuration created"
echo ""

# Install dependencies
echo "Installing dependencies..."
if ! npm install; then
    echo "❌ Error: Failed to install dependencies"
    exit 1
fi

echo "✅ Dependencies installed"
echo ""

# Build the application
echo "Building application..."
if ! npm run build; then
    echo "❌ Error: Failed to build application"
    exit 1
fi

echo "✅ Application built successfully"
echo ""

# Check if dist directory exists
if [ ! -d "dist" ]; then
    echo "❌ Error: Build output directory 'dist' not found"
    exit 1
fi

# Deploy to S3
echo "Deploying to S3 bucket: $BUCKET_NAME..."
if ! aws s3 sync dist/ "s3://$BUCKET_NAME" --delete; then
    echo "❌ Error: Failed to sync files to S3"
    exit 1
fi

echo "✅ Files deployed to S3"
echo ""

# Invalidate CloudFront cache (if CloudFront ID is available)
if [ -n "$CLOUDFRONT_ID" ]; then
    echo "Invalidating CloudFront cache..."
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
        --distribution-id "$CLOUDFRONT_ID" \
        --paths "/*" \
        --query 'Invalidation.Id' \
        --output text)
    
    if [ -n "$INVALIDATION_ID" ]; then
        echo "✅ CloudFront cache invalidation created (ID: $INVALIDATION_ID)"
    else
        echo "⚠️  Warning: Failed to create CloudFront invalidation"
    fi
else
    echo "⚠️  Skipping CloudFront cache invalidation (no distribution ID)"
fi

echo ""
echo "================================"
echo "✅ Deployment complete!"
echo "================================"
echo ""

if [ -n "$CLOUDFRONT_URL" ]; then
    # CloudFormation output already includes https://, so don't add it again
    if [[ "$CLOUDFRONT_URL" == https://* ]]; then
        echo "🌐 Application URL: $CLOUDFRONT_URL"
    else
        echo "🌐 Application URL: https://$CLOUDFRONT_URL"
    fi
else
    echo "🌐 Application URL: Check CloudFormation stack outputs for CloudFrontURL"
fi

echo ""
echo "Configuration Summary:"
echo "  User Pool ID: $USER_POOL_ID"
echo "  Client ID: $CLIENT_ID"
echo "  Region: $REGION"
echo "  AgentCore ARN: $AGENT_ARN"
echo ""
echo "You can now access the application and log in with your Cognito credentials."
echo ""
