<<<<<<< HEAD
# ia-agents
=======
# 🦄 WildRydes - AgentCore Security Workshop

A complete workshop demonstrating secure AI-powered applications using AWS Bedrock AgentCore, Cognito authentication, and a React frontend. This workshop showcases best practices for building production-ready AI applications with proper security, authentication, and infrastructure as code.

## 🎯 Workshop Overview

This workshop demonstrates:
- 🔐 **Secure Authentication**: AWS Cognito with JWT tokens
- 🤖 **AI Integration**: AWS Bedrock AgentCore Runtime with Gateway and Memory
- 🗄️ **Data Persistence**: DynamoDB for trip management
- 🌐 **Modern Frontend**: React + TypeScript + Vite with CloudFront distribution
- 📦 **Infrastructure as Code**: CloudFormation templates for reproducible deployments
- 🔒 **Security Best Practices**: IAM roles, encryption, and secure API communication

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CloudFront Distribution                  │
│                    (Static Content Delivery)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    S3 Bucket (Frontend)                      │
│              React App + Cognito Authentication              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  AWS Cognito User Pool                       │
│              (User Authentication & JWT Tokens)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  AgentCore Gateway                           │
│         (API Gateway with Cognito Authorization)             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  AgentCore Runtime                           │
│         (AI Agent with Memory & Tool Integration)            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Lambda Function (Trip Management)               │
│                    ↓                                         │
│              DynamoDB Table (Trips)                          │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Prerequisites

- **AWS Account** with appropriate permissions
- **AWS CLI** installed and configured
- **Python 3.8+** with pip
- **Node.js 18+** and npm
- **Git** for cloning the repository

## 🚀 Quick Start

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd agentcore-security-workshop
```

### Step 2: Install Python Dependencies

```bash
cd deploy-agentcore
pip install -r requirements.txt
cd ..
```

### Step 3: Deploy CloudFormation Infrastructure

Deploy the combined infrastructure (DynamoDB, Cognito, S3, CloudFront):

```bash
aws cloudformation deploy \
  --template-file Cfn/combined-infrastructure.yaml \
  --stack-name WildrydesFrontendStack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

This creates:
- 🗄️ DynamoDB table for trip storage
- 🔐 Cognito User Pool for frontend authentication
- 🪣 S3 bucket for static hosting
- 🌐 CloudFront distribution
- 👤 Two pre-loaded test users
- 🔒 Secrets Manager for AgentCore configuration

**Test User Credentials:**
- User 1: `webuser@example.com` / `WebPassword123!`
- User 2: `testuser@example.com` / `TestPassword123!`

### Step 4: Deploy Complete Workshop

Run the unified deployment script:

```bash
./deploy-workshop.sh
```

This script will:
1. ✅ Validate prerequisites (AWS CLI, Python, Node.js)
2. 🤖 Deploy AgentCore resources (Gateway, Memory, Runtime, Lambda)
3. 🌐 Build and deploy the React frontend
4. 📝 Store configuration in Secrets Manager

**Deployment takes approximately 10-15 minutes.**

### Step 5: Access the Application

After deployment completes, the script will display your CloudFront URL:

```
🌐 Application URL: https://d1234567890abc.cloudfront.net
```

Open the URL in your browser and log in with one of the test users!

## 📁 Project Structure

```
agentcore-security-workshop/
├── Cfn/
│   ├── combined-infrastructure.yaml    # Complete CloudFormation template
│   ├── backend.yaml                    # Backend resources (DynamoDB)
│   └── frontend.yaml                   # Frontend resources (Cognito, S3, CloudFront)
├── deploy-agentcore/
│   ├── agents/                         # Agent phase implementations
│   ├── deploy-agentcore.py            # AgentCore deployment script
│   ├── deploy-runtime.py              # Runtime deployment script
│   ├── lambda_function_code.py        # Trip management Lambda
│   ├── utils.py                       # Deployment utilities
│   └── requirements.txt               # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/                # React components
│   │   ├── contexts/                  # React contexts (Auth, Chat)
│   │   ├── services/                  # API services
│   │   ├── types/                     # TypeScript types
│   │   └── utils/                     # Utility functions
│   ├── deploy-frontend.sh             # Frontend deployment script
│   └── package.json                   # Node.js dependencies
├── deploy-workshop.sh                 # Complete deployment script
├── cleanup-workshop.sh                # Resource cleanup script
└── README.md                          # This file
```

## 🔧 Manual Deployment (Alternative)

If you prefer to deploy components individually:

### 1. Deploy CloudFormation Stack

```bash
aws cloudformation deploy \
  --template-file Cfn/combined-infrastructure.yaml \
  --stack-name WildrydesFrontendStack \
  --capabilities CAPABILITY_NAMED_IAM
```

### 2. Deploy AgentCore Resources

```bash
cd deploy-agentcore
python3 deploy-agentcore.py
cd ..
```

### 3. Deploy Frontend

```bash
cd frontend
./deploy-frontend.sh
cd ..
```

## 🧹 Cleanup

To delete all AgentCore resources (preserving CloudFormation stacks):

```bash
./cleanup-workshop.sh
```

To delete CloudFormation stacks:

```bash
aws cloudformation delete-stack --stack-name WildrydesFrontendStack
```

## 🎓 Workshop Features

### Authentication
- Email-based login with AWS Cognito
- JWT token authentication
- Two pre-loaded test users for quick testing
- Secure session management

### AI Chat Interface
- Real-time chat with AgentCore Runtime
- Conversation memory across sessions
- Trip planning and management capabilities
- Error handling and loading states

### Trip Management
- Create trips with dates and destinations
- View all trips for a user
- Update trip details
- Persistent storage in DynamoDB

### Security Features
- IAM roles with least privilege
- Encrypted DynamoDB table
- S3 bucket encryption
- CloudFront with Origin Access Control
- JWT-based API authentication
- Secrets Manager for sensitive configuration

## 💻 Local Development

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local file with your configuration
cat > .env.local << EOF
VITE_COGNITO_USER_POOL_ID=<your-user-pool-id>
VITE_COGNITO_CLIENT_ID=<your-client-id>
VITE_COGNITO_REGION=us-east-1
VITE_AGENT_ARN=<your-agent-arn>
EOF

# Start development server
npm run dev

# Application available at http://localhost:5173
```

### Testing with Pre-loaded Users

The application includes two test users for quick testing:

**User 1 (Web User):**
- Email: `webuser@example.com`
- Password: `WebPassword123!`
- Use case: Primary testing account

**User 2 (Test User):**
- Email: `testuser@example.com`
- Password: `TestPassword123!`
- Use case: Multi-user testing scenarios

Click the quick login buttons on the login page to instantly log in as either user!

## 🔍 How It Works

### Authentication Flow

1. **User Login**: User clicks quick login button or enters credentials
2. **Cognito Authentication**: AWS Cognito validates credentials and issues JWT tokens
3. **Token Storage**: JWT tokens stored in memory (not localStorage for security)
4. **API Requests**: All AgentCore requests include Bearer token in Authorization header
5. **Session Management**: Automatic token refresh and session validation

### Chat Flow

1. **Session Creation**: New chat generates unique session ID (UUID)
2. **Message Sending**: User message sent to AgentCore Runtime via Gateway
3. **AI Processing**: AgentCore processes message with access to:
   - Long-term memory (user preferences)
   - Trip management tools (Lambda + DynamoDB)
   - Conversation history
4. **Response Display**: AI response streamed back and displayed in chat

### Trip Management Flow

1. **User Request**: "Create a trip to Paris from June 1-10"
2. **AgentCore Processing**: AI understands intent and extracts parameters
3. **Tool Invocation**: AgentCore calls Lambda function via Gateway
4. **Lambda Execution**: Lambda writes to DynamoDB with user ID and trip details
5. **Response**: Confirmation sent back through AgentCore to user

## 🐛 Troubleshooting

### Deployment Issues

**CloudFormation stack creation fails:**
- Check IAM permissions for CloudFormation, S3, Cognito, DynamoDB
- Verify stack name doesn't already exist
- Check AWS service quotas

**AgentCore deployment fails:**
- Ensure Python dependencies are installed: `pip install -r deploy-agentcore/requirements.txt`
- Check AWS region supports Bedrock AgentCore
- Verify IAM permissions for Bedrock, Lambda, IAM

**Frontend deployment fails:**
- Verify CloudFormation stack is deployed successfully
- Check Node.js version (18+ required)
- Ensure AWS CLI is configured correctly

### Application Issues

**Cannot log in with test users:**
- Wait 2-3 minutes after CloudFormation deployment for user creation
- Check CloudFormation stack outputs for user credentials
- Verify Cognito User Pool exists in AWS Console

**Chat not working:**
- Check browser console for errors
- Verify AgentCore Runtime ARN in Secrets Manager
- Ensure JWT token is valid (check Network tab)
- Try clicking "New Chat" to start fresh session

**"Invalid session ID" errors:**
- Session IDs must be 33+ characters (UUID format)
- Click "New Chat" to generate new session
- Clear browser cache and reload

**CloudFront shows 403 errors:**
- Wait 5-10 minutes for CloudFront distribution to fully deploy
- Check S3 bucket policy allows CloudFront access
- Verify files were uploaded to S3

### Resource Cleanup Issues

**cleanup-workshop.sh fails:**
- Some resources may have dependencies - wait a few minutes and retry
- Check AWS Console for resources that failed to delete
- Manually delete stuck resources if needed

**CloudFormation stack deletion stuck:**
- Check for resources created outside CloudFormation
- Empty S3 bucket before deleting stack
- Delete stack resources manually if needed

## 📚 Technology Stack

### Frontend
- **React 18**: Modern UI framework
- **TypeScript**: Type-safe development
- **Vite**: Fast build tool and dev server
- **Tailwind CSS**: Utility-first styling
- **AWS Cognito SDK**: Authentication

### Backend
- **AWS Bedrock AgentCore**: AI agent runtime and orchestration
- **AWS Lambda**: Serverless compute for trip management
- **Amazon DynamoDB**: NoSQL database for trip storage
- **AWS Cognito**: User authentication and authorization
- **AWS Secrets Manager**: Secure configuration storage

### Infrastructure
- **AWS CloudFormation**: Infrastructure as code
- **Amazon S3**: Static website hosting
- **Amazon CloudFront**: Content delivery network
- **AWS IAM**: Identity and access management

## 🔒 Security Best Practices

This workshop demonstrates several security best practices:

1. **Authentication**: JWT tokens with Cognito
2. **Authorization**: IAM roles with least privilege
3. **Encryption**: DynamoDB and S3 encryption at rest
4. **Network Security**: CloudFront with Origin Access Control
5. **Secrets Management**: AWS Secrets Manager for sensitive data
6. **Input Validation**: Parameter validation in Lambda functions
7. **HTTPS**: Enforced via CloudFront

## 📖 Additional Resources

- [AWS Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/)
- [AWS Cognito Documentation](https://docs.aws.amazon.com/cognito/)
- [React Documentation](https://react.dev/)
- [TypeScript Documentation](https://www.typescriptlang.org/)
- [Tailwind CSS Documentation](https://tailwindcss.com/)

## 🤝 Contributing

This is a workshop demo application. Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

Workshop Demo Application - For Educational Purposes

## 💬 Support

For questions or issues:
1. Check the troubleshooting section above
2. Review AWS service documentation
3. Check CloudFormation stack events for errors
4. Review application logs in browser console

## 🎉 Workshop Complete!

Congratulations on completing the WildRydes AgentCore Security Workshop! You've learned how to:
- ✅ Deploy secure AI applications with AWS Bedrock AgentCore
- ✅ Implement authentication with AWS Cognito
- ✅ Build modern React frontends with TypeScript
- ✅ Use Infrastructure as Code with CloudFormation
- ✅ Integrate AI agents with backend services
- ✅ Follow security best practices

Happy building! 🦄
>>>>>>> 5f26535 (first commit)
