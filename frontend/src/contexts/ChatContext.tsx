import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import type { ReactNode } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { Message, ChatState } from '../types';
import { createNewSession as createSessionId } from '../services/sessionService';
import { useAuth } from './AuthContext';

/**
 * ChatContext Interface
 * Provides chat state and methods for managing messages and sessions
 */
interface ChatContextType {
  messages: Message[];
  sessionId: string;
  isLoading: boolean;
  error: string | null;
  addMessage: (content: string, sender: 'user' | 'system') => void;
  clearMessages: () => void;
  createNewSession: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

/**
 * ChatProvider Props
 */
interface ChatProviderProps {
  children: ReactNode;
}

/**
 * ChatProvider Component
 * Manages chat state including messages, session ID, loading, and error states
 */
export const ChatProvider: React.FC<ChatProviderProps> = ({ children }) => {
  const auth = useAuth();

  // Initialize with a new session ID
  const [state, setState] = useState<ChatState>({
    messages: [],
    sessionId: createSessionId(),
    isLoading: false,
    error: null,
  });

  /**
   * Add a new message to the chat
   * @param content - The message content
   * @param sender - The message sender ('user' or 'system')
   */
  const addMessage = useCallback((content: string, sender: 'user' | 'system') => {
    const newMessage: Message = {
      id: uuidv4(),
      content,
      sender,
      timestamp: new Date(),
    };

    setState((prevState) => ({
      ...prevState,
      messages: [...prevState.messages, newMessage],
    }));
  }, []);

  /**
   * Clear all messages from the chat
   */
  const clearMessages = useCallback(() => {
    setState((prevState) => ({
      ...prevState,
      messages: [],
    }));
  }, []);

  /**
   * Create a new chat session
   * Generates a new session ID and clears all messages
   */
  const createNewSession = useCallback(() => {
    const newSessionId = createSessionId();
    setState((prevState) => ({
      ...prevState,
      sessionId: newSessionId,
      messages: [],
      error: null,
    }));
  }, []);

  // Register cleanup function with AuthContext on mount
  useEffect(() => {
    auth.registerChatCleanup(createNewSession);
  }, [auth, createNewSession]);

  /**
   * Set loading state
   * @param loading - The loading state
   */
  const setLoading = useCallback((loading: boolean) => {
    setState((prevState) => ({
      ...prevState,
      isLoading: loading,
    }));
  }, []);

  /**
   * Set error state
   * @param error - The error message or null to clear error
   */
  const setError = useCallback((error: string | null) => {
    setState((prevState) => ({
      ...prevState,
      error,
    }));
  }, []);

  const value: ChatContextType = {
    messages: state.messages,
    sessionId: state.sessionId,
    isLoading: state.isLoading,
    error: state.error,
    addMessage,
    clearMessages,
    createNewSession,
    setLoading,
    setError,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
};

/**
 * Custom hook to use ChatContext
 * @throws Error if used outside of ChatProvider
 */
export const useChatContext = (): ChatContextType => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
};

export default ChatContext;
