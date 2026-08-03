/**
 * Analyseur de flux SSE (V2-LLD-010 §5.3).
 *
 * `EventSource` découperait les événements lui-même, mais il n'accepte aucun en-tête
 * personnalisé et ne peut donc pas porter `Authorization` (§1.7, écart 1). Le découpage
 * est donc explicite, et les deux erreurs classiques qu'il expose sont couvertes par un
 * test plutôt que par la vigilance :
 *
 *   - un fragment réseau ne coïncide pas avec un événement — le tampon est conservé
 *     entre deux `push`, et le décodage UTF-8 est incrémental pour qu'une séquence
 *     multi-octets coupée entre deux fragments ne produise pas de caractère de
 *     remplacement au milieu d'un mot accentué ;
 *   - un événement inconnu ne doit pas interrompre le flux — c'est le rôle du mapping
 *     (`streamEvents.ts`), l'analyseur restituant toute trame telle quelle.
 */

export interface SseFrame {
  /** Nom de l'événement, ou `null` si la trame ne porte que des lignes `data`. */
  event: string | null;
  /** Lignes `data` jointes par `\n`, conformément au format SSE. */
  data: string;
  /** Contenu d'une ligne de commentaire `: …`, ou `null`. */
  comment: string | null;
}

/** Séparateur de trames : une ligne vide, quelle que soit la convention de fin de ligne. */
const FRAME_SEPARATOR = /\r\n\r\n|\n\n|\r\r/;
const LINE_SEPARATOR = /\r\n|\n|\r/;

const parseFrame = (raw: string): SseFrame | null => {
  let event: string | null = null;
  let comment: string | null = null;
  const dataLines: string[] = [];

  for (const line of raw.split(LINE_SEPARATOR)) {
    if (line === '') {
      continue;
    }
    if (line.startsWith(':')) {
      comment = line.slice(1).trim();
      continue;
    }

    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) {
      value = value.slice(1);
    }

    if (field === 'event') {
      event = value;
    } else if (field === 'data') {
      dataLines.push(value);
    }
    // `id` et `retry` sont ignorés : la reprise ne passe pas par `Last-Event-ID`
    // mais par un rattachement explicite sur `operationId` (§5.5).
  }

  if (event === null && comment === null && dataLines.length === 0) {
    return null;
  }
  return { event, data: dataLines.join('\n'), comment };
};

export class SseParser {
  private readonly decoder = new TextDecoder('utf-8');
  private buffer = '';

  /** Consomme un fragment réseau et restitue les trames complètes qu'il achève. */
  push(chunk: Uint8Array): SseFrame[] {
    this.buffer += this.decoder.decode(chunk, { stream: true });
    return this.drain();
  }

  /**
   * Vide le décodeur et le tampon en fin de flux. Une trame non terminée par une ligne
   * vide est restituée : un serveur qui ferme la connexion juste après un événement
   * terminal ne doit pas le faire perdre.
   */
  flush(): SseFrame[] {
    this.buffer += this.decoder.decode();
    const frames = this.drain();
    const remainder = this.buffer;
    this.buffer = '';
    if (remainder.trim() !== '') {
      const frame = parseFrame(remainder);
      if (frame) {
        frames.push(frame);
      }
    }
    return frames;
  }

  private drain(): SseFrame[] {
    const frames: SseFrame[] = [];
    for (;;) {
      const match = FRAME_SEPARATOR.exec(this.buffer);
      if (!match) {
        return frames;
      }
      const raw = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const frame = parseFrame(raw);
      if (frame) {
        frames.push(frame);
      }
    }
  }
}
