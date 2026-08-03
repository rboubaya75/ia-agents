/**
 * Transport du flux conversationnel (V2-LLD-010 §5.2) et annulation (§6.2).
 *
 * `fetch` + `ReadableStream` plutôt qu'`EventSource` : ce dernier n'accepte aucun en-tête
 * personnalisé, et le seul moyen de lui présenter un jeton serait de le placer dans
 * l'URL — donc dans l'historique, le `Referer` et les journaux d'accès, ce que
 * `V2-LLD-005 §2.2` refuse (§1.7, écart 1). Ce choix impose de réécrire ce
 * qu'`EventSource` fournissait : le découpage des événements (`sseParser`) et la
 * détection de coupure (ci-dessous).
 */

import { SseParser } from '../lib/sseParser';
import { toStreamEvent } from '../lib/streamEvents';
import { getRuntimeConfig } from '../lib/runtimeConfig';
import { SessionExpiredError } from '../lib/authErrors';
import { isTerminalEvent, type StreamEvent, type TerminalStreamEvent } from '../types/stream';

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '';

export type AccessTokenProvider = (options?: { forceRefresh?: boolean }) => Promise<string>;

export class StreamTransportError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'StreamTransportError';
    this.status = status;
  }
}

export type StreamOutcome =
  | { kind: 'terminal'; event: TerminalStreamEvent }
  /** Flux coupé sans événement terminal — appelle un rattachement, jamais une réémission (§5.5). */
  | { kind: 'truncated'; reason: 'closed' | 'idle' };

const apiUrl = (path: string): string => {
  if (!API_BASE_URL) {
    throw new Error('VITE_API_BASE_URL n\'est pas configurée.');
  }
  return `${API_BASE_URL.replace(/\/$/, '')}${path}`;
};

const authHeaders = (accessToken: string): Record<string, string> => ({
  Authorization: `Bearer ${accessToken}`,
  'Content-Type': 'application/json',
});

/**
 * Émet la requête, avec **un seul** renouvellement sur 401 puis une seule réémission.
 * Jamais de boucle : réessayer indéfiniment sur une session morte produirait des appels
 * que le quota par identité de `V2-ADR-016` finirait par compter contre l'utilisateur.
 */
const fetchWithSingleRenewal = async (
  url: string,
  init: Omit<RequestInit, 'headers'>,
  getAccessToken: AccessTokenProvider,
  extraHeaders: Record<string, string> = {},
): Promise<Response> => {
  const first = await fetch(url, {
    ...init,
    headers: { ...authHeaders(await getAccessToken()), ...extraHeaders },
  });
  if (first.status !== 401) {
    return first;
  }

  const renewed = await fetch(url, {
    ...init,
    headers: { ...authHeaders(await getAccessToken({ forceRefresh: true })), ...extraHeaders },
  });
  if (renewed.status === 401) {
    throw new SessionExpiredError();
  }
  return renewed;
};

export interface StreamMessageOptions {
  conversationId: string;
  message: string;
  getAccessToken: AccessTokenProvider;
  /**
   * N'abandonner le `fetch` qu'**après** l'événement terminal, ou au démontage du
   * composant. L'abandonner au geste d'annulation couperait le canal par lequel
   * l'annulation doit être confirmée (§6.2).
   */
  signal: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}

export const streamMessage = async (
  options: StreamMessageOptions,
): Promise<StreamOutcome> => {
  const { conversationId, message, getAccessToken, signal, onEvent } = options;

  const response = await fetchWithSingleRenewal(
    apiUrl(`/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`),
    { method: 'POST', body: JSON.stringify({ message }), signal },
    getAccessToken,
    { Accept: 'text/event-stream' },
  );

  if (!response.ok) {
    throw new StreamTransportError(
      `Le flux n'a pas pu être ouvert (${response.status}).`,
      response.status,
    );
  }
  if (!response.body) {
    throw new StreamTransportError('Le flux ne porte aucun corps de réponse.', response.status);
  }

  const reader = response.body.getReader();
  const parser = new SseParser();
  const idleTimeoutMs = getRuntimeConfig().streamIdleTimeoutSeconds * 1000;
  let terminal: TerminalStreamEvent | null = null;

  const consume = (frames: ReturnType<SseParser['push']>): TerminalStreamEvent | null => {
    for (const frame of frames) {
      const event = toStreamEvent(frame);
      if (!event) {
        continue;
      }
      onEvent(event);
      if (isTerminalEvent(event)) {
        return event;
      }
    }
    return null;
  };

  try {
    for (;;) {
      // Sans `EventSource`, l'absence prolongée de `: ping` est le seul signal d'un flux
      // mort dont la connexion TCP tient encore. La borne est dérivée du keep-alive
      // serveur, pas choisie indépendamment (§5.5).
      let idleTimer: ReturnType<typeof setTimeout> | undefined;
      const idle = new Promise<'idle'>((resolve) => {
        idleTimer = setTimeout(() => resolve('idle'), idleTimeoutMs);
      });

      let result: Awaited<ReturnType<typeof reader.read>> | 'idle';
      try {
        result = await Promise.race([reader.read(), idle]);
      } finally {
        clearTimeout(idleTimer);
      }

      if (result === 'idle') {
        await reader.cancel().catch(() => undefined);
        return { kind: 'truncated', reason: 'idle' };
      }

      if (result.done) {
        terminal = consume(parser.flush()) ?? terminal;
        break;
      }

      terminal = consume(parser.push(result.value));
      if (terminal) {
        break;
      }
    }
  } finally {
    reader.releaseLock?.();
  }

  return terminal
    ? { kind: 'terminal', event: terminal }
    : { kind: 'truncated', reason: 'closed' };
};

export type CancelOutcome = 'requested' | 'unknown';

/**
 * Annuler, c'est appeler cette route — fermer l'onglet ou abandonner le `fetch`
 * n'annule rien de garanti (§6.1).
 *
 * FastAPI répond 404 aussi bien pour une opération inconnue que pour une opération
 * appartenant à un autre acteur : les distinguer offrirait un oracle d'existence. Le
 * client ne peut donc pas — et ne doit pas — les présenter différemment.
 */
export const cancelOperation = async (
  operationId: string,
  getAccessToken: AccessTokenProvider,
): Promise<CancelOutcome> => {
  const response = await fetchWithSingleRenewal(
    apiUrl(`/api/v1/operations/${encodeURIComponent(operationId)}/cancel`),
    { method: 'POST' },
    getAccessToken,
  );

  if (response.status === 404 || response.status === 403) {
    return 'unknown';
  }
  if (!response.ok) {
    throw new StreamTransportError(
      `L'annulation n'a pas pu être demandée (${response.status}).`,
      response.status,
    );
  }
  return 'requested';
};
