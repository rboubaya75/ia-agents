/**
 * État d'une invocation conversationnelle (V2-LLD-010 §2.3).
 *
 * Ce contexte existe parce que plusieurs composants sans lien de parenté en dépendent —
 * le flux, le bouton d'annulation, et la carte de confirmation qu'apportera le lot MCP.
 */

import React, {
  createContext,
  useCallback,
  useReducer,
  useRef,
  type ReactNode,
} from 'react';

import {
  initialOperation,
  operationReducer,
  type OperationSnapshot,
} from '../lib/operationReducer';
import type { TranslatedError } from '../lib/errorCatalog';
import { SessionExpiredError } from '../lib/authErrors';
import { getAccessToken } from '../services/authService';
import { cancelOperation, streamMessage } from '../services/streamService';

export interface OperationContextType {
  operation: OperationSnapshot;
  send: (conversationId: string, message: string) => Promise<void>;
  requestCancel: () => Promise<void>;
  reset: () => void;
}

const OperationContext = createContext<OperationContextType | undefined>(undefined);

const TRANSPORT_FAILURE: TranslatedError = {
  family: 'degradation',
  title: 'Flux interrompu',
  detail: 'La connexion au service a échoué. Réessayez dans quelques instants.',
  retryable: true,
};

interface OperationProviderProps {
  children: ReactNode;
  /** Remonté à la déconnexion forcée (§4.3) : le provider ne connaît pas l'écran de login. */
  onSessionExpired?: () => void;
}

export const OperationProvider: React.FC<OperationProviderProps> = ({
  children,
  onSessionExpired,
}) => {
  const [operation, dispatch] = useReducer(operationReducer, initialOperation);
  const abortRef = useRef<AbortController | null>(null);
  const operationIdRef = useRef<string | null>(null);

  const send = useCallback(
    async (conversationId: string, message: string) => {
      dispatch({ type: 'begin', at: Date.now() });
      operationIdRef.current = null;

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const outcome = await streamMessage({
          conversationId,
          message,
          getAccessToken,
          signal: controller.signal,
          onEvent: (event) => {
            if (event.type === 'meta') {
              operationIdRef.current = event.operationId;
            }
            dispatch({ type: 'event', event, at: Date.now() });
          },
        });

        if (outcome.kind === 'truncated') {
          // Un flux coupé sans événement terminal appelle un rattachement par
          // `operationId` (§5.5) — la route dédiée n'existe pas encore côté serveur, donc
          // l'interface bascule directement sur « issue inconnue » (§10.3) plutôt que de
          // réémettre le message, ce qui doublerait l'opération.
          console.warn('[stream] flux terminé sans événement terminal', {
            reason: outcome.reason,
          });
          dispatch({ type: 'truncated' });
        }
      } catch (error) {
        if (error instanceof SessionExpiredError) {
          onSessionExpired?.();
          dispatch({
            type: 'transport_error',
            error: {
              family: 'authorization',
              title: 'Session expirée',
              detail: 'Reconnectez-vous pour poursuivre.',
              retryable: false,
            },
          });
          return;
        }
        console.error('[stream] ouverture impossible', error);
        dispatch({ type: 'transport_error', error: TRANSPORT_FAILURE });
      } finally {
        // L'`AbortController` n'est déclenché qu'ici — après la terminaison — jamais au
        // geste d'annulation, qui couperait le canal par lequel l'annulation doit être
        // confirmée (§6.2).
        controller.abort();
        abortRef.current = null;
      }
    },
    [onSessionExpired],
  );

  const requestCancel = useCallback(async () => {
    const operationId = operationIdRef.current;
    if (!operationId) {
      return;
    }

    // L'état passe à « annulation demandée », pas à « annulé » : le flux reste ouvert et
    // c'est l'événement `cancelled` qui atteste que la consommation facturée s'est
    // arrêtée, et non seulement l'affichage (§6.1).
    dispatch({ type: 'cancel_requested' });

    try {
      const outcome = await cancelOperation(operationId, getAccessToken);
      if (outcome === 'unknown') {
        // Opération inconnue ou déjà close — FastAPI ne distingue pas les deux, pour ne
        // pas offrir d'oracle d'existence.
        console.info('[cancel] opération inconnue ou déjà close');
      }
    } catch (error) {
      if (error instanceof SessionExpiredError) {
        onSessionExpired?.();
        return;
      }
      console.error('[cancel] demande impossible', error);
    }
  }, [onSessionExpired]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    operationIdRef.current = null;
    dispatch({ type: 'reset' });
  }, []);

  const value: OperationContextType = { operation, send, requestCancel, reset };

  return <OperationContext.Provider value={value}>{children}</OperationContext.Provider>;
};

export default OperationContext;
