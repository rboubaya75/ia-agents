/**
 * Orchestrateur de l'interface conversationnelle.
 *
 * Le chemin V2 est le flux SSE de `V2-LLD-010 §5` : `POST /api/v1/conversations/{id}/messages`
 * lu par `fetch` + `ReadableStream`. Le service V1 (`chatService`, requête/réponse sur
 * `/agent/invoke`) reste dans l'arbre mais n'est plus appelé d'ici.
 *
 * La carte `fingerprint → operationId` de la V1 disparaît : son intention — ne jamais
 * réémettre une mutation dont l'issue est inconnue — est conservée, mais l'`operationId`
 * vient désormais du serveur par l'événement `meta` plutôt que d'une empreinte calculée
 * par le client (§1.5, §10.2).
 */

import React, { useEffect, useRef } from 'react';
import { useChatContext } from '../../contexts/useChatContext';
import { useOperation } from '../../contexts/useOperation';
import ChatHeader from './ChatHeader';
import ChatMessages from './ChatMessages';
import ChatInput from './ChatInput';
import StreamStatus from './StreamStatus';

export const ChatContainer: React.FC = () => {
  const { messages, sessionId, addMessage } = useChatContext();
  const { operation, send, requestCancel, reset } = useOperation();
  const settledRef = useRef<string | null>(null);

  // Une terminaison fige le message : le texte diffusé rejoint l'historique, et l'état
  // d'opération reste affiché par StreamStatus jusqu'au tour suivant.
  useEffect(() => {
    const settled =
      operation.state === 'done' ||
      operation.state === 'cancelled' ||
      operation.state === 'unknown_outcome';
    if (!settled || operation.text === '') {
      return;
    }
    const marker = `${operation.operationId ?? 'sans-id'}:${operation.state}`;
    if (settledRef.current === marker) {
      return;
    }
    settledRef.current = marker;
    addMessage(operation.text, 'system');
  }, [operation.state, operation.text, operation.operationId, addMessage]);

  const handleSendMessage = async (messageContent: string) => {
    const normalized = messageContent.trim();
    if (!normalized) {
      return;
    }
    reset();
    settledRef.current = null;
    addMessage(normalized, 'user');
    await send(sessionId, normalized);
  };

  const isBusy = operation.state === 'streaming' || operation.state === 'cancel_requested';
  // Tant que la terminaison n'est pas figée dans l'historique, le texte reste rendu comme
  // message en cours.
  const pendingContent = isBusy ? operation.text : '';

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <div className="flex flex-col h-screen max-w-5xl mx-auto w-full">
        <ChatHeader />

        <ChatMessages messages={messages} isLoading={isBusy} pendingContent={pendingContent} />

        <StreamStatus operation={operation} onCancel={requestCancel} />

        <ChatInput onSendMessage={handleSendMessage} isLoading={isBusy} />
      </div>
    </div>
  );
};

export default ChatContainer;
