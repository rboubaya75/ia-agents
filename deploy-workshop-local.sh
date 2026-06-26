#!/bin/bash
# deploy-workshop.sh - Complete WildRydes Workshop Deployment
#
# This script orchestrates the complete deployment of the WildRydes workshop:
#   1. Deploys AgentCore resources (Gateway, Memory, Runtime, Lambda)
#   2. Deploys frontend application (React app to S3/CloudFront)
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - CloudFormation stack deployed (combined-infrastructure.yaml)
#   - Python 3.x with required packages (boto3, bedrock-agentcore, etc.)
#   - Node.js and npm installed
#
# Usage:
#   ./deploy-workshop.sh                           # Uses default stack name
#   STACK_NAME=MyStack ./deploy-workshop.sh        # Uses custom stack name

echo "🦄 WildRydes Complete Workshop Deployment"
echo "=========================================="
echo ""

# Configuration
STACK_NAME="${STACK_NAME:-combined-infrastructure}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get AWS region - try multiple methods
# Method 1: Check environment variables first
AWS_REGION="${AWS_REGION:-$AWS_DEFAULT_REGION}"

# Method 2: Try IMDSv2 (requires token)
if [ -z "$AWS_REGION" ]; then
    TOKEN=$(curl -s --connect-timeout 2 -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null || echo "")
    if [ -n "$TOKEN" ]; then
        AWS_REGION=$(curl -s --connect-timeout 2 -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "")
    fi
fi

# Method 3: Try IMDSv1 (fallback)
if [ -z "$AWS_REGION" ]; then
    AWS_REGION=$(curl -s --connect-timeout 2 http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "")
fi

# Method 4: Try AWS CLI config
if [ -z "$AWS_REGION" ]; then
    AWS_REGION=$(aws configure get region 2>/dev/null || echo "")
fi

# Method 4: Default to us-east-1
if [ -z "$AWS_REGION" ]; then
    AWS_REGION="us-east-1"
fi

# Set AWS region environment variables
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_REGION="$AWS_REGION"

# Enable exit on error after initial setup
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC}  $1"
}

print_info() {
    echo -e "${BLUE}ℹ️${NC}  $1"
}

print_section() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
    echo ""
}

# Check prerequisites
print_section "Checking Prerequisites"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed"
    echo "Please install AWS CLI: https://aws.amazon.com/cli/"
    exit 1
fi
print_status "AWS CLI installed"

# Check AWS credentials (with region set)
print_info "Checking AWS credentials..."
print_info "AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:+set}"
print_info "AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:+set}"
print_info "AWS_SESSION_TOKEN: ${AWS_SESSION_TOKEN:+set}"
print_info "AWS_REGION: $AWS_REGION"
if aws sts get-caller-identity --region "$AWS_REGION" > /dev/null 2>&1; then
    print_status "AWS credentials configured"
    print_status "Using AWS region: $AWS_REGION"
else
    print_error "AWS credentials check failed or timed out"
    echo "Please ensure:"
    echo "  - EC2 instance has an IAM role attached, OR"
    echo "  - Run 'aws configure' to set credentials"
    echo ""
    echo "Debug: Try running manually: aws sts get-caller-identity --region $AWS_REGION"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    exit 1
fi
print_status "Python 3 installed"

# Install Python requirements
print_info "Installing Python requirements..."
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    if ! python3 -m pip install -q -r "$SCRIPT_DIR/requirements.txt"; then
        print_error "Failed to install Python requirements"
        echo "Please install manually: pip install -r $SCRIPT_DIR/requirements.txt"
        exit 1
    fi
    print_status "Python requirements installed"
else
    print_warning "requirements.txt not found, skipping Python package installation"
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed"
    echo "Please install Node.js: https://nodejs.org/"
    exit 1
fi
print_status "Node.js installed"

# Check npm
if ! command -v npm &> /dev/null; then
    print_error "npm is not installed"
    exit 1
fi
print_status "npm installed"

# Check CloudFormation stack exists
print_info "Checking CloudFormation stack: $STACK_NAME"
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
    print_error "CloudFormation stack '$STACK_NAME' not found"
    echo "Please deploy the CloudFormation stack first:"
    echo "  aws cloudformation deploy --template-file Cfn/combined-infrastructure.yaml --stack-name $STACK_NAME --capabilities CAPABILITY_NAMED_IAM"
    exit 1
fi
print_status "CloudFormation stack exists"

# ============================================
# PHASE 1: Deploy AgentCore Resources
# ============================================
print_section "Phase 1: Deploying AgentCore Resources"

cd "$SCRIPT_DIR/deploy-agentcore"

print_info "Running deploy-agentcore.py..."
print_info "This will create:"
print_info "  - AgentCore Gateway with Cognito authentication"
print_info "  - Memory with long-term strategy"
print_info "  - Lambda function for trip management"
print_info "  - AgentCore Runtime"
echo ""

if ! python3 deploy-agentcore.py; then
    print_error "AgentCore deployment failed"
    exit 1
fi

print_status "AgentCore resources deployed successfully"

# ============================================
# PHASE 2: Deploy Frontend Application
# ============================================
print_section "Phase 2: Deploying Frontend Application"

cd "$SCRIPT_DIR/frontend"

print_info "Running deploy-frontend.sh..."
print_info "This will:"
print_info "  - Retrieve configuration from CloudFormation and Secrets Manager"
print_info "  - Build the React application"
print_info "  - Deploy to S3"
print_info "  - Invalidate CloudFront cache"
echo ""

# Make sure the script is executable
chmod +x deploy-frontend.sh

# Export stack name for the frontend deployment script
export STACK_NAME="$STACK_NAME"

if ! ./deploy-frontend.sh; then
    print_error "Frontend deployment failed"
    exit 1
fi

print_status "Frontend deployed successfully"

# ============================================
# DEPLOYMENT COMPLETE
# ============================================
print_section "🎉 Workshop Deployment Complete!"

# Get CloudFront URL
CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
    --output text)

echo ""
echo "📦 Deployed Resources:"
echo "  🔐 Authentication: Cognito User Pool"
echo "  🗄️  Database: DynamoDB Table"
echo "  🤖 AgentCore: Gateway, Memory, Runtime"
echo "  🌐 Frontend: S3 + CloudFront"
echo ""

if [ -n "$CLOUDFRONT_URL" ]; then
    echo "🌐 Application URL: $CLOUDFRONT_URL"
else
    echo "🌐 Application URL: Check CloudFormation outputs"
fi

echo ""
echo "👤 Test User Credentials:"
echo "  User 1: webuser@example.com / WebPassword123!"
echo "  User 2: testuser@example.com / TestPassword123!"
echo ""
echo "📝 Configuration stored in:"
echo "  - deploy-agentcore/variables.txt"
echo "  - AWS Secrets Manager (wildrydes-secrets)"
echo ""
echo "🚀 You can now access the application and start testing!"
echo ""

cd "$SCRIPT_DIR"
