#!/bin/bash
# cleanup-workshop.sh - Clean up WildRydes Workshop Resources
#
# This script deletes all resources created by deploy-agentcore.py:
#   - AgentCore Gateway and Gateway Targets
#   - AgentCore Memory
#   - AgentCore Runtime
#   - Lambda functions
#   - IAM roles
#   - Cognito User Pool (Gateway)
#   - Secrets Manager secrets
#   - ECR repositories
#
# NOTE: This script does NOT delete CloudFormation stacks.
#       To delete CloudFormation stacks, run:
#       aws cloudformation delete-stack --stack-name <stack-name>
#
# Prerequisites:
#   - AWS CLI installed and configured
#   - Python 3.x with boto3
#   - Appropriate AWS permissions
#
# Usage:
#   ./cleanup-workshop.sh                    # Interactive mode with confirmations
#   ./cleanup-workshop.sh --force            # Skip confirmations (use with caution)

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE_MODE=false

# Parse arguments
if [ "$1" = "--force" ]; then
    FORCE_MODE=true
fi

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

# Function to confirm action
confirm_action() {
    if [ "$FORCE_MODE" = true ]; then
        return 0
    fi
    
    local message="$1"
    read -p "$message (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        return 1
    fi
    return 0
}

print_section "🧹 WildRydes Workshop Cleanup"

echo "This script will delete the following resources:"
echo "  🔐 AgentCore Gateway and Targets"
echo "  🧠 AgentCore Memory"
echo "  🤖 AgentCore Runtime"
echo "  λ  Lambda functions"
echo "  👤 IAM roles"
echo "  🔑 Cognito User Pool (Gateway)"
echo "  🔒 Secrets Manager secrets"
echo "  📦 ECR repositories"
echo ""
print_warning "CloudFormation stacks will NOT be deleted"
print_warning "This action cannot be undone!"
echo ""

if ! confirm_action "Do you want to proceed with cleanup?"; then
    echo "Cleanup cancelled"
    exit 0
fi

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured"
    exit 1
fi

# Get AWS region
REGION=$(aws configure get region)
if [ -z "$REGION" ]; then
    REGION="us-east-1"
    print_warning "Could not determine region, defaulting to us-east-1"
fi

print_info "Using AWS region: $REGION"

# Read variables from variables.txt if it exists
VARIABLES_FILE="$SCRIPT_DIR/deploy-agentcore/variables.txt"
GATEWAY_ID=""
MEMORY_ID=""
RUNTIME_ARN=""
RUNTIME_ID=""
USER_POOL_ID=""
RANDOM_INDICATOR=""

if [ -f "$VARIABLES_FILE" ]; then
    print_info "Reading configuration from variables.txt..."
    
    # Parse variables.txt
    while IFS='=' read -r key value; do
        # Remove whitespace and quotes
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs | tr -d "'\"")
        
        case "$key" in
            GATEWAY_ID) GATEWAY_ID="$value" ;;
            MEMORY_ID) MEMORY_ID="$value" ;;
            RUNTIME_ARN) RUNTIME_ARN="$value" ;;
            RUNTIME_ID) RUNTIME_ID="$value" ;;
            USER_POOL_ID) USER_POOL_ID="$value" ;;
            RANDOM_INDICATOR) RANDOM_INDICATOR="$value" ;;
        esac
    done < "$VARIABLES_FILE"
    
    print_status "Configuration loaded"
else
    print_warning "variables.txt not found, will attempt to discover resources"
fi

# ============================================
# Delete AgentCore Gateway and Targets
# ============================================
print_section "Deleting AgentCore Gateway"

if [ -n "$GATEWAY_ID" ]; then
    print_info "Deleting gateway targets for: $GATEWAY_ID"
    
    # List and delete all gateway targets
    TARGETS=$(aws bedrock-agentcore-control list-gateway-targets \
        --gateway-identifier "$GATEWAY_ID" \
        --region "$REGION" \
        --query 'gatewayTargets[].targetId' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$TARGETS" ]; then
        for TARGET_ID in $TARGETS; do
            print_info "Deleting gateway target: $TARGET_ID"
            aws bedrock-agentcore-control delete-gateway-target \
                --gateway-identifier "$GATEWAY_ID" \
                --target-identifier "$TARGET_ID" \
                --region "$REGION" 2>/dev/null || print_warning "Failed to delete target $TARGET_ID"
        done
        print_status "Gateway targets deleted"
    else
        print_info "No gateway targets found"
    fi
    
    # Delete the gateway
    print_info "Deleting gateway: $GATEWAY_ID"
    if aws bedrock-agentcore-control delete-gateway \
        --gateway-identifier "$GATEWAY_ID" \
        --region "$REGION" 2>/dev/null; then
        print_status "Gateway deleted"
    else
        print_warning "Failed to delete gateway (may not exist)"
    fi
else
    print_warning "Gateway ID not found, skipping gateway deletion"
fi

# ============================================
# Delete AgentCore Memory
# ============================================
print_section "Deleting AgentCore Memory"

if [ -n "$MEMORY_ID" ]; then
    print_info "Deleting memory: $MEMORY_ID"
    
    # Use Python to delete memory with proper waiting
    python3 << EOF
import boto3
from botocore.exceptions import ClientError

try:
    from bedrock_agentcore.memory import MemoryClient
    
    client = MemoryClient(region_name='$REGION')
    client.delete_memory_and_wait(memory_id='$MEMORY_ID', max_wait=300, poll_interval=10)
    print("Memory deleted successfully")
except ImportError:
    print("bedrock_agentcore not installed, using boto3 directly")
    client = boto3.client('bedrock-agentcore-memory', region_name='$REGION')
    try:
        client.delete_memory(memoryId='$MEMORY_ID')
        print("Memory deletion initiated")
    except ClientError as e:
        print(f"Failed to delete memory: {e}")
except ClientError as e:
    if 'ResourceNotFoundException' in str(e):
        print("Memory not found (may already be deleted)")
    else:
        print(f"Failed to delete memory: {e}")
except Exception as e:
    print(f"Error: {e}")
EOF
    
    print_status "Memory deletion completed"
else
    print_warning "Memory ID not found, attempting to discover memories..."
    
    # Try to find and delete memories with wildrydes prefix
    MEMORIES=$(aws bedrock-agentcore-memory list-memories \
        --region "$REGION" \
        --query 'memories[?starts_with(name, `wildrydes_memory_`)].id' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$MEMORIES" ]; then
        for MEM_ID in $MEMORIES; do
            print_info "Deleting discovered memory: $MEM_ID"
            aws bedrock-agentcore-memory delete-memory \
                --memory-id "$MEM_ID" \
                --region "$REGION" 2>/dev/null || print_warning "Failed to delete memory $MEM_ID"
        done
    else
        print_info "No memories found"
    fi
fi

# ============================================
# Delete AgentCore Runtime
# ============================================
print_section "Deleting AgentCore Runtime"

if [ -n "$RUNTIME_ID" ]; then
    print_info "Deleting runtime: $RUNTIME_ID"
    
    if aws bedrock-agentcore delete-agent \
        --agent-id "$RUNTIME_ID" \
        --region "$REGION" 2>/dev/null; then
        print_status "Runtime deleted"
    else
        print_warning "Failed to delete runtime (may not exist)"
    fi
else
    print_warning "Runtime ID not found, attempting to discover runtimes..."
    
    # Try to find and delete runtimes with origami prefix
    RUNTIMES=$(aws bedrock-agentcore list-agents \
        --region "$REGION" \
        --query 'agents[?starts_with(agentName, `origami_expeditions`)].agentId' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$RUNTIMES" ]; then
        for RUNTIME in $RUNTIMES; do
            print_info "Deleting discovered runtime: $RUNTIME"
            aws bedrock-agentcore delete-agent \
                --agent-id "$RUNTIME" \
                --region "$REGION" 2>/dev/null || print_warning "Failed to delete runtime $RUNTIME"
        done
    else
        print_info "No runtimes found"
    fi
fi

# ============================================
# Delete Lambda Functions
# ============================================
print_section "Deleting Lambda Functions"

# Delete Lambda functions with wildrydes prefix
LAMBDA_FUNCTIONS=$(aws lambda list-functions \
    --region "$REGION" \
    --query 'Functions[?starts_with(FunctionName, `wildrydes`)].FunctionName' \
    --output text 2>/dev/null || echo "")

if [ -n "$LAMBDA_FUNCTIONS" ]; then
    for FUNC in $LAMBDA_FUNCTIONS; do
        print_info "Deleting Lambda function: $FUNC"
        if aws lambda delete-function \
            --function-name "$FUNC" \
            --region "$REGION" 2>/dev/null; then
            print_status "Deleted Lambda function: $FUNC"
        else
            print_warning "Failed to delete Lambda function: $FUNC"
        fi
    done
else
    print_info "No Lambda functions found"
fi

# ============================================
# Delete IAM Roles
# ============================================
print_section "Deleting IAM Roles"

# Delete IAM roles with wildrydes and origami prefix
IAM_ROLES=$(aws iam list-roles \
    --query 'Roles[?starts_with(RoleName, `wildrydes`) || starts_with(RoleName, `origami`)].RoleName' \
    --output text 2>/dev/null || echo "")

if [ -n "$IAM_ROLES" ]; then
    for ROLE in $IAM_ROLES; do
        print_info "Deleting IAM role: $ROLE"
        
        # Detach managed policies
        ATTACHED_POLICIES=$(aws iam list-attached-role-policies \
            --role-name "$ROLE" \
            --query 'AttachedPolicies[].PolicyArn' \
            --output text 2>/dev/null || echo "")
        
        for POLICY_ARN in $ATTACHED_POLICIES; do
            aws iam detach-role-policy \
                --role-name "$ROLE" \
                --policy-arn "$POLICY_ARN" 2>/dev/null || true
        done
        
        # Delete inline policies
        INLINE_POLICIES=$(aws iam list-role-policies \
            --role-name "$ROLE" \
            --query 'PolicyNames[]' \
            --output text 2>/dev/null || echo "")
        
        for POLICY_NAME in $INLINE_POLICIES; do
            aws iam delete-role-policy \
                --role-name "$ROLE" \
                --policy-name "$POLICY_NAME" 2>/dev/null || true
        done
        
        # Delete the role
        if aws iam delete-role --role-name "$ROLE" 2>/dev/null; then
            print_status "Deleted IAM role: $ROLE"
        else
            print_warning "Failed to delete IAM role: $ROLE"
        fi
    done
else
    print_info "No IAM roles found"
fi

# ============================================
# Delete Cognito User Pool (Gateway)
# ============================================
print_section "Deleting Cognito User Pool (Gateway)"

if [ -n "$USER_POOL_ID" ]; then
    print_info "Deleting Cognito user pool: $USER_POOL_ID"
    
    # Delete app clients first
    CLIENTS=$(aws cognito-idp list-user-pool-clients \
        --user-pool-id "$USER_POOL_ID" \
        --region "$REGION" \
        --query 'UserPoolClients[].ClientId' \
        --output text 2>/dev/null || echo "")
    
    for CLIENT_ID in $CLIENTS; do
        aws cognito-idp delete-user-pool-client \
            --user-pool-id "$USER_POOL_ID" \
            --client-id "$CLIENT_ID" \
            --region "$REGION" 2>/dev/null || true
    done
    
    # Delete resource servers
    RESOURCE_SERVERS=$(aws cognito-idp list-resource-servers \
        --user-pool-id "$USER_POOL_ID" \
        --region "$REGION" \
        --query 'ResourceServers[].Identifier' \
        --output text 2>/dev/null || echo "")
    
    for RS_ID in $RESOURCE_SERVERS; do
        aws cognito-idp delete-resource-server \
            --user-pool-id "$USER_POOL_ID" \
            --identifier "$RS_ID" \
            --region "$REGION" 2>/dev/null || true
    done
    
    # Delete the user pool
    if aws cognito-idp delete-user-pool \
        --user-pool-id "$USER_POOL_ID" \
        --region "$REGION" 2>/dev/null; then
        print_status "Cognito user pool deleted"
    else
        print_warning "Failed to delete Cognito user pool"
    fi
else
    print_warning "User Pool ID not found, attempting to discover user pools..."
    
    # Try to find and delete user pools with wildrydes prefix
    USER_POOLS=$(aws cognito-idp list-user-pools \
        --max-results 60 \
        --region "$REGION" \
        --query 'UserPools[?starts_with(Name, `wildrydes_gateway`)].Id' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$USER_POOLS" ]; then
        for POOL_ID in $USER_POOLS; do
            print_info "Deleting discovered user pool: $POOL_ID"
            aws cognito-idp delete-user-pool \
                --user-pool-id "$POOL_ID" \
                --region "$REGION" 2>/dev/null || print_warning "Failed to delete user pool $POOL_ID"
        done
    else
        print_info "No gateway user pools found"
    fi
fi

# ============================================
# Delete Secrets Manager Secrets
# ============================================
print_section "Deleting Secrets Manager Secrets"

print_info "Deleting secret: wildrydes-secrets"
if aws secretsmanager delete-secret \
    --secret-id "wildrydes-secrets" \
    --force-delete-without-recovery \
    --region "$REGION" 2>/dev/null; then
    print_status "Secret deleted: wildrydes-secrets"
else
    print_warning "Failed to delete secret (may not exist)"
fi

# ============================================
# Delete ECR Repositories
# ============================================
print_section "Deleting ECR Repositories"

# Delete ECR repositories with origami prefix
ECR_REPOS=$(aws ecr describe-repositories \
    --region "$REGION" \
    --query 'repositories[?starts_with(repositoryName, `origami`)].repositoryName' \
    --output text 2>/dev/null || echo "")

if [ -n "$ECR_REPOS" ]; then
    for REPO in $ECR_REPOS; do
        print_info "Deleting ECR repository: $REPO"
        if aws ecr delete-repository \
            --repository-name "$REPO" \
            --force \
            --region "$REGION" 2>/dev/null; then
            print_status "Deleted ECR repository: $REPO"
        else
            print_warning "Failed to delete ECR repository: $REPO"
        fi
    done
else
    print_info "No ECR repositories found"
fi

# ============================================
# Delete variables.txt
# ============================================
if [ -f "$VARIABLES_FILE" ]; then
    print_info "Deleting variables.txt"
    rm -f "$VARIABLES_FILE"
    print_status "variables.txt deleted"
fi

# ============================================
# Cleanup Complete
# ============================================
print_section "🎉 Cleanup Complete!"

echo ""
echo "✅ All AgentCore resources have been deleted"
echo ""
print_warning "CloudFormation stacks were NOT deleted"
echo "To delete CloudFormation stacks, run:"
echo "  aws cloudformation delete-stack --stack-name WildrydesFrontendStack"
echo ""
print_info "Note: Some resources may take a few minutes to fully delete"
echo ""
