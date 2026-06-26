# JWT Token Fix for AgentCore Authentication

## Problem
Error: `OAuth authorization failed: Claim 'client_id' value mismatch with configuration`

## Root Cause
The application was using Cognito's **ID token** instead of the **access token**. 

### Token Differences:

**ID Token:**
- Contains user identity information
- Has claims: `sub`, `email`, `aud` (audience), etc.
- Does NOT have `client_id` claim
- Used for: User authentication and profile information

**Access Token:**
- Contains authorization information
- Has claims: `sub`, `client_id`, `scope`, `token_use`, etc.
- HAS the `client_id` claim
- Used for: API authorization (like AgentCore)

## Solution
Changed `authService.ts` to use **access token** for API calls:

```typescript
// Before (WRONG):
const jwtToken = session.getIdToken().getJwtToken();

// After (CORRECT):
const jwtToken = session.getAccessToken().getJwtToken();
```

## What Changed

### In `login()` function:
- Now uses access token for API authorization
- Still uses ID token to extract user ID (sub claim)

### In `getCurrentUser()` function:
- Now uses access token for API authorization
- Still uses ID token to extract user ID

### In `getJwtToken()` function:
- Now returns access token instead of ID token

## Testing

1. **Log out and log back in** - The token is cached in the session, so you need to re-authenticate
2. Send a chat message
3. The 403 error should be resolved

## Debug Tool

If you still have issues, use `frontend/debug-token.html`:
1. Open it in a browser
2. Paste your JWT token
3. Check if it has `client_id` claim

The access token should show:
```json
{
  "sub": "user-id",
  "client_id": "39nrcq17t41cpgjektu3jtkb5h",
  "token_use": "access",
  "scope": "...",
  ...
}
```

## Why This Matters

AgentCore's JWT authorizer validates:
1. The token signature (from Cognito)
2. The `client_id` claim matches the configured allowed clients
3. The issuer (`iss`) matches the discovery URL

Without the `client_id` claim, validation fails with a 403 error.
