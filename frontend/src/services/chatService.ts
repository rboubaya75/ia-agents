import type { ChatResponse } from '../types';

const AGENT_ARN = import.meta.env.VITE_AGENT_ARN || import.meta.env.NEXT_PUBLIC_AGENT_ARN;
const REQUEST_TIMEOUT = 120000;

/**
 * Construct the AgentCore endpoint URL from the agent ARN
 * Format: https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{URL_ENCODED_ARN}/invocations
 */
const getAgentCoreEndpoint = (): string => {
  if (!AGENT_ARN) {
    throw new Error('Agent ARN is not configured. Please set VITE_AGENT_ARN in .env.local');
  }

  // Parse ARN to get region: arn:aws:bedrock-agentcore:region:account:runtime/agentId
  const arnParts = AGENT_ARN.split(':');
  if (arnParts.length < 6) {
    throw new Error('Invalid Agent ARN format');
  }

  const region = arnParts[3];
  
  // URL encode the ARN (required by the API)
  const encodedArn = encodeURIComponent(AGENT_ARN);

  return `https://bedrock-agentcore.${region}.amazonaws.com/runtimes/${encodedArn}/invocations`;
};

/**
 * Send a message to AgentCore Runtime and receive a response
 * @param message - The user's message content
 * @param sessionId - The current session ID (must be 33+ characters)
 * @param actorId - The user's unique identifier (for memory isolation)
 * @param jwtToken - The JWT token from Cognito authentication
 * @returns Promise resolving to the chat response
 * @throws Error if the request fails or times out
 */
export const sendMessage = async (
  message: string,
  sessionId: string,
  actorId: string,
  jwtToken: string
): Promise<ChatResponse> => {
  if (!message.trim()) {
    throw new Error('Message cannot be empty');
  }

  if (!sessionId || sessionId.length < 33) {
    throw new Error('Invalid session ID: must be at least 33 characters');
  }

  if (!actorId) {
    throw new Error('Actor ID is required');
  }

  if (!jwtToken) {
    throw new Error('JWT token is required');
  }

  // Get the AgentCore endpoint URL
  const endpoint = getAgentCoreEndpoint();

  // Create abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${jwtToken}`,
        'Content-Type': 'application/json',
        'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': sessionId,
      },
      body: JSON.stringify({
        prompt: message,
        sessionId: sessionId,  // Include session ID in body for backend compatibility
        actorId: actorId,      // Include actor ID for memory isolation
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(
        `AgentCore request failed: ${response.status} ${response.statusText}. ${errorText}`
      );
    }

    // AgentCore returns the response directly as text or JSON
    const contentType = response.headers.get('content-type');
    
    let responseText: string;
    if (contentType?.includes('application/json')) {
      const data = await response.json();
      // Handle different possible response formats
      responseText = data.message || data.output?.message || JSON.stringify(data);
    } else {
      responseText = await response.text();
    }

    // Strip surrounding quotes if present (from JSON string responses)
    if (responseText.startsWith('"') && responseText.endsWith('"')) {
      responseText = responseText.slice(1, -1);
    }

    return {
      message: responseText,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new Error('Request timed out after 30 seconds');
      }
      throw error;
    }

    throw new Error('An unexpected error occurred while sending message');
  }
};

const chatService = {
  sendMessage,
};

export default chatService;
