/**
 * App Component
 * Root application component with context providers and routing
 * Sets up AuthContext and ChatContext providers
 * Implements routing between login page and chat interface
 * Requirements: 1.5, 2.1, All requirements
 */

import { useState } from 'react';
import { AuthProvider } from './contexts/AuthContext';
import { ChatProvider } from './contexts/ChatContext';
import AppLayout from './components/Layout/AppLayout';
import Login from './components/Auth/Login';
import Register from './components/Auth/Register';
import './App.css';

/**
 * AppContent handles routing based on authentication state
 * Renders Login/Register for unauthenticated users
 * AppLayout protects the chat route and renders ChatContainer for authenticated users
 */
const AppContent = () => {
  const [showRegister, setShowRegister] = useState(false);

  return (
    <AppLayout>
      {/* Unauthenticated content - Login or Register */}
      {showRegister ? (
        <Register onSwitchToLogin={() => setShowRegister(false)} />
      ) : (
        <Login onSwitchToRegister={() => setShowRegister(true)} />
      )}
    </AppLayout>
  );
};

/**
 * App Component
 * Wraps the application with AuthProvider and ChatContext providers
 * 
 * Provider hierarchy:
 * 1. AuthProvider - Manages authentication state and Cognito integration
 * 2. ChatProvider - Manages chat state (requires authentication context)
 * 3. AppContent - Handles routing based on authentication state
 * 
 * Cognito User Pool is configured via environment variables:
 * - VITE_COGNITO_USER_POOL_ID
 * - VITE_COGNITO_CLIENT_ID
 * - VITE_COGNITO_REGION
 * - VITE_AGENTCORE_ENDPOINT
 */
function App() {
  return (
    <AuthProvider>
      <ChatProvider>
        <AppContent />
      </ChatProvider>
    </AuthProvider>
  );
}

export default App;
