import React from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
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

  const processContent = (content: string): string => {
    return content
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t')
      .replace(/\\r/g, '\r');
  };

  const components: Components = {
    h1: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <h1 className={`text-2xl font-bold mb-2 ${isUser ? 'text-white' : 'text-gray-900'}`} {...elementProps} />;
    },
    h2: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <h2 className={`text-xl font-bold mb-2 ${isUser ? 'text-white' : 'text-gray-900'}`} {...elementProps} />;
    },
    h3: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <h3 className={`text-lg font-bold mb-1 ${isUser ? 'text-white' : 'text-gray-900'}`} {...elementProps} />;
    },
    ul: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <ul className="list-disc ml-4 my-2" {...elementProps} />;
    },
    ol: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <ol className="list-decimal ml-4 my-2" {...elementProps} />;
    },
    li: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <li className="mb-1" {...elementProps} />;
    },
    p: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <p className="mb-2 last:mb-0" {...elementProps} />;
    },
    strong: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <strong className="font-bold" {...elementProps} />;
    },
    code: (props) => {
      const { node, ...elementProps } = props;
      void node;
      return <code className={`px-1 py-0.5 rounded ${isUser ? 'bg-blue-600' : 'bg-gray-300'}`} {...elementProps} />;
    },
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
          <ReactMarkdown components={components}>
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
