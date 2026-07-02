import { AuthProvider } from './contexts/AuthContext';
import { ChatProvider } from './contexts/ChatContext';
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
        <AppContent />
      </ChatProvider>
    </AuthProvider>
  );
}

export default App;
