import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
  CognitoUserAttribute,
} from 'amazon-cognito-identity-js';
import type { AuthResult, User } from '../types';
import { extractUserId } from '../utils/jwtDecoder';

const userPool = new CognitoUserPool({
  UserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
  ClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || '',
});

let currentCognitoUser: CognitoUser | null = null;
let pendingNewPasswordUser: CognitoUser | null = null;

export class NewPasswordRequiredError extends Error {
  username: string;

  constructor(username: string) {
    super('NEW_PASSWORD_REQUIRED');
    this.name = 'NewPasswordRequiredError';
    this.username = username;
  }
}

const buildAuthResult = async (
  cognitoUser: CognitoUser,
  session: CognitoUserSession,
  username: string
): Promise<AuthResult> => {
  currentCognitoUser = cognitoUser;

  const jwtToken = session.getAccessToken().getJwtToken();
  const idToken = session.getIdToken().getJwtToken();
  const userId = extractUserId(idToken);

  return new Promise((resolve) => {
    cognitoUser.getUserAttributes((err, attributes) => {
      if (err) {
        resolve({
          user: {
            id: userId,
            username,
          },
          userId,
          jwtToken,
        });
        return;
      }

      const emailAttr = attributes?.find((attr) => attr.Name === 'email');
      const email = emailAttr?.Value;

      const user: User = {
        id: userId,
        username,
        email,
      };

      resolve({
        user,
        userId,
        jwtToken,
      });
    });
  });
};

export const login = async (
  username: string,
  password: string
): Promise<AuthResult> => {
  return new Promise((resolve, reject) => {
    const cleanUsername = username.trim();

    const authenticationDetails = new AuthenticationDetails({
      Username: cleanUsername,
      Password: password,
    });

    const cognitoUser = new CognitoUser({
      Username: cleanUsername,
      Pool: userPool,
    });

    cognitoUser.authenticateUser(authenticationDetails, {
      onSuccess: async (session: CognitoUserSession) => {
        pendingNewPasswordUser = null;
        const result = await buildAuthResult(cognitoUser, session, cleanUsername);
        resolve(result);
      },

      onFailure: (err) => {
        pendingNewPasswordUser = null;
        reject(new Error(`Authentication failed: ${err.message || 'Unknown error'}`));
      },

      newPasswordRequired: () => {
        pendingNewPasswordUser = cognitoUser;
        reject(new NewPasswordRequiredError(cleanUsername));
      },
    });
  });
};

export const completeNewPassword = async (
  newPassword: string
): Promise<AuthResult> => {
  return new Promise((resolve, reject) => {
    if (!pendingNewPasswordUser) {
      reject(new Error('No password change challenge is pending'));
      return;
    }

    const cognitoUser = pendingNewPasswordUser;
    const username = cognitoUser.getUsername();

    cognitoUser.completeNewPasswordChallenge(
      newPassword,
      {},
      {
        onSuccess: async (session: CognitoUserSession) => {
          pendingNewPasswordUser = null;
          const result = await buildAuthResult(cognitoUser, session, username);
          resolve(result);
        },

        onFailure: (err) => {
          reject(new Error(`Password change failed: ${err.message || 'Unknown error'}`));
        },
      }
    );
  });
};

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

export const logout = async (): Promise<void> => {
  return new Promise((resolve) => {
    if (currentCognitoUser) {
      currentCognitoUser.signOut();
    }

    currentCognitoUser = null;
    pendingNewPasswordUser = null;

    resolve();
  });
};

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

      currentCognitoUser = cognitoUser;

      const idToken = session.getIdToken().getJwtToken();
      const userId = extractUserId(idToken);

      cognitoUser.getUserAttributes((attrErr, attributes) => {
        if (attrErr) {
          resolve({
            id: userId,
            username: cognitoUser.getUsername(),
          });
          return;
        }

        const emailAttr = attributes?.find((attr) => attr.Name === 'email');
        const email = emailAttr?.Value;

        resolve({
          id: userId,
          username: cognitoUser.getUsername(),
          email,
        });
      });
    });
  });
};

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

      currentCognitoUser = cognitoUser;

      const jwtToken = session.getAccessToken().getJwtToken();
      resolve(jwtToken);
    });
  });
};

const authService = {
  login,
  completeNewPassword,
  signup,
  confirmSignup,
  resendConfirmationCode,
  logout,
  getCurrentUser,
  getJwtToken,
  extractUserId,
};

export default authService;
