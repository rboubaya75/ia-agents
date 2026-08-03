/**
 * Stockage des jetons Cognito (V2-LLD-010 §4.2 — décision de l'écart 3).
 *
 * `amazon-cognito-identity-js` accepte un objet `Storage` personnalisé à la construction
 * du pool ; ce point d'extension est le mécanisme de la décision.
 *
 *   Jeton d'accès          → mémoire du module uniquement. C'est le jeton qui autorise ;
 *                            il ne survit ni au rechargement ni à la fermeture de
 *                            l'onglet, et aucun script ne le lit par une API de stockage.
 *   Rafraîchissement, id   → `sessionStorage`. Le premier doit survivre à un rechargement,
 *                            sans quoi tout F5 déconnecte ; `sessionStorage` borne sa vie
 *                            à l'onglet.
 *
 * Pourquoi pas `localStorage` : il survit à la fermeture du navigateur et est partagé par
 * tous les onglets de l'origine. Avec un jeton de rafraîchissement de trente jours
 * (`V2-LLD-005 §2.3`), une faille XSS y prélève une session d'un mois sur une machine
 * partagée. `sessionStorage` ne supprime pas le risque — il en borne le produit à la durée
 * d'un onglet. La règle de lint du §15.3 interdit `localStorage` pour que cette décision
 * ne soit pas annulée par mégarde.
 */

const ACCESS_TOKEN_SUFFIX = '.accessToken';

const isAccessTokenKey = (key: string): boolean => key.endsWith(ACCESS_TOKEN_SUFFIX);

/** Repli lorsque `sessionStorage` est indisponible (navigation privée stricte). */
class MemoryStore {
  private readonly entries = new Map<string, string>();

  getItem(key: string): string | null {
    return this.entries.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.entries.set(key, value);
  }

  removeItem(key: string): void {
    this.entries.delete(key);
  }

  clear(): void {
    this.entries.clear();
  }
}

const persistentStore = (): Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> & {
  clear: () => void;
} => {
  try {
    const probe = '__v2_probe__';
    window.sessionStorage.setItem(probe, '1');
    window.sessionStorage.removeItem(probe);
    return window.sessionStorage;
  } catch {
    console.warn('[auth] sessionStorage indisponible, session bornée à la page');
    return new MemoryStore();
  }
};

/**
 * Implémente `ICognitoStorage`. Le SDK appelle ces quatre méthodes de façon synchrone,
 * d'où l'absence de promesse.
 */
export class SplitTokenStorage {
  private readonly volatile = new MemoryStore();
  private readonly persistent = persistentStore();

  getItem(key: string): string | null {
    return isAccessTokenKey(key) ? this.volatile.getItem(key) : this.persistent.getItem(key);
  }

  setItem(key: string, value: string): void {
    if (isAccessTokenKey(key)) {
      this.volatile.setItem(key, value);
      return;
    }
    this.persistent.setItem(key, value);
  }

  removeItem(key: string): void {
    if (isAccessTokenKey(key)) {
      this.volatile.removeItem(key);
      return;
    }
    this.persistent.removeItem(key);
  }

  clear(): void {
    this.volatile.clear();
    this.persistent.clear();
  }
}

export const tokenStorage = new SplitTokenStorage();
