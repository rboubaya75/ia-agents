/**
 * AuthContext
 * Provides global authentication state management for the application
 */

import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import type { AuthState } from '../types';
import * as authService from '../services/authService';
import { extractUserId } from '../utils/jwtDecoder';

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  registerChatCleanup: (cleanup: () => void) => void;
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

  // Store chat cleanup function
  const [chatCleanup, setChatCleanup] = useState<(() => void) | null>(null);

  // Check for existing session on mount
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
      } catch (error) {
        // No existing session or session expired
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

  /**
   * Logs in a user with username and password
   * @param username - The username
   * @param password - The password
   * @throws Error if authentication fails
   */
  const login = async (username: string, password: string): Promise<void> => {
    try {
      const result = await authService.login(username, password);

      setAuthState({
        isAuthenticated: true,
        user: result.user,
        userId: result.userId,
        jwtToken: result.jwtToken,
      });
    } catch (error) {
      // Clear auth state on login failure
      setAuthState({
        isAuthenticated: false,
        user: null,
        userId: null,
        jwtToken: null,
      });
      throw error;
    }
  };

  /**
   * Register chat cleanup function to be called on logout
   * @param cleanup - Function to clear chat state
   */
  const registerChatCleanup = (cleanup: () => void): void => {
    setChatCleanup(() => cleanup);
  };

  /**
   * Logs out the current user
   * Clears authentication state, chat messages, and Cognito session
   */
  const logout = async (): Promise<void> => {
    try {
      await authService.logout();
    } finally {
      // Clear chat state if cleanup function is registered
      if (chatCleanup) {
        chatCleanup();
      }

      // Always clear auth state, even if logout fails
      setAuthState({
        isAuthenticated: false,
        user: null,
        userId: null,
        jwtToken: null,
      });
    }
  };

  /**
   * Refreshes the JWT token for the current user
   * Updates the authentication state with the new token
   * @throws Error if token refresh fails
   */
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
      // If token refresh fails, clear auth state
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
    logout,
    refreshToken,
    registerChatCleanup,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * Custom hook to access the AuthContext
 * @returns The authentication context
 * @throws Error if used outside of AuthProvider
 */
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
};

export default AuthContext;
