/**
 * ChatContainer Component
 * Main orchestrator for the chat interface
 */

import React from 'react';
import { v4 as uuidv4 } from 'uuid';
import { useChatContext } from '../../contexts/useChatContext';
import { useAuth } from '../../contexts/useAuth';
import { AgentRequestError, sendMessage } from '../../services/chatService';
import ChatHeader from './ChatHeader';
import ChatMessages from './ChatMessages';
import ChatInput from './ChatInput';

type PendingOperationMap = Record<string, string>;

const pendingStorageKey = (sessionId: string): string =>
  `agent-pending-operations:${sessionId}`;

const readPendingOperations = (sessionId: string): PendingOperationMap => {
  try {
    const raw = window.sessionStorage.getItem(pendingStorageKey(sessionId));
    if (!raw) {
      return {};
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).filter(
        ([fingerprint, operationId]) =>
          fingerprint.length === 64 && typeof operationId === 'string',
      ),
    );
  } catch {
    return {};
  }
};

const writePendingOperations = (
  sessionId: string,
  pendingOperations: PendingOperationMap,
): void => {
  try {
    const key = pendingStorageKey(sessionId);
    if (Object.keys(pendingOperations).length === 0) {
      window.sessionStorage.removeItem(key);
      return;
    }
    window.sessionStorage.setItem(key, JSON.stringify(pendingOperations));
  } catch {
    // The current attempt remains safe; persistence across a page refresh is best effort.
  }
};

const messageFingerprint = async (sessionId: string, message: string): Promise<string> => {
  const value = new TextEncoder().encode(`${sessionId}\u0000${message}`);
  const digest = await window.crypto.subtle.digest('SHA-256', value);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
};

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

  const { getValidAccessToken } = useAuth();

  const handleSendMessage = async (messageContent: string) => {
    const normalizedMessage = messageContent.trim();
    setError(null);
    setLoading(true);

    let fingerprint: string | null = null;
    let pendingOperations: PendingOperationMap = {};

    try {
      fingerprint = await messageFingerprint(sessionId, normalizedMessage);
      pendingOperations = readPendingOperations(sessionId);
      const existingOperationId = pendingOperations[fingerprint];
      const operationId = existingOperationId ?? uuidv4();
      pendingOperations[fingerprint] = operationId;
      writePendingOperations(sessionId, pendingOperations);

      if (!existingOperationId) {
        addMessage(normalizedMessage, 'user');
      }

      const response = await sendMessage(
        normalizedMessage,
        sessionId,
        getValidAccessToken,
        operationId,
      );

      delete pendingOperations[fingerprint];
      writePendingOperations(sessionId, pendingOperations);
      addMessage(response.message, 'system');
    } catch (err) {
      if (err instanceof AgentRequestError && err.retryable && fingerprint) {
        pendingOperations[fingerprint] = err.operationId;
        writePendingOperations(sessionId, pendingOperations);
      } else if (fingerprint) {
        delete pendingOperations[fingerprint];
        writePendingOperations(sessionId, pendingOperations);
      }

      const baseMessage = err instanceof Error
        ? err.message
        : 'An unexpected error occurred while sending your message';
      const retryHint = err instanceof AgentRequestError && err.retryable
        ? ' Retry the same message; its operation identifier will be reused.'
        : '';
      const errorMessage = `${baseMessage}${retryHint}`;

      setError(errorMessage);
      addMessage(`Error: ${errorMessage}`, 'system');
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
