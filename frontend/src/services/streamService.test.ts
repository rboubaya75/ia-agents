import { afterEach, describe, expect, it, vi } from 'vitest';
import { cancelOperation, StreamTransportError, streamMessage } from './streamService';
import { SessionExpiredError } from '../lib/authErrors';
import type { StreamEvent } from '../types/stream';

const encoder = new TextEncoder();

const streamOf = (chunks: string[]): ReadableStream<Uint8Array> =>
  new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

const sseResponse = (chunks: string[], status = 200): Response =>
  ({
    ok: status >= 200 && status < 300,
    status,
    body: streamOf(chunks),
  }) as unknown as Response;

const emptyResponse = (status: number): Response =>
  ({ ok: status >= 200 && status < 300, status, body: null }) as unknown as Response;

const token = async () => 'jeton';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('streamMessage', () => {
  it('restitue les événements dans l\'ordre et se termine sur done', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'event: meta\ndata: {"streaming":"emulated","operationId":"op-1"}\n\n',
          ': ping\n\n',
          'event: delta\ndata: {"text":"bon"}\n\nevent: delta\ndata: {"text":"jour"}\n\n',
          'event: done\ndata: {"answer":"bonjour","turnCount":1,"inputTokens":1,"outputTokens":2,"toolCallsCount":0,"budgetExhausted":false,"degraded":true,"servedInvocationId":"stub"}\n\n',
        ]),
      ),
    );

    const seen: StreamEvent[] = [];
    const outcome = await streamMessage({
      conversationId: 'conv-1',
      message: 'bonjour',
      getAccessToken: token,
      signal: new AbortController().signal,
      onEvent: (event) => seen.push(event),
    });

    expect(seen.map((event) => event.type)).toEqual(['meta', 'ping', 'delta', 'delta', 'done']);
    expect(outcome).toMatchObject({ kind: 'terminal' });
    expect(outcome.kind === 'terminal' && outcome.event.type).toBe('done');
  });

  // §5.5 — un flux coupé sans événement terminal appelle un rattachement, jamais une
  // réémission : le service doit donc le signaler et non le confondre avec une fin normale.
  it('signale une coupure sans événement terminal', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse(['event: meta\ndata: {"streaming":"native","operationId":"op-2"}\n\n']),
      ),
    );

    const outcome = await streamMessage({
      conversationId: 'conv-1',
      message: 'x',
      getAccessToken: token,
      signal: new AbortController().signal,
      onEvent: () => undefined,
    });

    expect(outcome).toEqual({ kind: 'truncated', reason: 'closed' });
  });

  it('n\'interrompt pas le flux sur un événement inconnu', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'event: command\ndata: {"commandId":"c-1"}\n\n',
          'event: error\ndata: {"code":"model_throttled","message":"x"}\n\n',
        ]),
      ),
    );

    const seen: StreamEvent[] = [];
    const outcome = await streamMessage({
      conversationId: 'conv-1',
      message: 'x',
      getAccessToken: token,
      signal: new AbortController().signal,
      onEvent: (event) => seen.push(event),
    });

    expect(seen.map((event) => event.type)).toEqual(['error']);
    expect(outcome).toMatchObject({ kind: 'terminal' });
    warn.mockRestore();
  });

  // §4.3 — un seul renouvellement par appel, jamais de boucle.
  it('renouvelle une seule fois sur 401 puis réémet', async () => {
    const responses = [emptyResponse(401), sseResponse(['event: done\ndata: {}\n\n'])];
    const fetchMock = vi.fn(async () => responses.shift()!);
    vi.stubGlobal('fetch', fetchMock);

    const forced: boolean[] = [];
    await streamMessage({
      conversationId: 'conv-1',
      message: 'x',
      getAccessToken: async (options) => {
        forced.push(options?.forceRefresh === true);
        return 'jeton';
      },
      signal: new AbortController().signal,
      onEvent: () => undefined,
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(forced).toEqual([false, true]);
  });

  it('déconnecte sur un second 401 sans réessayer', async () => {
    const fetchMock = vi.fn(async () => emptyResponse(401));
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      streamMessage({
        conversationId: 'conv-1',
        message: 'x',
        getAccessToken: token,
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toBeInstanceOf(SessionExpiredError);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('lève une erreur de transport sur un statut d\'échec', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => emptyResponse(503)));

    await expect(
      streamMessage({
        conversationId: 'conv-1',
        message: 'x',
        getAccessToken: token,
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    ).rejects.toBeInstanceOf(StreamTransportError);
  });
});

describe('cancelOperation', () => {
  it('signale la demande acceptée', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => emptyResponse(200)));
    await expect(cancelOperation('op-1', token)).resolves.toBe('requested');
  });

  // FastAPI répond 404 aussi bien pour une opération inconnue que pour celle d'un autre
  // acteur : le client ne peut pas les distinguer, et ne doit pas essayer.
  it('traite 404 et 403 de la même façon', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => emptyResponse(404)));
    await expect(cancelOperation('op-1', token)).resolves.toBe('unknown');

    vi.stubGlobal('fetch', vi.fn(async () => emptyResponse(403)));
    await expect(cancelOperation('op-1', token)).resolves.toBe('unknown');
  });
});
