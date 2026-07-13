import { v4 as uuidv4 } from 'uuid';
import type { ChatResponse } from '../types';

const AGENT_INVOKE_URL =
  import.meta.env.VITE_AGENT_INVOKE_URL || import.meta.env.NEXT_PUBLIC_AGENT_INVOKE_URL;
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.NEXT_PUBLIC_API_BASE_URL;
const REQUEST_TIMEOUT = 35000;
const SESSION_ID_PATTERN = /^[A-Za-z0-9._:-]{33,128}$/;
const OPERATION_ID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/;
const MAX_PROMPT_LENGTH = 4000;
const GENERIC_AGENT_ERROR = 'The agent request could not be completed.';

type AgentErrorPayload = {
  message?: unknown;
  requestId?: unknown;
};

type AgentErrorDetails = {
  message: string;
  requestId?: string;
};

export type AccessTokenProvider = () => Promise<string>;

export class AgentRequestError extends Error {
  readonly operationId: string;
  readonly retryable: boolean;
  readonly requestId?: string;
  readonly status?: number;

  constructor(
    message: string,
    operationId: string,
    retryable: boolean,
    options: { requestId?: string; status?: number } = {},
  ) {
    super(message);
    this.name = 'AgentRequestError';
    this.operationId = operationId;
    this.retryable = retryable;
    this.requestId = options.requestId;
    this.status = options.status;
  }
}

const getAgentInvokeEndpoint = (): string => {
  if (AGENT_INVOKE_URL) {
    return AGENT_INVOKE_URL;
  }

  if (!API_BASE_URL) {
    throw new Error('Agent API URL is not configured.');
  }

  return `${API_BASE_URL.replace(/\/$/, '')}/agent/invoke`;
};

const getErrorDetails = async (response: Response): Promise<AgentErrorDetails> => {
  const contentType = response.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    const payload: AgentErrorPayload | null = await response.json().catch(() => null);
    if (payload) {
      const message = typeof payload.message === 'string' ? payload.message : GENERIC_AGENT_ERROR;
      const requestId =
        typeof payload.requestId === 'string' && payload.requestId ? payload.requestId : undefined;
      const messageWithReference = requestId
        ? `${message} Reference: ${payload.requestId}.`
        : message;
      return { message: messageWithReference, requestId };
    }
  }
  return { message: GENERIC_AGENT_ERROR };
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

const isAmbiguousStatus = (status: number): boolean =>
  status === 408 || status === 425 || status === 429 || status >= 500;

export const sendMessage = async (
  message: string,
  sessionId: string,
  getAccessToken: AccessTokenProvider,
  existingOperationId?: string,
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

  const operationId = existingOperationId ?? uuidv4();
  if (!OPERATION_ID_PATTERN.test(operationId)) {
    throw new Error('Invalid operation ID');
  }

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
      const details = await getErrorDetails(response);
      throw new AgentRequestError(
        `${details.message} (${response.status})`,
        operationId,
        isAmbiguousStatus(response.status),
        { requestId: details.requestId, status: response.status },
      );
    }

    const contentType = response.headers.get('content-type');
    let responseText: string;
    let responseOperationId = operationId;
    let requestId: string | undefined;

    if (contentType?.includes('application/json')) {
      const data: unknown = await response.json();
      if (typeof data !== 'object' || data === null) {
        throw new AgentRequestError(GENERIC_AGENT_ERROR, operationId, true);
      }
      const payload = data as {
        message?: unknown;
        output?: { message?: unknown };
        response?: unknown;
        operationId?: unknown;
        requestId?: unknown;
      };
      const candidate = payload.message ?? payload.output?.message ?? payload.response;
      if (typeof candidate !== 'string' || !candidate.trim()) {
        throw new AgentRequestError(GENERIC_AGENT_ERROR, operationId, true);
      }
      responseText = candidate.trim();
      if (typeof payload.operationId === 'string' && OPERATION_ID_PATTERN.test(payload.operationId)) {
        responseOperationId = payload.operationId;
      }
      if (typeof payload.requestId === 'string' && payload.requestId) {
        requestId = payload.requestId;
      }
    } else {
      responseText = (await response.text()).trim();
      if (!responseText) {
        throw new AgentRequestError(GENERIC_AGENT_ERROR, operationId, true);
      }
    }

    return {
      message: responseText,
      timestamp: new Date().toISOString(),
      operationId: responseOperationId,
      requestId,
    };
  } catch (error) {
    if (error instanceof AgentRequestError) {
      throw error;
    }
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new AgentRequestError('Request timed out', operationId, true);
      }
      if (error instanceof TypeError) {
        throw new AgentRequestError('Network request failed', operationId, true);
      }
      throw error;
    }
    throw new AgentRequestError(
      'An unexpected error occurred while sending the message',
      operationId,
      true,
    );
  } finally {
    window.clearTimeout(timeoutId);
  }
};

const chatService = {
  sendMessage,
};

export default chatService;
