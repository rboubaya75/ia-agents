import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { Message as MessageType } from '../../types';

interface MessageProps {
  message: MessageType;
}

const Message: React.FC<MessageProps> = ({ message }) => {
  const isUser = message.sender === 'user';
  
  const formatTimestamp = (date: Date): string => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Preprocess content to handle escaped characters
  const processContent = (content: string): string => {
    return content
      .replace(/\\n/g, '\n')    // Convert \n to actual newlines
      .replace(/\\t/g, '\t')    // Convert \t to actual tabs
      .replace(/\\r/g, '\r');   // Convert \r to carriage returns
  };

  return (
    <div className={`flex mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[70%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-blue-500 text-white'
            : 'bg-gray-200 text-gray-900'
        }`}
      >
        <div className="prose prose-sm max-w-none break-words">
          <ReactMarkdown
            components={{
              // Style headings
              h1: ({node, ...props}) => <h1 className={`text-2xl font-bold mb-2 ${isUser ? 'text-white' : 'text-gray-900'}`} {...props} />,
              h2: ({node, ...props}) => <h2 className={`text-xl font-bold mb-2 ${isUser ? 'text-white' : 'text-gray-900'}`} {...props} />,
              h3: ({node, ...props}) => <h3 className={`text-lg font-bold mb-1 ${isUser ? 'text-white' : 'text-gray-900'}`} {...props} />,
              // Style lists
              ul: ({node, ...props}) => <ul className="list-disc ml-4 my-2" {...props} />,
              ol: ({node, ...props}) => <ol className="list-decimal ml-4 my-2" {...props} />,
              li: ({node, ...props}) => <li className="mb-1" {...props} />,
              // Style paragraphs
              p: ({node, ...props}) => <p className="mb-2 last:mb-0" {...props} />,
              // Style strong/bold
              strong: ({node, ...props}) => <strong className="font-bold" {...props} />,
              // Style code
              code: ({node, ...props}) => <code className={`px-1 py-0.5 rounded ${isUser ? 'bg-blue-600' : 'bg-gray-300'}`} {...props} />,
            }}
          >
            {processContent(message.content)}
          </ReactMarkdown>
        </div>
        {message.timestamp && (
          <div
            className={`text-xs mt-1 ${
              isUser ? 'text-blue-100' : 'text-gray-500'
            }`}
          >
            {formatTimestamp(message.timestamp)}
          </div>
        )}
      </div>
    </div>
  );
};

export default Message;
