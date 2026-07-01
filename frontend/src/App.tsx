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
 * Wraps the application with AuthProvider and ChatContext providers.
 *
 * Frontend configuration is provided through:
 * - VITE_COGNITO_USER_POOL_ID
 * - VITE_COGNITO_CLIENT_ID
 * - VITE_COGNITO_REGION
 * - VITE_API_BASE_URL
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
