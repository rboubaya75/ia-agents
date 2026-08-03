import { describe, expect, it } from 'vitest';
import { initialOperation, operationReducer, type OperationSnapshot } from './operationReducer';

const begin = (at = 1_000): OperationSnapshot =>
  operationReducer(initialOperation, { type: 'begin', at });

describe('operationReducer', () => {
  // §6.1 — l'interface n'affiche pas « annulé » avant l'événement `cancelled` : afficher
  // l'annulation plus tôt donnerait la certitude que la consommation facturée a cessé.
  it('distingue « annulation demandée » de « annulé »', () => {
    const requested = operationReducer(begin(), { type: 'cancel_requested' });
    expect(requested.state).toBe('cancel_requested');

    const cancelled = operationReducer(requested, {
      type: 'event',
      event: { type: 'cancelled', cause: 'client', inputTokens: 10, outputTokens: 5 },
      at: 2_000,
    });
    expect(cancelled.state).toBe('cancelled');
  });

  // §6.3 — une annulation réduit le coût engagé, elle ne l'annule pas.
  it('affiche les compteurs consommés sur une annulation', () => {
    const cancelled = operationReducer(begin(), {
      type: 'event',
      event: { type: 'cancelled', cause: 'deadline', inputTokens: 7, outputTokens: 3 },
      at: 2_000,
    });
    expect(cancelled).toMatchObject({ cause: 'deadline', inputTokens: 7, outputTokens: 3 });
  });

  it('accumule les fragments', () => {
    let state = begin();
    for (const text of ['bon', 'jour ', 'monde']) {
      state = operationReducer(state, { type: 'event', event: { type: 'delta', text }, at: 1_100 });
    }
    expect(state.text).toBe('bonjour monde');
  });

  // §14.2 — le time-to-first-token est mesuré au premier fragment seulement.
  it('mesure le time-to-first-token une seule fois', () => {
    let state = begin(1_000);
    state = operationReducer(state, { type: 'event', event: { type: 'delta', text: 'a' }, at: 1_250 });
    expect(state.firstTokenMs).toBe(250);
    state = operationReducer(state, { type: 'event', event: { type: 'delta', text: 'b' }, at: 1_900 });
    expect(state.firstTokenMs).toBe(250);
  });

  it('traduit un code d\'erreur connu', () => {
    const state = operationReducer(begin(), {
      type: 'event',
      event: { type: 'error', code: 'model_throttled', message: 'ignoré' },
      at: 2_000,
    });
    expect(state.state).toBe('error');
    expect(state.error?.family).toBe('degradation');
  });

  // §11.2 — un code absent de la table close ne s'affiche jamais en brut.
  it('n\'expose jamais un code inconnu dans le message rendu', () => {
    const state = operationReducer(begin(), {
      type: 'event',
      event: { type: 'error', code: 'code_interne_xyz', message: 'détail serveur' },
      at: 2_000,
    });
    expect(state.error?.title).not.toContain('code_interne_xyz');
    expect(state.error?.detail).not.toContain('code_interne_xyz');
    expect(state.error?.detail).not.toContain('détail serveur');
  });

  it('conserve le drapeau degraded porté par done', () => {
    const state = operationReducer(begin(), {
      type: 'event',
      event: {
        type: 'done',
        answer: 'réponse',
        turnCount: 1,
        inputTokens: 1,
        outputTokens: 2,
        toolCallsCount: 0,
        budgetExhausted: false,
        degraded: true,
        servedInvocationId: 'stub',
      },
      at: 2_000,
    });
    expect(state).toMatchObject({ state: 'done', degraded: true });
  });

  it('bascule sur « issue inconnue » quand le flux se coupe sans terminaison', () => {
    expect(operationReducer(begin(), { type: 'truncated' }).state).toBe('unknown_outcome');
  });

  it('ne rouvre pas une opération déjà terminée', () => {
    const done = operationReducer(begin(), {
      type: 'event',
      event: {
        type: 'done',
        answer: 'x',
        turnCount: 1,
        inputTokens: 0,
        outputTokens: 0,
        toolCallsCount: 0,
        budgetExhausted: false,
        degraded: false,
        servedInvocationId: 's',
      },
      at: 2_000,
    });
    expect(operationReducer(done, { type: 'truncated' }).state).toBe('done');
    expect(operationReducer(done, { type: 'cancel_requested' }).state).toBe('done');
  });

  it('ignore un ping', () => {
    const state = begin();
    expect(operationReducer(state, { type: 'event', event: { type: 'ping' }, at: 1_500 })).toBe(state);
  });
});
