/**
 * Authentication Service
 * Handles AWS Cognito authentication operations
 */

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
  CognitoUserAttribute,
} from 'amazon-cognito-identity-js';
import type { AuthResult, User } from '../types';
import { extractUserId } from '../utils/jwtDecoder';

// Cognito User Pool configuration
const userPool = new CognitoUserPool({
  UserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
  ClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || '',
});

// Store current user in memory
let currentCognitoUser: CognitoUser | null = null;

/**
 * Authenticates a user with AWS Cognito
 * @param username - The username
 * @param password - The password
 * @returns AuthResult containing user information, user ID, and JWT token
 * @throws Error if authentication fails
 */
export const login = async (
  username: string,
  password: string
): Promise<AuthResult> => {
  return new Promise((resolve, reject) => {
    const authenticationDetails = new AuthenticationDetails({
      Username: username,
      Password: password,
    });

    const cognitoUser = new CognitoUser({
      Username: username,
      Pool: userPool,
    });

    cognitoUser.authenticateUser(authenticationDetails, {
      onSuccess: (session: CognitoUserSession) => {
        // Store user in memory
        currentCognitoUser = cognitoUser;

        // Extract JWT token - use ACCESS token for AgentCore (has client_id claim)
        const jwtToken = session.getAccessToken().getJwtToken();

        // Extract user ID from ID token (has sub claim)
        const idToken = session.getIdToken().getJwtToken();
        const userId = extractUserId(idToken);

        // Get user attributes
        cognitoUser.getUserAttributes((err, attributes) => {
          if (err) {
            // If we can't get attributes, still return basic user info
            const user: User = {
              id: userId,
              username: username,
            };

            resolve({
              user,
              userId,
              jwtToken,
            });
            return;
          }

          // Extract email from attributes if available
          const emailAttr = attributes?.find(attr => attr.Name === 'email');
          const email = emailAttr?.Value;

          const user: User = {
            id: userId,
            username: username,
            email: email,
          };

          resolve({
            user,
            userId,
            jwtToken,
          });
        });
      },
      onFailure: (err) => {
        reject(new Error(`Authentication failed: ${err.message || 'Unknown error'}`));
      },
    });
  });
};

/**
 * Registers a new user with AWS Cognito
 * @param username - The username
 * @param password - The password
 * @param email - The email address
 * @returns Success message and username
 * @throws Error if registration fails
 */
export const signup = async (
  username: string,
  password: string,
  email: string
): Promise<{ message: string; username: string; userConfirmed: boolean }> => {
  return new Promise((resolve, reject) => {
    const attributeList = [
      new CognitoUserAttribute({
        Name: 'email',
        Value: email,
      }),
    ];

    userPool.signUp(
      username,
      password,
      attributeList,
      [],
      (err, result) => {
        if (err) {
          reject(new Error(`Registration failed: ${err.message || 'Unknown error'}`));
          return;
        }

        if (!result) {
          reject(new Error('Registration failed: No result returned'));
          return;
        }

        resolve({
          message: result.userConfirmed 
            ? 'Registration successful! You can now log in.' 
            : 'Registration successful! Please check your email for a verification code.',
          username: result.user.getUsername(),
          userConfirmed: result.userConfirmed,
        });
      }
    );
  });
};

/**
 * Confirms user registration with verification code
 * @param username - The username
 * @param code - The verification code from email
 * @returns Success message
 * @throws Error if confirmation fails
 */
export const confirmSignup = async (
  username: string,
  code: string
): Promise<{ message: string }> => {
  return new Promise((resolve, reject) => {
    const cognitoUser = new CognitoUser({
      Username: username,
      Pool: userPool,
    });

    cognitoUser.confirmRegistration(code, true, (err) => {
      if (err) {
        reject(new Error(`Verification failed: ${err.message || 'Unknown error'}`));
        return;
      }

      resolve({
        message: 'Email verified successfully! You can now log in.',
      });
    });
  });
};

/**
 * Resends the verification code to the user's email
 * @param username - The username
 * @returns Success message
 * @throws Error if resend fails
 */
export const resendConfirmationCode = async (
  username: string
): Promise<{ message: string }> => {
  return new Promise((resolve, reject) => {
    const cognitoUser = new CognitoUser({
      Username: username,
      Pool: userPool,
    });

    cognitoUser.resendConfirmationCode((err) => {
      if (err) {
        reject(new Error(`Failed to resend code: ${err.message || 'Unknown error'}`));
        return;
      }

      resolve({
        message: 'Verification code resent! Please check your email.',
      });
    });
  });
};

/**
 * Logs out the current user
 * Clears the session and signs out from Cognito
 */
export const logout = async (): Promise<void> => {
  return new Promise((resolve) => {
    if (currentCognitoUser) {
      currentCognitoUser.signOut();
    }
    
    // Clear stored user
    currentCognitoUser = null;
    
    resolve();
  });
};

/**
 * Gets the current authenticated user
 * @returns The current user information
 * @throws Error if no user is authenticated
 */
export const getCurrentUser = async (): Promise<User> => {
  return new Promise((resolve, reject) => {
    const cognitoUser = userPool.getCurrentUser();

    if (!cognitoUser) {
      reject(new Error('No authenticated user'));
      return;
    }

    cognitoUser.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session || !session.isValid()) {
        reject(new Error('Session is invalid or expired'));
        return;
      }

      // Store user in memory
      currentCognitoUser = cognitoUser;
      
      // Extract user ID from ID token (has sub claim)
      const idToken = session.getIdToken().getJwtToken();
      const userId = extractUserId(idToken);

      // Get user attributes
      cognitoUser.getUserAttributes((attrErr, attributes) => {
        if (attrErr) {
          // Return basic user info if attributes can't be retrieved
          resolve({
            id: userId,
            username: cognitoUser.getUsername(),
          });
          return;
        }

        const emailAttr = attributes?.find(attr => attr.Name === 'email');
        const email = emailAttr?.Value;

        resolve({
          id: userId,
          username: cognitoUser.getUsername(),
          email: email,
        });
      });
    });
  });
};

/**
 * Gets the JWT token for the current authenticated user
 * @returns The JWT ID token
 * @throws Error if no user is authenticated or session is invalid
 */
export const getJwtToken = async (): Promise<string> => {
  return new Promise((resolve, reject) => {
    const cognitoUser = userPool.getCurrentUser();

    if (!cognitoUser) {
      reject(new Error('No authenticated user'));
      return;
    }

    cognitoUser.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session || !session.isValid()) {
        reject(new Error('Session is invalid or expired'));
        return;
      }

      // Store user in memory
      currentCognitoUser = cognitoUser;

      // Return ACCESS token for AgentCore (has client_id claim)
      const jwtToken = session.getAccessToken().getJwtToken();
      resolve(jwtToken);
    });
  });
};

// Export as default object matching AuthService interface
const authService = {
  login,
  signup,
  confirmSignup,
  resendConfirmationCode,
  logout,
  getCurrentUser,
  getJwtToken,
  extractUserId, // Re-export from jwtDecoder for convenience
};

export default authService;
