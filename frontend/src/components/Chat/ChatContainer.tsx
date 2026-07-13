/**
 * ChatContainer Component
 * Main orchestrator for the chat interface
 */

import React from 'react';
import { useChatContext } from '../../contexts/useChatContext';
import { useAuth } from '../../contexts/useAuth';
import { sendMessage } from '../../services/chatService';
import ChatHeader from './ChatHeader';
import ChatMessages from './ChatMessages';
import ChatInput from './ChatInput';

export const ChatContainer: React.FC = () => {
  const {
    messages,
    sessionId,
    isLoading,
    error,
    addMessage,
    setLoading,
    setError,
  } = useChatContext();

  const { jwtToken } = useAuth();

  const handleSendMessage = async (messageContent: string) => {
    setError(null);
    addMessage(messageContent, 'user');
    setLoading(true);

    try {
      if (!jwtToken) {
        throw new Error('Authentication token is missing. Please log in again.');
      }

      const response = await sendMessage(messageContent, sessionId, jwtToken);
      addMessage(response.message, 'system');
    } catch (err) {
      const errorMessage = err instanceof Error
        ? err.message
        : 'An unexpected error occurred while sending your message';

      setError(errorMessage);
      addMessage(`Error: ${errorMessage}. Please try again.`, 'system');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <div className="flex flex-col h-screen max-w-5xl mx-auto w-full">
        <ChatHeader />

        {error && (
          <div className="bg-red-100 border-l-4 border-red-500 text-red-700 px-4 py-3" role="alert">
            <p className="font-medium">Error</p>
            <p className="text-sm">{error}</p>
          </div>
        )}

        <ChatMessages messages={messages} isLoading={isLoading} />
        <ChatInput onSendMessage={handleSendMessage} isLoading={isLoading} />
      </div>
    </div>
  );
};

export default ChatContainer;
