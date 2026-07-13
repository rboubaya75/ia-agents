import { v4 as uuidv4 } from 'uuid';
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

export type AccessTokenProvider = () => Promise<string>;

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

const invokeAgent = (
  prompt: string,
  sessionId: string,
  operationId: string,
  accessToken: string,
  signal: AbortSignal,
): Promise<Response> => fetch(getAgentInvokeEndpoint(), {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    prompt,
    sessionId,
    operationId,
  }),
  signal,
});

export const sendMessage = async (
  message: string,
  sessionId: string,
  getAccessToken: AccessTokenProvider,
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

  const operationId = uuidv4();
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    let accessToken = await getAccessToken();
    if (!accessToken) {
      throw new Error('Authentication token is required');
    }

    let response = await invokeAgent(prompt, sessionId, operationId, accessToken, controller.signal);

    if (response.status === 401) {
      accessToken = await getAccessToken();
      if (!accessToken) {
        throw new Error('Authentication token renewal failed');
      }
      response = await invokeAgent(prompt, sessionId, operationId, accessToken, controller.signal);
    }

    if (!response.ok) {
      const messageText = await getErrorMessage(response);
      throw new Error(`${messageText} (${response.status})`);
    }

    const contentType = response.headers.get('content-type');
    let responseText: string;

    if (contentType?.includes('application/json')) {
      const data: unknown = await response.json();
      if (typeof data !== 'object' || data === null) {
        throw new Error(GENERIC_AGENT_ERROR);
      }
      const payload = data as {
        message?: unknown;
        output?: { message?: unknown };
        response?: unknown;
      };
      const candidate = payload.message ?? payload.output?.message ?? payload.response;
      if (typeof candidate !== 'string' || !candidate.trim()) {
        throw new Error(GENERIC_AGENT_ERROR);
      }
      responseText = candidate.trim();
    } else {
      responseText = (await response.text()).trim();
      if (!responseText) {
        throw new Error(GENERIC_AGENT_ERROR);
      }
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
