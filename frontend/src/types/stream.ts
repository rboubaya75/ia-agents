/**
 * Contrat d'événements SSE consommé par le client (V2-LLD-010 §5.4).
 *
 * Les champs reproduisent la sérialisation de FastAPI (`app/routes/conversations.py`).
 * Toute divergence doit casser à la compilation plutôt qu'à l'exécution (§15.3).
 */

export type StreamingMode = 'native' | 'emulated';

export type CancellationCause = 'client' | 'deadline' | 'operator';

export interface Citation {
  documentId?: string;
  title?: string;
  excerpt?: string;
  uri?: string;
}

export interface StreamMetaEvent {
  type: 'meta';
  streaming: StreamingMode;
  operationId: string;
}

export interface StreamDeltaEvent {
  type: 'delta';
  text: string;
}

export interface StreamCitationEvent {
  type: 'citation';
  citations: Citation[];
}

export interface StreamDoneEvent {
  type: 'done';
  answer: string;
  turnCount: number;
  inputTokens: number;
  outputTokens: number;
  toolCallsCount: number;
  budgetExhausted: boolean;
  /** Retrieval, mémoire ou tool dégradé sans échec de la réponse (§11.4). */
  degraded: boolean;
  servedInvocationId: string;
}

export interface StreamCancelledEvent {
  type: 'cancelled';
  cause: CancellationCause;
  inputTokens: number;
  outputTokens: number;
}

export interface StreamErrorEvent {
  type: 'error';
  code: string;
  message: string;
}

/** Commentaire `: ping` — réarme le détecteur d'inactivité, aucun effet visible (§5.4). */
export interface StreamPingEvent {
  type: 'ping';
}

export type StreamEvent =
  | StreamMetaEvent
  | StreamDeltaEvent
  | StreamCitationEvent
  | StreamDoneEvent
  | StreamCancelledEvent
  | StreamErrorEvent
  | StreamPingEvent;

export type TerminalStreamEvent =
  | StreamDoneEvent
  | StreamCancelledEvent
  | StreamErrorEvent;

/**
 * `done`, `cancelled` et `error` sont trois terminaisons distinctes que le client ne
 * fusionne pas (§5.4) : présenter une interruption voulue comme une panne apprend à
 * l'utilisateur à se méfier d'un geste qui a fonctionné.
 */
export const isTerminalEvent = (event: StreamEvent): event is TerminalStreamEvent =>
  event.type === 'done' || event.type === 'cancelled' || event.type === 'error';
