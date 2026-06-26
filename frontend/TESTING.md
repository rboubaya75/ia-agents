# Testing AgentCore Integration

## Prerequisites

1. AgentCore runtime deployed (check `deploy-agentcore/variables.txt` for confirmation)
2. Environment variables configured in `frontend/.env.local`:
   - `VITE_COGNITO_USER_POOL_ID`
   - `VITE_COGNITO_CLIENT_ID`
   - `VITE_AGENTCORE_ID`
   - `VITE_AGENT_ARN`

## Start the Development Server

```bash
cd frontend
npm run dev
```

The app will be available at http://localhost:5173

## Testing Flow

### 1. Register a New User
1. Click "Sign Up" on the login page
2. Enter your email and a password (min 8 characters)
3. Check your email for the verification code
4. Enter the verification code to confirm your account

### 2. Login
1. Enter your registered email and password
2. Click "Sign In"
3. You should be redirected to the chat interface

### 3. Test Chat with AgentCore
1. You should see:
   - Your User ID in the header
   - A Session ID in the header
   - An empty chat area
   - A message input box at the bottom

2. Type a message (e.g., "Hello, what can you help me with?")
3. Click "Send" or press Enter

4. Expected behavior:
   - Your message appears immediately in the chat
   - A loading indicator shows while waiting for response
   - The AgentCore response appears in the chat
   - The response should be from your deployed agent

### 4. Test New Chat Session
1. Click "New Chat" button in the header
2. The Session ID should change
3. The chat history should clear
4. Send a new message to verify the new session works

## Troubleshooting

### "Agent ARN is not configured"
- Check that `VITE_AGENT_ARN` is set in `.env.local`
- Restart the dev server after changing `.env.local`

### "Authentication token is missing"
- Log out and log back in
- Check browser console for Cognito errors

### "AgentCore request failed: 403"
- Verify the JWT token is being sent correctly
- Check that the Cognito User Pool Client ID matches the one configured in AgentCore deployment
- Verify the authorizer configuration in `deploy-agentcore/deploy-runtime.py`

### "AgentCore request failed: 404"
- Verify the Agent ARN is correct
- Check that the agent is deployed: `aws bedrock-agentcore list-runtimes --region us-east-1`

### Network errors
- Check browser console for CORS errors
- Verify you have internet connectivity
- Check AWS credentials are valid

## Verifying the Integration

### Check Environment Variables
```bash
cat frontend/.env.local
```

Should show all four required variables.

### Check AgentCore Endpoint Construction
The endpoint is constructed as:
```
https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{URL_ENCODED_ARN}/invocations
```

Example:
```
https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A846436852630%3Aruntime%2Forigami_expeditions-Rx29PFDdOG/invocations
```

### Check Request Format
The request sent to AgentCore:
```json
{
  "prompt": "Your message here"
}
```

Headers:
- `Authorization: Bearer {jwtToken}`
- `Content-Type: application/json`
- `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: {sessionId}`

### Expected Response Format
The response can be either JSON or plain text, depending on your agent implementation.

## Next Steps

Once basic chat is working:
1. Test error handling (invalid messages, network issues)
2. Test session persistence across page refreshes
3. Test multiple concurrent sessions
4. Monitor AgentCore logs in CloudWatch
5. Test with different types of prompts
