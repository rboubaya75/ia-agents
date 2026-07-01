import type { ChatResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.NEXT_PUBLIC_API_BASE_URL;
const REQUEST_TIMEOUT = 120000;

const getAgentInvokeEndpoint = (): string => {
  if (!API_BASE_URL) {
    throw new Error('API base URL is not configured. Please set VITE_API_BASE_URL.');
  }

  return `${API_BASE_URL.replace(/\/$/, '')}/agent/invoke`;
};

export const sendMessage = async (
  message: string,
  sessionId: string,
  accessToken: string
): Promise<ChatResponse> => {
  if (!message.trim()) {
    throw new Error('Message cannot be empty');
  }

  if (!sessionId || sessionId.length < 33) {
    throw new Error('Invalid session ID: must be at least 33 characters');
  }

  if (!accessToken) {
    throw new Error('Authentication token is required');
  }

  const endpoint = getAgentInvokeEndpoint();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        Authorization: ['Bearer', accessToken].join(' '),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: message,
        sessionId,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(
        `Agent API request failed: ${response.status} ${response.statusText}. ${errorText}`
      );
    }

    const contentType = response.headers.get('content-type');

    let responseText: string;
    if (contentType?.includes('application/json')) {
      const data = await response.json();
      responseText = data.message || data.output?.message || data.response || JSON.stringify(data);
    } else {
      responseText = await response.text();
    }

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
        throw new Error('Request timed out after 120 seconds');
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
