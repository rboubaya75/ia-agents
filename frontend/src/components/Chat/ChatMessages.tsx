import React, { useEffect, useRef } from 'react';
import type { Message as MessageType } from '../../types';
import Message from './Message';
import TypingIndicator from './TypingIndicator';

interface ChatMessagesProps {
  messages: MessageType[];
  isLoading?: boolean;
  /** Texte en cours de diffusion, rendu tant que l'événement terminal n'est pas reçu. */
  pendingContent?: string;
}

const PENDING_MESSAGE_ID = '__streaming__';

const ChatMessages: React.FC<ChatMessagesProps> = ({
  messages,
  isLoading = false,
  pendingContent = '',
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, pendingContent]);

  const isEmpty = messages.length === 0 && pendingContent === '';

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {isEmpty ? (
        <div className="flex items-center justify-center h-full text-gray-500">
          <p>Start a conversation by sending a message below</p>
        </div>
      ) : (
        <>
          {messages.map((message) => (
            <Message key={message.id} message={message} />
          ))}
          {/*
            `aria-live` est délibérément absent : une annonce par fragment rendrait la
            diffusion inutilisable au lecteur d'écran. L'annonce unique de fin est portée
            par StreamStatus (V2-LLD-010 §13.1).
          */}
          {pendingContent !== '' && (
            <Message
              message={{
                id: PENDING_MESSAGE_ID,
                content: pendingContent,
                sender: 'system',
                timestamp: new Date(),
              }}
            />
          )}
          {isLoading && pendingContent === '' && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </>
      )}
    </div>
  );
};

export default ChatMessages;
