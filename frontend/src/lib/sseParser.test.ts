import { describe, expect, it } from 'vitest';
import { SseParser } from './sseParser';

const bytes = (text: string): Uint8Array => new TextEncoder().encode(text);

describe('SseParser', () => {
  it('restitue une trame complète', () => {
    const parser = new SseParser();
    const frames = parser.push(bytes('event: delta\ndata: {"text":"bonjour"}\n\n'));
    expect(frames).toEqual([
      { event: 'delta', data: '{"text":"bonjour"}', comment: null },
    ]);
  });

  // §5.3 — « un fragment réseau ne coïncide pas avec un événement »
  it('assemble une trame répartie sur plusieurs fragments', () => {
    const parser = new SseParser();
    expect(parser.push(bytes('event: de'))).toHaveLength(0);
    expect(parser.push(bytes('lta\ndata: {"text":'))).toHaveLength(0);
    const frames = parser.push(bytes('"ok"}\n\n'));
    expect(frames).toEqual([{ event: 'delta', data: '{"text":"ok"}', comment: null }]);
  });

  it('restitue plusieurs trames contenues dans un seul fragment', () => {
    const parser = new SseParser();
    const frames = parser.push(
      bytes('event: meta\ndata: {"a":1}\n\nevent: delta\ndata: {"text":"x"}\n\n'),
    );
    expect(frames.map((frame) => frame.event)).toEqual(['meta', 'delta']);
  });

  // §5.3 — un décodage par fragment produirait un caractère de remplacement au milieu
  // d'un mot accentué : défaut visible, rare, et impossible à reproduire sans ce test.
  it('ne casse pas une séquence UTF-8 coupée entre deux fragments', () => {
    const parser = new SseParser();
    const payload = bytes('event: delta\ndata: {"text":"café élégant"}\n\n');

    // Coupe au milieu du « é » de « café » (deux octets en UTF-8).
    const cut = payload.indexOf(0xc3);
    expect(cut).toBeGreaterThan(0);

    expect(parser.push(payload.slice(0, cut + 1))).toHaveLength(0);
    const frames = parser.push(payload.slice(cut + 1));

    expect(frames).toHaveLength(1);
    expect(JSON.parse(frames[0].data)).toEqual({ text: 'café élégant' });
    expect(frames[0].data).not.toContain('�');
  });

  it('reconnaît un commentaire de keep-alive', () => {
    const parser = new SseParser();
    const frames = parser.push(bytes(': ping\n\n'));
    expect(frames).toEqual([{ event: null, data: '', comment: 'ping' }]);
  });

  it('joint les lignes data multiples par un saut de ligne', () => {
    const parser = new SseParser();
    const frames = parser.push(bytes('event: delta\ndata: une\ndata: deux\n\n'));
    expect(frames[0].data).toBe('une\ndeux');
  });

  it('accepte les fins de ligne CRLF', () => {
    const parser = new SseParser();
    const frames = parser.push(bytes('event: done\r\ndata: {"ok":true}\r\n\r\n'));
    expect(frames).toEqual([{ event: 'done', data: '{"ok":true}', comment: null }]);
  });

  it('restitue une trame finale non terminée par une ligne vide', () => {
    const parser = new SseParser();
    expect(parser.push(bytes('event: done\ndata: {"ok":true}'))).toHaveLength(0);
    const frames = parser.flush();
    expect(frames).toEqual([{ event: 'done', data: '{"ok":true}', comment: null }]);
  });

  it('ignore une ligne sans valeur sans produire de trame vide', () => {
    const parser = new SseParser();
    expect(parser.push(bytes('\n\n'))).toHaveLength(0);
  });
});
