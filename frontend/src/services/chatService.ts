import type { ChatResponse } from '../types';

const AGENT_INVOKE_URL =
  import.meta.env.VITE_AGENT_INVOKE_URL || import.meta.env.NEXT_PUBLIC_AGENT_INVOKE_URL;
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.NEXT_PUBLIC_API_BASE_URL;
const REQUEST_TIMEOUT = 35000;
const SESSION_ID_PATTERN = /^[A-Za-z0-9._:-]{33,128}$/;
const MAX_PROMPT_LENGTH = 4000;
const GENERIC_AGENT_ERROR = 'The agent request could not be completed.';

type AgentErrorPayload = {
  message?: unknown;
  requestId?: unknown;
};

const getAgentInvokeEndpoint = (): string => {
  if (AGENT_INVOKE_URL) {
    return AGENT_INVOKE_URL;
  }

  if (!API_BASE_URL) {
    throw new Error('Agent API URL is not configured.');
  }

  return `${API_BASE_URL.replace(/\/$/, '')}/agent/invoke`;
};

const getErrorMessage = async (response: Response): Promise<string> => {
  const contentType = response.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    const payload: AgentErrorPayload | null = await response.json().catch(() => null);
    if (payload) {
      const message = typeof payload.message === 'string' ? payload.message : GENERIC_AGENT_ERROR;
      if (typeof payload.requestId === 'string' && payload.requestId) {
        return `${message} Reference: ${payload.requestId}.`;
      }
      return message;
    }
  }
  return GENERIC_AGENT_ERROR;
};

export const sendMessage = async (
  message: string,
  sessionId: string,
  accessToken: string
): Promise<ChatResponse> => {
  const prompt = message.trim();
  if (!prompt) {
    throw new Error('Message cannot be empty');
  }
  if (prompt.length > MAX_PROMPT_LENGTH) {
    throw new Error(`Message cannot exceed ${MAX_PROMPT_LENGTH} characters`);
  }
  if (!SESSION_ID_PATTERN.test(sessionId)) {
    throw new Error('Invalid session ID');
  }
  if (!accessToken) {
    throw new Error('Authentication token is required');
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    const response = await fetch(getAgentInvokeEndpoint(), {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt,
        sessionId,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const messageText = await getErrorMessage(response);
      throw new Error(`${messageText} (${response.status})`);
    }

    const contentType = response.headers.get('content-type');
    let responseText: string;

    if (contentType?.includes('application/json')) {
      const data = await response.json();
      responseText = data.message || data.output?.message || data.response || JSON.stringify(data);
    } else {
      responseText = await response.text();
    }

    return {
      message: responseText,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new Error('Request timed out');
      }
      throw error;
    }
    throw new Error('An unexpected error occurred while sending the message');
  } finally {
    window.clearTimeout(timeoutId);
  }
};

const chatService = {
  sendMessage,
};

export default chatService;
