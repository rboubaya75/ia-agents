# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType
from botocore.exceptions import ClientError
import uuid
import os
import utils
import boto3
import json

REGION = os.environ.get('AWS_REGION', 'us-east-1')
region = REGION
random_indicator = uuid.uuid4().hex[:8]

## Deploys memory
def create_long_term_memory():
    client = MemoryClient(region_name=region)
    memory_name = f"wildrydes_memory_{random_indicator}"
    print(f"Creating Memory with Long-Term Strategy name {memory_name}")
    try:
        # Create the memory resource with a single long-term memory strategy
        # The {actorId} placeholder will be dynamically replaced with the actual actor ID
        memory = client.create_memory_and_wait(
            name=memory_name,
            description="Travel Agent with Long-Term Memory",
            strategies=[{
                StrategyType.USER_PREFERENCE.value: {
                    "name": "UserPreferences",
                    "description": "Captures user preferences",
                    "namespaces": ["travel/{actorId}/preferences"]
                }
            }],
            event_expiry_days=7,  # Short-term conversation expires after 7 days
            max_wait=300,
            poll_interval=10
        )

        # Extract and print the memory ID
        memory_id = memory['id']
        print(f"Memory created successfully with ID: {memory_id}")
        return (memory_id)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ValidationException' and "already exists" in str(e):
            # If memory already exists, retrieve its ID
            memories = client.list_memories()
            memory_id = next((m['id'] for m in memories if m['id'].startswith(memory_name)), None)
            print(f"Memory already exists. Using existing memory ID: {memory_id}")
    except Exception as e:
        # Handle any errors during memory creation
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup on error - delete the memory if it was partially created
        if memory_id:
            try:
                client.delete_memory_and_wait(memory_id=memory_id)
                print(f"Cleaned up memory: {memory_id}")
            except Exception as cleanup_error:
                print(f"Failed to clean up memory: {cleanup_error}")


# Function to create AgentCore Gateway Cognito

## Creating Cognito User Pool 
def create_gateway():
    print('creating agentcore gateway')
    USER_POOL_NAME = f"wildrydes_gateway_user_pool_{random_indicator}"
    RESOURCE_SERVER_ID = f"wildrydes_resource_server_id_{random_indicator}"
    RESOURCE_SERVER_NAME = f"wildrydes_resource_server_{random_indicator}"
    CLIENT_NAME = f"wildrydes_appclient_{random_indicator}"
    ROLE_NAME = f"wildrydes_gateway_role_{random_indicator}"
    GATEWAY_NAME = f"wildrydes-gateway-{random_indicator}"
    SCOPES = [
        {"ScopeName": "gateway:read", "ScopeDescription": "Read access"},
        {"ScopeName": "gateway:write", "ScopeDescription": "Write access"}
    ]
    scopeString = f"{RESOURCE_SERVER_ID}/gateway:read {RESOURCE_SERVER_ID}/gateway:write"

    ## Create IAM role for Gateway to assume
    agentcore_gateway_iam_role = utils.create_agentcore_gateway_role(ROLE_NAME, REGION)
    print("Agentcore gateway role ARN: ", agentcore_gateway_iam_role['Role']['Arn'])    
    cognito = boto3.client("cognito-idp", region_name=REGION)

    print("Creating or retrieving Cognito resources...")
    user_pool_id = utils.get_or_create_user_pool(cognito, USER_POOL_NAME)
    print(f"User Pool ID: {user_pool_id}")

    utils.get_or_create_resource_server(cognito, user_pool_id, RESOURCE_SERVER_ID, RESOURCE_SERVER_NAME, SCOPES)
    print("Resource server ensured.")

    client_id, client_secret  = utils.get_or_create_m2m_client(cognito, user_pool_id, CLIENT_NAME, RESOURCE_SERVER_ID)
    print(f"Client ID: {client_id}")

    # Get discovery URL and token URL
    cognito_discovery_url = f'https://cognito-idp.{REGION}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration'
    user_pool_id_without_underscore = user_pool_id.replace("_", "")
    token_url = f"https://{user_pool_id_without_underscore}.auth.{REGION}.amazoncognito.com/oauth2/token"

    ## Function to create AgentCore Gateway
    # CreateGateway with Cognito authorizer without CMK. Use the Cognito user pool created in the previous step
    gateway_client = boto3.client('bedrock-agentcore-control', region_name = region)
    auth_config = {
        "customJWTAuthorizer": { 
            "allowedClients": [client_id],  # Client MUST match with the ClientId configured in Cognito. Example: 7rfbikfsm51j2fpaggacgng84g
            "discoveryUrl": cognito_discovery_url
        }
    }
    create_response = gateway_client.create_gateway(name=GATEWAY_NAME,
        roleArn = agentcore_gateway_iam_role['Role']['Arn'], # The IAM Role must have permissions to create/list/get/delete Gateway 
        protocolType='MCP',
        authorizerType='CUSTOM_JWT',
        authorizerConfiguration=auth_config, 
        description='Wildrydes AgentCore Gateway'
    )
    # Retrieve the GatewayID used for GatewayTarget creation
    gatewayID = create_response["gatewayId"]
    gatewayURL = create_response["gatewayUrl"]
    
    # Wait for gateway to become ACTIVE
    print(f"Waiting for gateway {gatewayID} to become ACTIVE...")
    import time
    max_wait_time = 300  # 5 minutes
    wait_interval = 10   # Check every 10 seconds
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        get_response = gateway_client.get_gateway(gatewayIdentifier=gatewayID)
        status = get_response.get('status', 'UNKNOWN')
        print(f"Gateway status: {status} (waited {elapsed_time}s)")
        
        if status in ['ACTIVE', 'READY']:
            print(f"✅ Gateway is now {status}")
            break
        elif status in ['FAILED', 'DELETING', 'DELETED']:
            raise Exception(f"Gateway creation failed with status: {status}")
        
        time.sleep(wait_interval)
        elapsed_time += wait_interval
    else:
        raise Exception(f"Gateway did not become ACTIVE/READY within {max_wait_time} seconds")

    ## Create a Lambda target
    ## Creating sample function
    lambda_resp = utils.create_gateway_lambda("lambda_function_code.py", REGION)
    print ('Creating Lambda function')
    if lambda_resp is not None:
        if lambda_resp['exit_code'] == 0:
            print("Lambda function created with ARN: ", lambda_resp['lambda_function_arn'])
        else:
            print("Lambda function creation failed with message: ", lambda_resp['lambda_function_arn'])

# Replace the AWS Lambda function ARN below
    print ('attaching Lambda function')
    lambda_target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_resp['lambda_function_arn'], # Replace this with your AWS Lambda function ARN
                "toolSchema": {
                    "inlinePayload": [
                            {
                                "name": "create_trip",
                                "description": "Create a new trip with name, dates, and optional details",
                                "inputSchema": {
                                "type": "object",
                                "required": ["operation", "userId", "tripName", "startDate", "endDate"],
                                "properties": {
                                    "operation": {
                                    "type": "string",
                                    "description": "Operation type: create_trip"
                                    },
                                    "userId": {
                                    "type": "string",
                                    "description": "User ID for the trip owner"
                                    },
                                    "tripName": {
                                    "type": "string",
                                    "description": "Name of the trip"
                                    },
                                    "startDate": {
                                    "type": "string",
                                    "description": "Start date (YYYY-MM-DD)"
                                    },
                                    "endDate": {
                                    "type": "string",
                                    "description": "End date (YYYY-MM-DD)"
                                    },
                                    "destination": {
                                    "type": "string",
                                    "description": "Destination of the trip"
                                    },
                                    "description": {
                                    "type": "string",
                                    "description": "Trip description"
                                    }
                                }
                                }
                            },
                            {
                                "name": "get_trips",
                                "description": "Get all trips for a specific user",
                                "inputSchema": {
                                "type": "object",
                                "required": ["operation", "userId"],
                                "properties": {
                                    "operation": {
                                    "type": "string",
                                    "description": "Operation type: get_trips"
                                    },
                                    "userId": {
                                    "type": "string",
                                    "description": "User ID to get trips for"
                                    }
                                }
                                }
                            },
                            {
                                "name": "get_trip",
                                "description": "Get details of a specific trip",
                                "inputSchema": {
                                "type": "object",
                                "required": ["operation", "userId", "tripId"],
                                "properties": {
                                    "operation": {
                                    "type": "string",
                                    "description": "Operation type: get_trip"
                                    },
                                    "userId": {
                                    "type": "string",
                                    "description": "User ID"
                                    },
                                    "tripId": {
                                    "type": "string",
                                    "description": "ID of the trip to retrieve"
                                    }
                                }
                                }
                            },
                            {
                                "name": "update_trip",
                                "description": "Update an existing trip",
                                "inputSchema": {
                                "type": "object",
                                "required": ["operation", "userId", "tripId"],
                                "properties": {
                                    "operation": {
                                    "type": "string",
                                    "description": "Operation type: update_trip"
                                    },
                                    "userId": {
                                    "type": "string",
                                    "description": "User ID"
                                    },
                                    "tripId": {
                                    "type": "string",
                                    "description": "ID of the trip to update"
                                    },
                                    "tripName": {
                                    "type": "string",
                                    "description": "Updated name"
                                    },
                                    "startDate": {
                                    "type": "string",
                                    "description": "Updated start date"
                                    },
                                    "endDate": {
                                    "type": "string",
                                    "description": "Updated end date"
                                    },
                                    "description": {
                                    "type": "string",
                                    "description": "Updated description"
                                    }
                                }
                                }
                            }
                    ]
                }
            }
        }
    }

    credential_config = [ 
        {
            "credentialProviderType" : "GATEWAY_IAM_ROLE"
        }
    ]
    targetname='Wildrydes-trip-planner-CRU'
    response = gateway_client.create_gateway_target(
        gatewayIdentifier=gatewayID,
        name=targetname,
        description='Wildrydes trip planner function that can create and update trips',
        targetConfiguration=lambda_target_config,
        credentialProviderConfigurations=credential_config)
    return (cognito_discovery_url, gatewayID, gatewayURL, client_id, client_secret, scopeString, user_pool_id, token_url)

# Store secrets
def store_secrets_in_secrets_manager(variables):
    """Store variables in AWS Secrets Manager"""
    secrets_client = boto3.client('secretsmanager', region_name=REGION)
    secret_name = 'wildrydes-secrets'
    
    try:
        # Try to update existing secret
        secrets_client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(variables)
        )
        print(f"Updated secret: {secret_name}")
    except secrets_client.exceptions.ResourceNotFoundException:
        # Create new secret if it doesn't exist
        secrets_client.create_secret(
            Name=secret_name,
            SecretString=json.dumps(variables),
            Description='WildRydes application secrets'
        )
        print(f"Created secret: {secret_name}")

# Deploy AgentCore Runtime
def deploy_agentcore_runtime():
    """Deploy the AgentCore Runtime"""
    from bedrock_agentcore_starter_toolkit import Runtime
    from boto3.session import Session
    
    print("\n" + "="*50)
    print("Deploying AgentCore Runtime...")
    print("="*50)
    
    boto_session = Session()
    agentcore_runtime = Runtime()
    
    # Create Agent IAM role
    def create_agent_admin_role(role_name):
        iam = boto3.client('iam')
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AssumeRolePolicy",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "bedrock-agentcore.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole",
                    "Condition": {
                        "StringEquals": {
                            "aws:SourceAccount": account_id
                        },
                        "ArnLike": {
                            "aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:*"
                        }
                    }
                }
            ]
        }
        
        try:
            response = iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='Agent role with full admin permissions'
            )
            
            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess'
            )
            
            print(f"✅ Created IAM role: {role_name}")
            return response['Role']['Arn']
        except iam.exceptions.EntityAlreadyExistsException:
            role_arn = iam.get_role(RoleName=role_name)['Role']['Arn']
            print(f"✅ Using existing IAM role: {role_name}")
            return role_arn
    
    # Create custom admin role
    role_name = "origami-expeditions-1.5"
    admin_role_arn = create_agent_admin_role(role_name)
    
    # Configure runtime
    print("Configuring AgentCore Runtime...")
    agentcore_runtime.configure(
        entrypoint="agents/phase_1.py",
        auto_create_execution_role=False,
        execution_role=admin_role_arn,
        auto_create_ecr=True,
        requirements_file="requirements.txt",
        region=REGION,
        agent_name="origami_expeditions_1_5"
    )
    
    # Launch runtime
    print("Launching AgentCore Runtime (this may take several minutes)...")
    launch_result = agentcore_runtime.launch(auto_update_on_conflict=True)
    
    # Extract runtime information
    runtime_arn = launch_result.agent_arn
    runtime_id = launch_result.agent_id
    
    print(f"✅ AgentCore Runtime deployed successfully!")
    print(f"   Runtime ARN: {runtime_arn}")
    print(f"   Runtime ID: {runtime_id}")
    
    return runtime_arn, runtime_id

def main():
    print("\n" + "="*60)
    print("🦄 WildRydes AgentCore Deployment")
    print("="*60)
    print("This script will deploy:")
    print("  1. AgentCore Gateway with Cognito authentication")
    print("  2. Memory with long-term strategy")
    print("  3. AgentCore Runtime")
    print("="*60 + "\n")
    
    # Create resources and collect variables
    print("Step 1: Creating Gateway and Memory...")
    cognito_discovery_url, gateway_id, gateway_url, client_id, client_secret, scope_string, user_pool_id, token_url = create_gateway()
    memory_id = create_long_term_memory()
    
    # Deploy AgentCore Runtime
    print("\nStep 2: Deploying AgentCore Runtime...")
    runtime_arn, runtime_id = deploy_agentcore_runtime()
    
    # Prepare variables dictionary
    variables = {
        'MEMORY_ID': memory_id,
        'GATEWAY_ID': gateway_id,
        'GATEWAY_URL': gateway_url,
        'CLIENT_ID': client_id,
        'CLIENT_SECRET': client_secret,
        'COGNITO_DISCOVERY_URL': cognito_discovery_url,
        'SCOPE_STRING': scope_string,
        'USER_POOL_ID': user_pool_id,
        'TOKEN_URL': token_url,
        'RANDOM_INDICATOR': random_indicator,
        'REGION': REGION,
        'GUARDRAILS_ID': '',
        'GUARDRAILS_VERSION': '1',
        'RUNTIME_ARN': runtime_arn,
        'RUNTIME_ID': runtime_id
    }
    
    # Store in Secrets Manager
    print("\nStep 3: Storing configuration in Secrets Manager...")
    store_secrets_in_secrets_manager(variables)
    
    # Write variables to file (existing code)
    print("\nStep 4: Writing configuration to variables.txt...")
    with open('variables.txt', 'w') as f:
        f.write(f"MEMORY_ID={memory_id}\n\n")
        f.write(f"GATEWAY_ID={gateway_id}\n\n")
        f.write(f"GATEWAY_URL={gateway_url}\n\n")
        f.write(f"CLIENT_ID={client_id}\n\n")
        f.write(f"CLIENT_SECRET={client_secret}\n\n")
        f.write(f"COGNITO_DISCOVERY_URL={cognito_discovery_url}\n\n")
        f.write(f"SCOPE_STRING={scope_string}\n\n")
        f.write(f"USER_POOL_ID={user_pool_id}\n\n")
        f.write(f"TOKEN_URL={token_url}\n\n")
        f.write(f"RANDOM_INDICATOR={random_indicator}\n\n")
        f.write(f"REGION={REGION}\n\n")
        f.write(f"GUARDRAILS_ID=''\n")
        f.write(f"GUARDRAILS_VERSION='1'\n")
        f.write(f"RUNTIME_ARN={runtime_arn}\n\n")
        f.write(f"RUNTIME_ID={runtime_id}\n\n")
    
    print("\n" + "="*60)
    print("✅ WildRydes AgentCore Deployment Complete!")
    print("="*60)
    print("\n📦 Deployed Resources:")
    print(f"  🔐 Gateway ID: {gateway_id}")
    print(f"  🧠 Memory ID: {memory_id}")
    print(f"  🤖 Runtime ARN: {runtime_arn}")
    print(f"  🔑 Secrets Manager: wildrydes-secrets")
    print("\n📝 Configuration saved to:")
    print(f"  - variables.txt")
    print(f"  - AWS Secrets Manager (wildrydes-secrets)")
    print("\n🚀 Next Steps:")
    print("  1. Deploy the frontend:")
    print("     cd ../frontend")
    print("     ./deploy.sh")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
