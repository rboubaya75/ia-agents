import { v4 as uuidv4 } from 'uuid';

/**
 * Session Management Service
 * 
 * Manages session IDs for chat conversations.
 * AgentCore requires session IDs to be 33+ characters.
 * UUID v4 format generates 36 characters (including hyphens), meeting this requirement.
 */

let currentSessionId: string | null = null;

/**
 * Generates a new session ID using UUID v4
 * @returns A unique session ID (36 characters, meets 33+ requirement)
 */
export const generateSessionId = (): string => {
  return uuidv4();
};

/**
 * Gets the current session ID
 * @returns The current session ID or null if no session exists
 */
export const getCurrentSessionId = (): string | null => {
  return currentSessionId;
};

/**
 * Creates a new session and returns the session ID
 * @returns The newly created session ID
 */
export const createNewSession = (): string => {
  currentSessionId = generateSessionId();
  return currentSessionId;
};
