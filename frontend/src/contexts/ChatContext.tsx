import React, { createContext, useCallback, useEffect, useState, type ReactNode } from 'react';
import { v4 as uuidv4 } from 'uuid';
import type { Message, ChatState } from '../types';
import { createNewSession as createSessionId } from '../services/sessionService';
import { useAuth } from './useAuth';

export interface ChatContextType {
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

interface ChatProviderProps {
  children: ReactNode;
}

export const ChatProvider: React.FC<ChatProviderProps> = ({ children }) => {
  const auth = useAuth();
  const [state, setState] = useState<ChatState>({
    messages: [],
    sessionId: createSessionId(),
    isLoading: false,
    error: null,
  });

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

  const clearMessages = useCallback(() => {
    setState((prevState) => ({
      ...prevState,
      messages: [],
    }));
  }, []);

  const createNewSession = useCallback(() => {
    setState((prevState) => ({
      ...prevState,
      sessionId: createSessionId(),
      messages: [],
      error: null,
    }));
  }, []);

  useEffect(() => {
    auth.registerChatCleanup(createNewSession);
  }, [auth, createNewSession]);

  const setLoading = useCallback((loading: boolean) => {
    setState((prevState) => ({
      ...prevState,
      isLoading: loading,
    }));
  }, []);

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

export default ChatContext;
