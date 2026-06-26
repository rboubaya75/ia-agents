# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from bedrock_agentcore_starter_toolkit import Runtime
from boto3.session import Session
import os
import sys
import boto3
import json

region = os.environ.get('AWS_REGION', 'us-east-1')
boto_session = Session()
agentcore_runtime = Runtime()
agent_path = "agents/phase_1.py"


## Create Agent IAM role
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
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
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
        
        return response['Role']['Arn']
    except iam.exceptions.EntityAlreadyExistsException:
        return iam.get_role(RoleName=role_name)['Role']['Arn']


## JWT Authentication Configuration
## Uncomment this section to get set up authentication for your agent
client_ids = [
     "7nl7doqgnf1pedhico3v28qvb2"
]
discovery_url = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_KX6fkxJzE/.well-known/openid-configuration"

## Main deployment function
# Create custom admin role
admin_role_arn = create_agent_admin_role("origami-expeditions-1.5")

response = agentcore_runtime.configure(
    entrypoint=agent_path,
    auto_create_execution_role=False,
    execution_role=admin_role_arn,
    auto_create_ecr=True,
    requirements_file="requirements.txt",
    region=region,
    ## Additional piece for inbound auth
    ## JWT Authentication Configuration. Uncomment this section to set up Cognito authentication for your agent
    authorizer_configuration={
            "customJWTAuthorizer": {
            "allowedClients": client_ids,
           "discoveryUrl": discovery_url
     }
     },
    agent_name="origami_expeditions_1_5"
)
response

launch_result = agentcore_runtime.launch(auto_update_on_conflict=True)