/**
 * App Component
 * Root application component with context providers and routing.
 *
 * V1 authentication model:
 * - invitation-only users
 * - no public self-signup
 * - no demo users
 */

import { AuthProvider } from './contexts/AuthContext';
import { ChatProvider } from './contexts/ChatContext';
import { OperationProvider } from './contexts/OperationContext';
import AppLayout from './components/Layout/AppLayout';
import Login from './components/Auth/Login';
import './App.css';

const AppContent = () => {
  return (
    <AppLayout>
      <Login />
    </AppLayout>
  );
};

function App() {
  return (
    <AuthProvider>
      <ChatProvider>
        <OperationProvider>
          <AppContent />
        </OperationProvider>
      </ChatProvider>
    </AuthProvider>
  );
}

export default App;
