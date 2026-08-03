import { describe, expect, it, vi } from 'vitest';
import { toStreamEvent } from './streamEvents';

describe('toStreamEvent', () => {
  it('traduit meta', () => {
    expect(
      toStreamEvent({
        event: 'meta',
        data: '{"streaming":"emulated","operationId":"op-1"}',
        comment: null,
      }),
    ).toEqual({ type: 'meta', streaming: 'emulated', operationId: 'op-1' });
  });

  it('traduit done avec ses compteurs', () => {
    const event = toStreamEvent({
      event: 'done',
      data: JSON.stringify({
        answer: 'réponse',
        turnCount: 1,
        inputTokens: 12,
        outputTokens: 34,
        toolCallsCount: 0,
        budgetExhausted: false,
        degraded: true,
        servedInvocationId: 'stub',
      }),
      comment: null,
    });
    expect(event).toMatchObject({ type: 'done', degraded: true, outputTokens: 34 });
  });

  it('traduit un commentaire de keep-alive en ping', () => {
    expect(toStreamEvent({ event: null, data: '', comment: 'ping' })).toEqual({ type: 'ping' });
  });

  // §5.3 — « ignorer et journaliser, jamais rompre » : un client qui échouerait sur un
  // événement inconnu rendrait toute extension serveur incompatible.
  it('ignore un événement inconnu sans lever', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(toStreamEvent({ event: 'command', data: '{"commandId":"c1"}', comment: null })).toBeNull();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('ignore une charge utile illisible sans lever', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(toStreamEvent({ event: 'delta', data: '{ceci n\'est pas du json', comment: null })).toBeNull();
    warn.mockRestore();
  });

  // §5.1 — supposer `native` masquerait une dégradation ; le repli assumé est `emulated`.
  it('retombe sur emulated pour un mode de streaming non reconnu', () => {
    expect(
      toStreamEvent({ event: 'meta', data: '{"streaming":"turbo","operationId":"x"}', comment: null }),
    ).toMatchObject({ streaming: 'emulated' });
  });

  it('ne journalise jamais la charge utile', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    toStreamEvent({ event: 'inconnu', data: '{"secret":"contenu de conversation"}', comment: null });
    const serialised = JSON.stringify(warn.mock.calls);
    expect(serialised).not.toContain('contenu de conversation');
    warn.mockRestore();
  });
});
