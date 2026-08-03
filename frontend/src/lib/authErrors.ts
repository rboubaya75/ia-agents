/**
 * Erreurs d'authentification partagées par le service d'authentification et le transport
 * (V2-LLD-010 §4.3).
 */

/**
 * La session ne peut plus être renouvelée : jeton de rafraîchissement invalide ou révoqué,
 * ou deux 401 consécutifs. Dans les deux cas la conduite est la même — déconnexion
 * immédiate, sans réessai. Réessayer indéfiniment produirait une boucle d'appels sur une
 * session morte, que le quota par identité de `V2-ADR-016` compterait contre l'utilisateur.
 */
export class SessionExpiredError extends Error {
  constructor(message = 'La session a expiré. Reconnectez-vous.') {
    super(message);
    this.name = 'SessionExpiredError';
  }
}
