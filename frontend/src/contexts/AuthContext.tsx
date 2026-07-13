import React, {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { AuthState } from '../types';
import * as authService from '../services/authService';
import { NewPasswordRequiredError } from '../services/authService';
import { extractUserId } from '../utils/jwtDecoder';

export interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  completeNewPassword: (newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  getValidAccessToken: () => Promise<string>;
  registerChatCleanup: (cleanup: () => void) => void;
  newPasswordRequired: boolean;
  pendingUsername: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

const EMPTY_AUTH_STATE: AuthState = {
  isAuthenticated: false,
  user: null,
  userId: null,
  jwtToken: null,
};

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [authState, setAuthState] = useState<AuthState>(EMPTY_AUTH_STATE);
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
        setAuthState(EMPTY_AUTH_STATE);
      }
    };

    void checkExistingSession();
  }, []);

  const login = useCallback(async (username: string, password: string): Promise<void> => {
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
      setAuthState(EMPTY_AUTH_STATE);

      if (error instanceof NewPasswordRequiredError) {
        setNewPasswordRequired(true);
        setPendingUsername(error.username);
      }

      throw error;
    }
  }, []);

  const completeNewPassword = useCallback(async (newPassword: string): Promise<void> => {
    const result = await authService.completeNewPassword(newPassword);

    setNewPasswordRequired(false);
    setPendingUsername(null);
    setAuthState({
      isAuthenticated: true,
      user: result.user,
      userId: result.userId,
      jwtToken: result.jwtToken,
    });
  }, []);

  const registerChatCleanup = useCallback((cleanup: () => void): void => {
    setChatCleanup(() => cleanup);
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await authService.logout();
    } finally {
      chatCleanup?.();
      setNewPasswordRequired(false);
      setPendingUsername(null);
      setAuthState(EMPTY_AUTH_STATE);
    }
  }, [chatCleanup]);

  const getValidAccessToken = useCallback(async (): Promise<string> => {
    try {
      const jwtToken = await authService.getJwtToken();
      const userId = extractUserId(jwtToken);

      setAuthState((current) => ({
        ...current,
        isAuthenticated: true,
        userId,
        jwtToken,
      }));
      return jwtToken;
    } catch (error) {
      setAuthState(EMPTY_AUTH_STATE);
      throw error;
    }
  }, []);

  const refreshToken = useCallback(async (): Promise<void> => {
    await getValidAccessToken();
  }, [getValidAccessToken]);

  const value = useMemo<AuthContextType>(() => ({
    ...authState,
    login,
    completeNewPassword,
    logout,
    refreshToken,
    getValidAccessToken,
    registerChatCleanup,
    newPasswordRequired,
    pendingUsername,
  }), [
    authState,
    completeNewPassword,
    getValidAccessToken,
    login,
    logout,
    newPasswordRequired,
    pendingUsername,
    refreshToken,
    registerChatCleanup,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export default AuthContext;
