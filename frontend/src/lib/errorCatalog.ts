/**
 * Traduction des codes d'erreur (V2-LLD-010 §11).
 *
 * La table est **close**. Un code absent produit un message générique et une trace —
 * jamais l'affichage du code brut, qui n'apprend rien à l'utilisateur et expose une
 * information de structure interne (§11.2).
 *
 * Les familles ne sont pas décoratives : `V2-ADR-016` impose que les refus pour quota,
 * pour autorisation et pour throttling soient trois séries distinctes, et la raison vaut
 * à l'écran — les trois appellent trois conduites différentes de l'utilisateur (§11.1).
 */

export type ErrorFamily =
  | 'authorization'
  | 'quota'
  | 'degradation'
  | 'contract'
  | 'unknown';

export interface TranslatedError {
  family: ErrorFamily;
  title: string;
  detail: string;
  /** Vrai lorsque réémettre la demande a un sens pour l'utilisateur. */
  retryable: boolean;
}

const GENERIC: TranslatedError = {
  family: 'unknown',
  title: 'La demande n\'a pas abouti',
  detail: 'Une erreur inattendue est survenue. Réessayez ; si cela persiste, signalez-le.',
  retryable: true,
};

const CATALOG: Readonly<Record<string, TranslatedError>> = {
  // Invocation agentique — V2-LLD-003 §3.2
  budget_exceeded: {
    family: 'quota',
    title: 'Capacité conversationnelle atteinte',
    detail:
      'La capacité allouée à cette conversation est consommée. Ouvrez une nouvelle conversation ou attendez le renouvellement de la fenêtre.',
    retryable: false,
  },
  deadline_exceeded: {
    family: 'degradation',
    title: 'Durée maximale atteinte',
    detail: 'La demande a dépassé le temps qui lui est alloué. Réessayer plus tard a un sens.',
    retryable: true,
  },
  tool_denied: {
    family: 'authorization',
    title: 'Action non autorisée',
    detail: 'Cette action n\'est pas permise à votre compte. Réessayer ne changera rien.',
    retryable: false,
  },
  model_throttled: {
    family: 'degradation',
    title: 'Plateforme sous contrainte',
    detail: 'Le service de génération est momentanément saturé. Réessayez dans quelques instants.',
    retryable: true,
  },
  tool_unavailable: {
    family: 'degradation',
    title: 'Outil indisponible',
    detail: 'Un outil nécessaire à cette demande est momentanément indisponible.',
    retryable: true,
  },
  memory_unavailable: {
    family: 'degradation',
    title: 'Mémoire de conversation indisponible',
    detail:
      'L\'historique de la conversation n\'a pas pu être consulté. La réponse peut ignorer les échanges précédents.',
    retryable: true,
  },
  // Émis par FastAPI lorsqu'une défaillance n'est attribuable à aucune des causes
  // ci-dessus. Ce code n'appartient pas au jeu de `V2-LLD-003 §3.2` — voir la note de
  // livraison du lot ; il est traité ici pour ne pas retomber sur le message générique.
  internal_error: {
    family: 'degradation',
    title: 'Erreur interne',
    detail: 'Le service n\'a pas pu traiter la demande. Réessayez dans quelques instants.',
    retryable: true,
  },

  // Contrat — V2-LLD-005 §4.1. Un champ interdit est un défaut applicatif, pas une
  // erreur d'utilisation : l'utilisateur ne peut rien y faire (§11.1).
  forbidden_field: {
    family: 'contract',
    title: 'Demande refusée',
    detail: 'La demande n\'est pas conforme au contrat du service. L\'incident a été enregistré.',
    retryable: false,
  },
};

/**
 * Quotas — `V2-ADR-016` en borne trois, et les trois se rencontrent dans cette interface
 * (§11.3). Seul le quota de commandes `pending` a une sortie que l'utilisateur détient,
 * et l'interface doit le dire : sans cela il fait face à un blocage dont la cause est à
 * l'écran et dont il ignore le lien.
 */
export const QUOTA_MESSAGES: Readonly<Record<string, TranslatedError>> = {
  identity_tokens: {
    family: 'quota',
    title: 'Capacité conversationnelle atteinte',
    detail: 'La capacité allouée sur la fenêtre en cours est consommée. Attendez son renouvellement.',
    retryable: false,
  },
  pending_commands: {
    family: 'quota',
    title: 'Trop de propositions en attente',
    detail:
      'Confirmez ou laissez expirer les propositions en attente pour pouvoir en demander de nouvelles.',
    retryable: false,
  },
  documents_ingesting: {
    family: 'quota',
    title: 'Trop de documents en cours d\'ingestion',
    detail: 'Attendez la fin des ingestions en cours avant d\'en déposer de nouveaux.',
    retryable: false,
  },
};

export interface UnknownCodeReport {
  code: string;
}

/**
 * Traduit un code. `onUnknown` reçoit les codes absents de la table close, pour la trace
 * du §14.3 — le code n'est jamais rendu à l'écran.
 */
export const translateErrorCode = (
  code: string,
  onUnknown?: (report: UnknownCodeReport) => void,
): TranslatedError => {
  const known = CATALOG[code] ?? QUOTA_MESSAGES[code];
  if (known) {
    return known;
  }
  onUnknown?.({ code });
  console.warn('[error] code inconnu, message générique rendu', { code });
  return GENERIC;
};

export const isKnownErrorCode = (code: string): boolean =>
  Object.hasOwn(CATALOG, code) || Object.hasOwn(QUOTA_MESSAGES, code);
