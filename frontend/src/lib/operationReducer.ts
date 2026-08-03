/**
 * État d'une invocation conversationnelle (V2-LLD-010 §2.3).
 *
 * Réducteur pur : c'est ce qui rend vérifiables les règles que le LLD pose sur la
 * terminaison — notamment qu'« annulé » ne s'affiche **qu'après** l'événement
 * `cancelled` (§6.1), et que `done`, `cancelled` et `error` restent trois états distincts
 * (§5.4).
 */

import { translateErrorCode, type TranslatedError } from './errorCatalog';
import type {
  CancellationCause,
  Citation,
  StreamEvent,
  StreamingMode,
} from '../types/stream';

export type OperationState =
  | 'idle'
  | 'streaming'
  /**
   * Le geste a été émis et accepté, le flux reste ouvert. Cet état est distinct de
   * `cancelled` : afficher l'annulation avant l'événement donnerait à l'utilisateur la
   * certitude que la consommation facturée s'est arrêtée, alors que c'est précisément ce
   * que `V2-ADR-011` exige de garantir (§6.1).
   */
  | 'cancel_requested'
  | 'done'
  | 'cancelled'
  | 'error'
  /** Flux coupé sans terminaison et rattachements épuisés (§10.3). */
  | 'unknown_outcome';

export interface OperationSnapshot {
  operationId: string | null;
  streaming: StreamingMode | null;
  state: OperationState;
  /** Texte accumulé depuis les `delta`. */
  text: string;
  citations: Citation[];
  turnCount: number;
  inputTokens: number;
  outputTokens: number;
  toolCallsCount: number;
  budgetExhausted: boolean;
  degraded: boolean;
  cause: CancellationCause | null;
  error: TranslatedError | null;
  /** Time-to-first-token observé côté navigateur, en millisecondes (§14.2). */
  firstTokenMs: number | null;
  /** Horodatage d'ouverture, base de la mesure ci-dessus. */
  startedAt: number | null;
}

export const initialOperation: OperationSnapshot = {
  operationId: null,
  streaming: null,
  state: 'idle',
  text: '',
  citations: [],
  turnCount: 0,
  inputTokens: 0,
  outputTokens: 0,
  toolCallsCount: 0,
  budgetExhausted: false,
  degraded: false,
  cause: null,
  error: null,
  firstTokenMs: null,
  startedAt: null,
};

export type OperationAction =
  | { type: 'begin'; at: number }
  | { type: 'event'; event: StreamEvent; at: number }
  | { type: 'cancel_requested' }
  | { type: 'truncated' }
  | { type: 'transport_error'; error: TranslatedError }
  | { type: 'reset' };

const TERMINAL_STATES: readonly OperationState[] = [
  'done',
  'cancelled',
  'error',
  'unknown_outcome',
];

const isSettled = (state: OperationState): boolean => TERMINAL_STATES.includes(state);

export const operationReducer = (
  snapshot: OperationSnapshot,
  action: OperationAction,
): OperationSnapshot => {
  switch (action.type) {
    case 'begin':
      return { ...initialOperation, state: 'streaming', startedAt: action.at };

    case 'cancel_requested':
      // Une demande d'annulation arrivée après la terminaison ne rouvre pas l'opération.
      return snapshot.state === 'streaming'
        ? { ...snapshot, state: 'cancel_requested' }
        : snapshot;

    case 'truncated':
      return isSettled(snapshot.state) ? snapshot : { ...snapshot, state: 'unknown_outcome' };

    case 'transport_error':
      return isSettled(snapshot.state)
        ? snapshot
        : { ...snapshot, state: 'error', error: action.error };

    case 'reset':
      return initialOperation;

    case 'event':
      return applyEvent(snapshot, action.event, action.at);

    default:
      return snapshot;
  }
};

const applyEvent = (
  snapshot: OperationSnapshot,
  event: StreamEvent,
  at: number,
): OperationSnapshot => {
  switch (event.type) {
    case 'ping':
      return snapshot;

    case 'meta':
      return {
        ...snapshot,
        operationId: event.operationId,
        streaming: event.streaming,
      };

    case 'delta':
      return {
        ...snapshot,
        text: snapshot.text + event.text,
        // Mesuré au premier fragment seulement : un mode `native` déclaré dont le premier
        // fragment arrive à la fin de la réponse est une dégradation silencieuse, et le
        // client est le seul point d'où elle est observable (§5.1).
        firstTokenMs:
          snapshot.firstTokenMs === null && snapshot.startedAt !== null
            ? at - snapshot.startedAt
            : snapshot.firstTokenMs,
      };

    case 'citation':
      return { ...snapshot, citations: [...snapshot.citations, ...event.citations] };

    case 'done':
      return {
        ...snapshot,
        state: 'done',
        // Le texte assemblé localement fait foi tant qu'il est non vide : `answer` le
        // répète, et préférer ce dernier ferait clignoter l'affichage en fin de flux.
        text: snapshot.text !== '' ? snapshot.text : event.answer,
        turnCount: event.turnCount,
        inputTokens: event.inputTokens,
        outputTokens: event.outputTokens,
        toolCallsCount: event.toolCallsCount,
        budgetExhausted: event.budgetExhausted,
        degraded: event.degraded,
      };

    case 'cancelled':
      return {
        ...snapshot,
        state: 'cancelled',
        cause: event.cause,
        // Affichés dans les trois causes : une annulation réduit le coût engagé, elle ne
        // l'annule pas, et l'interface ne doit pas suggérer l'inverse (§6.3).
        inputTokens: event.inputTokens,
        outputTokens: event.outputTokens,
      };

    case 'error':
      return {
        ...snapshot,
        state: 'error',
        error: translateErrorCode(event.code),
      };

    default:
      return snapshot;
  }
};
