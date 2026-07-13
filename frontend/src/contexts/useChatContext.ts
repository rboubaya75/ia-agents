import { useContext } from 'react';
import ChatContext, { type ChatContextType } from './ChatContext';

export const useChatContext = (): ChatContextType => {
  const context = useContext(ChatContext);

  if (context === undefined) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }

  return context;
};
