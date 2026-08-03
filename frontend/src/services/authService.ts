import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
  CognitoUserAttribute,
} from 'amazon-cognito-identity-js';
import type { AuthResult, User } from '../types';
import { extractUserId } from '../utils/jwtDecoder';
import { tokenStorage } from './tokenStorage';
import { getRuntimeConfig } from '../lib/runtimeConfig';
import { SessionExpiredError } from '../lib/authErrors';

// `Storage` scinde les jetons : accès en mémoire, rafraîchissement et identité en
// `sessionStorage` (V2-LLD-010 §4.2). Le SDK n'hérite pas ce réglage du pool vers les
// `CognitoUser` construits directement — il est donc répété à chaque construction, sans
// quoi ces derniers retomberaient sur `localStorage`.
const userPool = new CognitoUserPool({
  UserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
  ClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || '',
  Storage: tokenStorage,
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
      Storage: tokenStorage,
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
      Storage: tokenStorage,
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
      Storage: tokenStorage,
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

const currentSession = (cognitoUser: CognitoUser): Promise<CognitoUserSession> =>
  new Promise((resolve, reject) => {
    cognitoUser.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session) {
        reject(new SessionExpiredError());
        return;
      }
      resolve(session);
    });
  });

/**
 * Jeton d'accès valide, renouvelé **par l'échéance et non par l'échec** (V2-LLD-010 §4.3).
 *
 * Attendre le 401 signifie qu'un appel sur deux échoue au voisinage de l'expiration, et
 * surtout qu'un appel non rejouable — une confirmation de commande en est un — peut
 * échouer. La marge est un paramètre d'exécution, pas une constante (§15.2).
 *
 * C'est le jeton d'**accès** qui est présenté à l'API, jamais le jeton d'identité
 * (`V2-ADR-020`) ; ce dernier n'est décodé que pour l'affichage du profil.
 */
export const getAccessToken = async (
  options: { forceRefresh?: boolean } = {},
): Promise<string> => {
  const cognitoUser = userPool.getCurrentUser();
  if (!cognitoUser) {
    throw new SessionExpiredError('Aucune session authentifiée.');
  }

  const session = await currentSession(cognitoUser);
  currentCognitoUser = cognitoUser;

  const secondsLeft = session.getAccessToken().getExpiration() - Math.floor(Date.now() / 1000);
  if (!options.forceRefresh && secondsLeft > getRuntimeConfig().tokenRenewalMarginSeconds) {
    return session.getAccessToken().getJwtToken();
  }

  const renewed = await new Promise<CognitoUserSession>((resolve, reject) => {
    cognitoUser.refreshSession(
      session.getRefreshToken(),
      (err: Error | null, next: CognitoUserSession | null) => {
        if (err || !next) {
          // Jeton de rafraîchissement invalide ou révoqué : déconnexion immédiate, sans
          // réessai (§4.3).
          reject(new SessionExpiredError());
          return;
        }
        resolve(next);
      },
    );
  });

  return renewed.getAccessToken().getJwtToken();
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
  getAccessToken,
  extractUserId,
};

export default authService;
