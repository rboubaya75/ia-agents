/**
 * Traduction des trames SSE en événements typés (V2-LLD-010 §5.4).
 *
 * Règle unique et non négociable : **un événement inconnu est ignoré et journalisé,
 * jamais une rupture du flux** (§5.3). Le jeu d'événements est amené à s'étendre —
 * `command` et `citation` arrivent avec les lots serveur suivants — et un client qui
 * échouerait sur un `event:` qu'il ne connaît pas rendrait toute extension serveur
 * incompatible avec les clients déjà déployés.
 */

import type { SseFrame } from './sseParser';
import type {
  CancellationCause,
  Citation,
  StreamEvent,
  StreamingMode,
} from '../types/stream';

const STREAMING_MODES: readonly string[] = ['native', 'emulated'];
const CANCELLATION_CAUSES: readonly string[] = ['client', 'deadline', 'operator'];

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const asString = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback;

const asNumber = (value: unknown): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : 0;

const asBoolean = (value: unknown): boolean => value === true;

const asCitations = (value: unknown): Citation[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((entry) => {
    const record = asRecord(entry);
    return {
      documentId: typeof record.documentId === 'string' ? record.documentId : undefined,
      title: typeof record.title === 'string' ? record.title : undefined,
      excerpt: typeof record.excerpt === 'string' ? record.excerpt : undefined,
      uri: typeof record.uri === 'string' ? record.uri : undefined,
    };
  });
};

/**
 * Journalise un rejet sans jamais reproduire la charge utile : celle-ci porte le texte
 * de la conversation, que le §12.5 interdit de journaliser.
 */
const reportIgnored = (reason: string, eventName: string | null): void => {
  console.warn(`[sse] ${reason}`, { event: eventName ?? '(sans nom)' });
};

export const toStreamEvent = (frame: SseFrame): StreamEvent | null => {
  if (frame.comment !== null && frame.event === null && frame.data === '') {
    // `: ping` — réarme le détecteur d'inactivité (§5.5), aucun effet visible.
    return { type: 'ping' };
  }

  if (frame.event === null) {
    reportIgnored('trame sans nom d\'événement ignorée', null);
    return null;
  }

  let payload: Record<string, unknown> = {};
  if (frame.data !== '') {
    try {
      payload = asRecord(JSON.parse(frame.data));
    } catch {
      reportIgnored('charge utile illisible, trame ignorée', frame.event);
      return null;
    }
  }

  switch (frame.event) {
    case 'meta': {
      const mode = asString(payload.streaming);
      return {
        type: 'meta',
        // Un mode non reconnu est traité comme `emulated` : c'est le repli assumé,
        // et le supposer `native` masquerait une dégradation (§5.1).
        streaming: (STREAMING_MODES.includes(mode) ? mode : 'emulated') as StreamingMode,
        operationId: asString(payload.operationId),
      };
    }

    case 'delta':
      return { type: 'delta', text: asString(payload.text) };

    case 'citation':
      return { type: 'citation', citations: asCitations(payload.citations) };

    case 'done':
      return {
        type: 'done',
        answer: asString(payload.answer),
        turnCount: asNumber(payload.turnCount),
        inputTokens: asNumber(payload.inputTokens),
        outputTokens: asNumber(payload.outputTokens),
        toolCallsCount: asNumber(payload.toolCallsCount),
        budgetExhausted: asBoolean(payload.budgetExhausted),
        degraded: asBoolean(payload.degraded),
        servedInvocationId: asString(payload.servedInvocationId),
      };

    case 'cancelled': {
      const cause = asString(payload.cause);
      return {
        type: 'cancelled',
        cause: (CANCELLATION_CAUSES.includes(cause) ? cause : 'client') as CancellationCause,
        inputTokens: asNumber(payload.inputTokens),
        outputTokens: asNumber(payload.outputTokens),
      };
    }

    case 'error':
      return {
        type: 'error',
        code: asString(payload.code, 'unknown'),
        message: asString(payload.message),
      };

    default:
      // `command` (§7) et tout événement ajouté par un lot serveur ultérieur passent
      // ici tant que ce client ne les gère pas. Le flux continue.
      reportIgnored('événement inconnu ignoré', frame.event);
      return null;
  }
};
