/**
 * Test d'intégration du contrat front ↔ FastAPI.
 *
 * Ignoré tant que `V2_API_URL` n'est pas défini : il exige un service en écoute. C'est le
 * seul test qui vérifie que l'analyseur, le mapping et le réducteur consomment
 * réellement ce que FastAPI sérialise — les tests unitaires reposent tous sur des trames
 * écrites à la main, qui pourraient dériver du serveur sans que rien ne le signale.
 *
 *   uvicorn serve_test:app --port 8099
 *   V2_API_URL=http://127.0.0.1:8099 npx vitest run streamService.integration
 */

import { describe, expect, it } from 'vitest';
import { SseParser } from '../lib/sseParser';
import { toStreamEvent } from '../lib/streamEvents';
import { initialOperation, operationReducer } from '../lib/operationReducer';
import { isTerminalEvent, type StreamEvent } from '../types/stream';

const API = process.env.V2_API_URL;

const readStream = async (response: Response): Promise<StreamEvent[]> => {
  const reader = response.body!.getReader();
  const parser = new SseParser();
  const events: StreamEvent[] = [];
  for (;;) {
    const { done, value } = await reader.read();
    const frames = done ? parser.flush() : parser.push(value!);
    for (const frame of frames) {
      const event = toStreamEvent(frame);
      if (event) {
        events.push(event);
      }
    }
    if (done || events.some(isTerminalEvent)) {
      break;
    }
  }
  return events;
};

describe.skipIf(!API)('contrat front ↔ FastAPI', () => {
  it('consomme un tour complet et en dérive un état cohérent', async () => {
    const response = await fetch(`${API}/api/v1/conversations/conversation-integration/messages`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer jeton-de-test',
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({ message: 'Bonjour, café élégant ?' }),
    });

    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toContain('text/event-stream');
    expect(response.headers.get('x-operation-id')).toBeTruthy();

    const events = await readStream(response);

    // L'ordre du contrat : meta en premier, exactement une terminaison en dernier.
    expect(events[0].type).toBe('meta');
    expect(events.filter(isTerminalEvent)).toHaveLength(1);
    expect(events[events.length - 1].type).toBe('done');

    const state = events.reduce(
      (snapshot, event) => operationReducer(snapshot, { type: 'event', event, at: Date.now() }),
      operationReducer(initialOperation, { type: 'begin', at: Date.now() }),
    );

    expect(state.state).toBe('done');
    expect(state.operationId).toBe(response.headers.get('x-operation-id'));
    expect(state.streaming).toBe('emulated');
    // Le stub sert la réponse : le drapeau doit remonter jusqu'à l'interface (§11.4).
    expect(state.degraded).toBe(true);
    // Les accents traversent le décodage incrémental sans caractère de remplacement.
    expect(state.text).toContain('café élégant');
    expect(state.text).not.toContain('�');
  });

  it('refuse un message vide au contrat d\'entrée', async () => {
    const response = await fetch(`${API}/api/v1/conversations/conversation-integration/messages`, {
      method: 'POST',
      headers: { Authorization: 'Bearer jeton-de-test', 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: '' }),
    });
    expect(response.status).toBe(422);
  });

  it('répond 404 pour une opération inconnue à l\'annulation', async () => {
    const response = await fetch(`${API}/api/v1/operations/inconnue/cancel`, {
      method: 'POST',
      headers: { Authorization: 'Bearer jeton-de-test' },
    });
    expect(response.status).toBe(404);
  });
});
