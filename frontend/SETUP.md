# Frontend Setup Guide

## AWS Cognito Configuration

This application requires AWS Cognito to be configured with **email as the primary sign-in method**.

### Step-by-Step Cognito Setup

#### 1. Create a Cognito User Pool

Navigate to AWS Cognito Console and create a new User Pool:

**Authentication providers:**
- ✅ Cognito user pool
- Sign-in options: **Email** (required)

**Password policy:**
- Minimum length: 8 characters (recommended)
- Require numbers, special characters, uppercase, lowercase (as needed)

**Multi-factor authentication (MFA):**
- Optional (can be enabled for additional security)

**User account recovery:**
- Enable self-service account recovery
- Email only (recommended)

#### 2. Configure Sign-up Experience

**Self-service sign-up:**
- ✅ Enable self-registration

**Attribute verification and user account confirmation:**
- ✅ Allow Cognito to automatically send messages to verify and confirm
- Attributes to verify: **Email** (required)
- Active attribute values when an update is pending: Keep original attribute value active

**Required attributes:**
- ✅ email (must be required)

**Custom attributes:**
- None required for this application

#### 3. Configure Message Delivery

**Email:**
- Send email with Cognito (for testing)
- OR Configure SES for production use

**SES Configuration (Production):**
1. Verify your email domain in Amazon SES
2. Move out of SES sandbox if needed
3. Configure FROM email address
4. Customize email templates (optional)

#### 4. Integrate Your App

**User pool name:**
- Choose a descriptive name (e.g., "wildrydes-workshop-users")

**App client:**
- App client name: "wildrydes-frontend"
- ❌ Don't generate a client secret (public client)
- Authentication flows:
  - ✅ ALLOW_USER_PASSWORD_AUTH
  - ✅ ALLOW_REFRESH_TOKEN_AUTH
  - ✅ ALLOW_USER_SRP_AUTH

**Advanced app client settings:**
- Access token expiration: 60 minutes (default)
- ID token expiration: 60 minutes (default)
- Refresh token expiration: 30 days (default)

#### 5. Get Your Configuration Values

After creating the User Pool:

1. **User Pool ID:**
   - Go to User Pool overview
   - Copy the "User pool ID" (format: `us-east-1_xxxxxxxxx`)

2. **App Client ID:**
   - Go to "App integration" tab
   - Under "App clients and analytics", click your app client
   - Copy the "Client ID" (format: long alphanumeric string)

### Environment Configuration

Create a `.env` file in the `frontend` directory:

```env
# AWS Cognito Configuration
VITE_COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx

# AgentCore Runtime Configuration
VITE_AGENTCORE_ENDPOINT=https://your-agentcore-endpoint.com/invocations
```

**Important Notes:**
- Never commit `.env` files to version control
- Use different User Pools for dev/staging/production
- Rotate credentials regularly

## Why Email as Username?

This application is designed with email as the primary identifier because:

1. **User-Friendly**: Users remember their email addresses
2. **Unique Identifier**: Email addresses are naturally unique
3. **Communication Channel**: Direct channel for verification and notifications
4. **Industry Standard**: Common pattern in modern web applications
5. **Password Recovery**: Simplified password reset flow

### Application Flow with Email Authentication

**Registration:**
```
User enters email + password
    ↓
Cognito creates user with email as username
    ↓
Verification code sent to email
    ↓
User enters code to confirm
    ↓
Account activated
```

**Login:**
```
User enters email + password
    ↓
Cognito validates credentials
    ↓
JWT tokens issued
    ↓
User authenticated
```

## Testing Your Setup

### 1. Test Registration Flow

```bash
# Start the dev server
npm run dev
```

1. Navigate to http://localhost:5173
2. Click "Sign Up"
3. Enter a valid email address and password
4. Check your email for verification code
5. Enter the verification code
6. Verify you're redirected to login

### 2. Test Login Flow

1. Enter your registered email and password
2. Click "Sign In"
3. Verify you're redirected to the chat interface
4. Check that your User ID and Session ID are displayed

### 3. Test Chat Functionality

1. Type a message in the chat input
2. Click "Send"
3. Verify the message appears in the chat
4. Verify you receive a response from AgentCore
5. Click "New Chat" to start a new session

## Common Issues and Solutions

### Issue: "User does not exist"
**Solution:** 
- Ensure the user has completed email verification
- Check that you're using the correct email address
- Verify the User Pool ID is correct

### Issue: "Verification code not received"
**Solution:**
- Check spam/junk folder
- Verify email configuration in Cognito
- If using SES, ensure domain is verified
- Click "Resend" to get a new code

### Issue: "Invalid password"
**Solution:**
- Ensure password meets Cognito requirements:
  - Minimum 8 characters
  - Contains required character types (numbers, special chars, etc.)

### Issue: "Network error" during authentication
**Solution:**
- Verify internet connection
- Check that Cognito User Pool ID and Client ID are correct
- Ensure the User Pool is in the correct AWS region
- Check browser console for detailed error messages

### Issue: "Cannot read properties of undefined"
**Solution:**
- Ensure `.env` file exists in frontend directory
- Verify all required environment variables are set
- Restart the dev server after changing `.env`

## Security Best Practices

### Development:
- Use separate Cognito User Pools for dev/prod
- Never commit `.env` files
- Use test email addresses for development
- Enable CloudWatch logging for debugging

### Production:
- Enable MFA for sensitive operations
- Configure SES for reliable email delivery
- Set up CloudWatch alarms for failed auth attempts
- Implement rate limiting
- Use HTTPS only
- Configure CORS properly
- Enable AWS WAF for additional protection
- Regular security audits

## Additional Resources

- [AWS Cognito Documentation](https://docs.aws.amazon.com/cognito/)
- [amazon-cognito-identity-js SDK](https://github.com/aws-amplify/amplify-js/tree/main/packages/amazon-cognito-identity-js)
- [Cognito User Pool Best Practices](https://docs.aws.amazon.com/cognito/latest/developerguide/best-practices.html)
- [SES Email Sending](https://docs.aws.amazon.com/ses/latest/dg/send-email.html)

## Next Steps

After completing the setup:

1. ✅ Cognito User Pool configured with email sign-in
2. ✅ Environment variables configured
3. ✅ Application running locally
4. ✅ Registration and login tested

You're ready to:
- Integrate with AgentCore Runtime
- Customize the UI
- Add additional features
- Deploy to production
