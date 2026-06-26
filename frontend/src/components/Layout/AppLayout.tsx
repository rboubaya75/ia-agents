/**
 * AppLayout Component
 * Provides the main application layout structure
 * Handles routing between login page and chat interface
 * Protects chat route with authentication check
 * Requirements: 1.5, 2.1
 */

import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import ChatContainer from '../Chat/ChatContainer';

interface AppLayoutProps {
  children?: React.ReactNode;
}

/**
 * AppLayout Component
 * Renders authenticated content (chat interface) or unauthenticated content (login/register)
 * 
 * @param children - Unauthenticated content (Login or Register components)
 */
export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const { isAuthenticated } = useAuth();

  // Protect chat route: redirect unauthenticated users to login
  if (!isAuthenticated) {
    // Render unauthenticated content (Login or Register)
    return <>{children}</>;
  }

  // Render authenticated content (Chat interface)
  return <ChatContainer />;
};

export default AppLayout;
