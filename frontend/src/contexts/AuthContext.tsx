import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import type { AuthState } from '../types';
import * as authService from '../services/authService';
import { NewPasswordRequiredError } from '../services/authService';
import { extractUserId } from '../utils/jwtDecoder';

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  completeNewPassword: (newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  registerChatCleanup: (cleanup: () => void) => void;
  newPasswordRequired: boolean;
  pendingUsername: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    userId: null,
    jwtToken: null,
  });

  const [newPasswordRequired, setNewPasswordRequired] = useState(false);
  const [pendingUsername, setPendingUsername] = useState<string | null>(null);
  const [chatCleanup, setChatCleanup] = useState<(() => void) | null>(null);

  useEffect(() => {
    const checkExistingSession = async () => {
      try {
        const user = await authService.getCurrentUser();
        const jwtToken = await authService.getJwtToken();
        const userId = extractUserId(jwtToken);

        setAuthState({
          isAuthenticated: true,
          user,
          userId,
          jwtToken,
        });
      } catch {
        setAuthState({
          isAuthenticated: false,
          user: null,
          userId: null,
          jwtToken: null,
        });
      }
    };

    checkExistingSession();
  }, []);

  const login = async (username: string, password: string): Promise<void> => {
    try {
      const result = await authService.login(username, password);

      setNewPasswordRequired(false);
      setPendingUsername(null);

      setAuthState({
        isAuthenticated: true,
        user: result.user,
        userId: result.userId,
        jwtToken: result.jwtToken,
      });
    } catch (error) {
      setAuthState({
        isAuthenticated: false,
        user: null,
        userId: null,
        jwtToken: null,
      });

      if (error instanceof NewPasswordRequiredError) {
        setNewPasswordRequired(true);
        setPendingUsername(error.username);
      }

      throw error;
    }
  };

  const completeNewPassword = async (newPassword: string): Promise<void> => {
    const result = await authService.completeNewPassword(newPassword);

    setNewPasswordRequired(false);
    setPendingUsername(null);

    setAuthState({
      isAuthenticated: true,
      user: result.user,
      userId: result.userId,
      jwtToken: result.jwtToken,
    });
  };

  const registerChatCleanup = (cleanup: () => void): void => {
    setChatCleanup(() => cleanup);
  };

  const logout = async (): Promise<void> => {
    try {
      await authService.logout();
    } finally {
      if (chatCleanup) {
        chatCleanup();
      }

      setNewPasswordRequired(false);
      setPendingUsername(null);

      setAuthState({
        isAuthenticated: false,
        user: null,
        userId: null,
        jwtToken: null,
      });
    }
  };

  const refreshToken = async (): Promise<void> => {
    try {
      const jwtToken = await authService.getJwtToken();
      const userId = extractUserId(jwtToken);
      const user = await authService.getCurrentUser();

      setAuthState({
        isAuthenticated: true,
        user,
        userId,
        jwtToken,
      });
    } catch (error) {
      setAuthState({
        isAuthenticated: false,
        user: null,
        userId: null,
        jwtToken: null,
      });
      throw error;
    }
  };

  const value: AuthContextType = {
    ...authState,
    login,
    completeNewPassword,
    logout,
    refreshToken,
    registerChatCleanup,
    newPasswordRequired,
    pendingUsername,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
};

export default AuthContext;
