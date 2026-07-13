/**
 * AppLayout Component
 * Provides the main application layout structure
 * Handles routing between login page and chat interface
 * Protects chat route with authentication check
 * Requirements: 1.5, 2.1
 */

import React from 'react';
import { useAuth } from '../../contexts/useAuth';
import ChatContainer from '../Chat/ChatContainer';

interface AppLayoutProps {
  children?: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <>{children}</>;
  }

  return <ChatContainer />;
};

export default AppLayout;
