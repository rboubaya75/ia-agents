/**
 * Ce que l'utilisateur voit du transport et de la terminaison
 * (V2-LLD-010 §5.6, §6.1, §6.3, §11.4).
 */

import React from 'react';
import type { OperationSnapshot } from '../../lib/operationReducer';
import type { CancellationCause } from '../../types/stream';

interface StreamStatusProps {
  operation: OperationSnapshot;
  onCancel: () => void;
}

const CANCELLATION_LABEL: Readonly<Record<CancellationCause, string>> = {
  // Trois causes, trois formulations : présenter une échéance atteinte comme un geste de
  // l'utilisateur serait faux (§6.3).
  client: 'Interrompu à votre demande',
  deadline: 'Interrompu : durée maximale atteinte',
  operator: 'Interrompu par l\'exploitant',
};

const Counters: React.FC<{ operation: OperationSnapshot }> = ({ operation }) => (
  <span className="text-xs text-gray-500">
    {operation.inputTokens + operation.outputTokens} jetons consommés
    {operation.turnCount > 0 ? ` · ${operation.turnCount} tour(s)` : ''}
  </span>
);

const StreamStatus: React.FC<StreamStatusProps> = ({ operation, onCancel }) => {
  const streaming = operation.state === 'streaming';
  const cancelRequested = operation.state === 'cancel_requested';

  if (operation.state === 'idle') {
    return null;
  }

  return (
    <div className="px-4 pb-2 space-y-2">
      {/* Un mode `emulated` est une mention discrète et permanente, pas une alerte :
          c'est un repli assumé, pas un incident (§5.6). */}
      {operation.streaming === 'emulated' && (
        <p className="text-xs text-gray-500">
          Réponse transmise en mode compatible (diffusion émulée).
        </p>
      )}

      {(streaming || cancelRequested) && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelRequested}
            className="text-sm px-3 py-1 rounded border border-gray-400 text-gray-700 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {cancelRequested ? 'Annulation demandée…' : 'Interrompre'}
          </button>
          {cancelRequested && (
            <span className="text-xs text-gray-500">
              En attente de la confirmation du service.
            </span>
          )}
        </div>
      )}

      {/* Une seule annonce, à la terminaison — pas une par fragment (§13.1). */}
      <div aria-live="polite">
        {operation.state === 'done' && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Counters operation={operation} />
            {/* Affiché discrètement et systématiquement : masquer la dégradation donnerait
                à une réponse produite sans contexte documentaire le même crédit qu'une
                réponse complète (§11.4). */}
            {operation.degraded && (
              <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
                Réponse produite en mode dégradé
              </span>
            )}
            {operation.budgetExhausted && (
              <span className="text-xs text-amber-700">Budget de la réponse épuisé</span>
            )}
          </div>
        )}

        {operation.state === 'cancelled' && operation.cause && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-sm text-gray-700">{CANCELLATION_LABEL[operation.cause]}</span>
            <Counters operation={operation} />
          </div>
        )}

        {operation.state === 'error' && operation.error && (
          <div
            className="border-l-4 border-red-400 bg-red-50 px-3 py-2"
            role="alert"
          >
            <p className="text-sm font-medium text-red-800">{operation.error.title}</p>
            <p className="text-sm text-red-700">{operation.error.detail}</p>
          </div>
        )}

        {operation.state === 'unknown_outcome' && (
          <div className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2" role="alert">
            <p className="text-sm font-medium text-amber-800">Issue inconnue</p>
            <p className="text-sm text-amber-700">
              La connexion s'est interrompue avant la fin de la réponse. Le traitement a pu
              aboutir : ne réémettez pas le message, rechargez la conversation.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default StreamStatus;
