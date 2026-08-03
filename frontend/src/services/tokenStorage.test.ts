/**
 * @vitest-environment jsdom
 *
 * Preuve P9 (V2-LLD-010 §16) : le jeton d'accès n'est présent dans aucun stockage
 * navigateur, et le jeton de rafraîchissement n'est pas en `localStorage`.
 */

/* eslint-disable no-restricted-properties --
 * Ce fichier est le seul autorisé à lire `localStorage` : la preuve P9 consiste
 * précisément à constater qu'aucun jeton ne s'y trouve. La règle du §15.3 reste active
 * partout ailleurs.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { SplitTokenStorage } from './tokenStorage';

const ACCESS_KEY = 'CognitoIdentityServiceProvider.abc123.alice.accessToken';
const REFRESH_KEY = 'CognitoIdentityServiceProvider.abc123.alice.refreshToken';
const ID_KEY = 'CognitoIdentityServiceProvider.abc123.alice.idToken';
const LAST_USER_KEY = 'CognitoIdentityServiceProvider.abc123.LastAuthUser';

describe('SplitTokenStorage', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it('garde le jeton d\'accès hors de tout stockage navigateur', () => {
    const storage = new SplitTokenStorage();
    storage.setItem(ACCESS_KEY, 'jeton-acces');

    expect(storage.getItem(ACCESS_KEY)).toBe('jeton-acces');
    expect(window.sessionStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(window.localStorage.getItem(ACCESS_KEY)).toBeNull();
    // Aucune clé du stockage ne porte la valeur, quel que soit son nom.
    const dumped = JSON.stringify({ ...window.sessionStorage, ...window.localStorage });
    expect(dumped).not.toContain('jeton-acces');
  });

  it('place le jeton de rafraîchissement en sessionStorage, jamais en localStorage', () => {
    const storage = new SplitTokenStorage();
    storage.setItem(REFRESH_KEY, 'jeton-refresh');

    expect(window.sessionStorage.getItem(REFRESH_KEY)).toBe('jeton-refresh');
    expect(window.localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('place le jeton d\'identité et l\'utilisateur courant en sessionStorage', () => {
    const storage = new SplitTokenStorage();
    storage.setItem(ID_KEY, 'jeton-id');
    storage.setItem(LAST_USER_KEY, 'alice');

    expect(window.sessionStorage.getItem(ID_KEY)).toBe('jeton-id');
    expect(window.sessionStorage.getItem(LAST_USER_KEY)).toBe('alice');
    expect(window.localStorage.length).toBe(0);
  });

  it('ne survit pas au rechargement pour le jeton d\'accès', () => {
    const before = new SplitTokenStorage();
    before.setItem(ACCESS_KEY, 'jeton-acces');
    before.setItem(REFRESH_KEY, 'jeton-refresh');

    // Une nouvelle instance modélise un rechargement de page : le module est réévalué.
    const after = new SplitTokenStorage();
    expect(after.getItem(ACCESS_KEY)).toBeNull();
    expect(after.getItem(REFRESH_KEY)).toBe('jeton-refresh');
  });

  it('efface les deux emplacements', () => {
    const storage = new SplitTokenStorage();
    storage.setItem(ACCESS_KEY, 'a');
    storage.setItem(REFRESH_KEY, 'r');
    storage.clear();

    expect(storage.getItem(ACCESS_KEY)).toBeNull();
    expect(storage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('retire une clé de l\'emplacement qui la porte', () => {
    const storage = new SplitTokenStorage();
    storage.setItem(ACCESS_KEY, 'a');
    storage.setItem(REFRESH_KEY, 'r');

    storage.removeItem(ACCESS_KEY);
    expect(storage.getItem(ACCESS_KEY)).toBeNull();
    expect(storage.getItem(REFRESH_KEY)).toBe('r');
  });
});
