/**
 * Configuration d'exécution (V2-LLD-010 §15.1).
 *
 * Un bundle statique ne lit pas de variables d'environnement à l'exécution. Ce qui est
 * constant pour un environnement — origine de l'API, pool Cognito — est injecté au build
 * par Vite. Ce qui peut changer sans reconstruction est lu ici, au démarrage, depuis un
 * fichier servi avec les mêmes en-têtes de cache que l'`index.html`.
 *
 * Ce n'est pas une commodité : figer ces bornes dans le bundle laisserait un client plus
 * permissif que le serveur jusqu'au prochain déploiement de frontend.
 */

export interface RuntimeConfig {
  /** Marge avant échéance déclenchant un renouvellement silencieux du jeton (§4.3). */
  tokenRenewalMarginSeconds: number;
  /**
   * Borne d'inactivité du flux, dérivée du keep-alive de `V2-LLD-001 §7.3` — un multiple
   * de l'intervalle de `: ping`. Trop courte, elle produit des rattachements sur un flux
   * vivant ; trop longue, elle laisse l'utilisateur devant une interface figée (§5.5).
   */
  streamIdleTimeoutSeconds: number;
  /** Au-delà, l'interface bascule sur « issue inconnue » plutôt que de boucler (§5.5). */
  maxReattachments: number;
}

const DEFAULTS: RuntimeConfig = {
  tokenRenewalMarginSeconds: 120,
  streamIdleTimeoutSeconds: 60,
  maxReattachments: 3,
};

const CONFIG_URL = '/config.json';

let loaded: RuntimeConfig = DEFAULTS;

const positiveInteger = (value: unknown, fallback: number): number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;

/**
 * Charge la configuration servie. Un fichier absent ou illisible n'empêche pas le
 * démarrage : les défauts s'appliquent et l'écart est journalisé. Refuser de démarrer
 * transformerait une erreur de déploiement bénigne en indisponibilité totale.
 */
export const loadRuntimeConfig = async (): Promise<RuntimeConfig> => {
  try {
    const response = await fetch(CONFIG_URL, { cache: 'no-cache' });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload: unknown = await response.json();
    const record =
      typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>) : {};
    loaded = {
      tokenRenewalMarginSeconds: positiveInteger(
        record.tokenRenewalMarginSeconds,
        DEFAULTS.tokenRenewalMarginSeconds,
      ),
      streamIdleTimeoutSeconds: positiveInteger(
        record.streamIdleTimeoutSeconds,
        DEFAULTS.streamIdleTimeoutSeconds,
      ),
      maxReattachments: positiveInteger(record.maxReattachments, DEFAULTS.maxReattachments),
    };
  } catch (error) {
    console.warn('[config] configuration d\'exécution indisponible, défauts appliqués', error);
    loaded = DEFAULTS;
  }
  return loaded;
};

export const getRuntimeConfig = (): RuntimeConfig => loaded;
