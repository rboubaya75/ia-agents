/**
 * ChatHeader Component
 * Displays the Wildrydes branding, User ID, Session ID, and New Chat button
 * Requirements: 2.2, 4.1, 4.2, 4.3, 3.3
 */

import React from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useChatContext } from '../../contexts/ChatContext';

export const ChatHeader: React.FC = () => {
  const { userId, logout } = useAuth();
  const { sessionId, createNewSession } = useChatContext();

  /**
   * Handle New Chat button click
   * Creates a new session and clears messages
   */
  const handleNewChat = () => {
    createNewSession();
  };

  /**
   * Handle Sign Out button click
   * Logs out the user and clears authentication state
   */
  const handleSignOut = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Error signing out:', error);
    }
  };

  return (
    <header className="bg-gray-800 text-white px-6 py-4 shadow-lg">
      <div className="flex items-center justify-between">
        {/* Branding */}
        <div className="flex items-center space-x-2">
          <h1 className="text-2xl font-bold">🦄 Wildrydes</h1>
        </div>

        {/* User ID and Session ID Display */}
        <div className="flex items-center space-x-6 text-sm">
          <div className="flex items-center space-x-2">
            <span className="text-gray-400">User ID:</span>
            <span className="font-mono bg-gray-700 px-2 py-1 rounded">
              {userId || 'N/A'}
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-gray-400">Session:</span>
            <span className="font-mono bg-gray-700 px-2 py-1 rounded text-xs">
              {sessionId}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center space-x-3">
          <button
            onClick={handleNewChat}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold px-4 py-2 rounded transition-colors duration-200"
            aria-label="Start a new chat"
          >
            New Chat
          </button>
          <button
            onClick={handleSignOut}
            className="bg-red-600 hover:bg-red-700 text-white font-semibold px-4 py-2 rounded transition-colors duration-200"
            aria-label="Sign out"
          >
            Sign Out
          </button>
        </div>
      </div>
    </header>
  );
};

export default ChatHeader;
