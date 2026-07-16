# V1 — Synthèse Memory, sécurité et preuves

> Support court pour entretien technique, onboarding et revue d’architecture.
>
> Pour les protocoles détaillés, voir [`V1-MEMORY-SECURITY-TESTS-FR.md`](./V1-MEMORY-SECURITY-TESTS-FR.md).
>
> Dernière mise à jour : 16 juillet 2026.

## Architecture en une phrase

Le navigateur React s’authentifie avec Cognito, appelle API Gateway, puis une Lambda de sécurité dérive l’identité serveur avant d’invoquer AgentCore Runtime en IAM ; le Runtime appelle une Gateway MCP IAM, des Lambda tools et DynamoDB.

```text
React/CloudFront
  -> API Gateway + Cognito JWT
  -> Lambda Security Facade
  -> AgentCore Runtime IAM-only
  -> AgentCore Gateway MCP IAM
  -> Lambda Trip Tools
  -> DynamoDB
```

## Blocage principal rencontré

Les interactions étaient bien enregistrées dans AgentCore Memory, comme le montraient les événements `memory_saved`, mais les préférences n’étaient pas retrouvées dans une nouvelle session.

La cause était la différence entre :

- les **événements de mémoire**, écrits par `create_event` ;
- les **enregistrements longue durée**, produits uniquement lorsqu’une stratégie Memory les extrait.

La Memory ne possédait pas de stratégie `USER_PREFERENCE`. Le Runtime et son IAM d’écriture fonctionnaient donc, mais aucune préférence durable n’était créée dans le namespace interrogé.

## Solution mise en place

```text
Nom       : TravelPreferences
Type      : USER_PREFERENCE
Namespace : /travel/{actorId}/preferences
Statut    : ACTIVE
```

Le correctif comprend :

- configuration idempotente de la stratégie ;
- vérification fail-closed avant création ou mise à jour du Runtime ;
- contrôle strict du type, du statut, de la description et du namespace ;
- SDK de déploiement verrouillé à `boto3==1.43.46` ;
- validation du vrai modèle Botocore et tests avec `Stubber` ;
- plan Terraform de PR avec AgentCore explicitement activé ;
- logs redacted distinguant succès, absence de résultat et erreur ;
- mémoire récupérée traitée comme donnée utilisateur non fiable.

PR de référence : **#10**, merge commit :

```text
17cb5b96cd6f42a10df4740b07dc8e78a5dfebb9
```

## Difficultés d’industrialisation

### Faux positif Terraform

Le premier plan vert pouvait ne pas activer le contrôle-plane AgentCore. La modification Memory pouvait donc être absente du plan.

**Réponse :** une pipeline dédiée force `enable_agentcore_control_plane=true` et vérifie les adresses attendues dans le plan JSON.

### Dérive masquée

Un provisioner `local-exec` ne se rejoue pas sans changement de trigger.

**Réponse :** `ensure` est rejoué à chaque révision d’image et un second contrôle `check` bloque le Runtime si la stratégie n’est pas conforme.

### Mocks insuffisants

Un faux client Python peut accepter un payload que le SDK AWS réel rejetterait.

**Réponse :** validation du modèle Botocore et tests `Stubber` des appels `UpdateMemory`.

### Données Memory non fiables

Une préférence stockée peut contenir une tentative d’injection.

**Réponse :** le contenu récupéré est préfixé comme donnée non fiable et ne peut ni modifier le prompt système, ni les permissions, ni la liste des tools.

## Tests réalisés

### Automatisés

```text
Python Code Review          PASS
Commit Lint                 PASS
144 tests unitaires         PASS
Audit Python                PASS
Frontend lint/build/audit   PASS
Secret scan                 PASS
Terraform fmt/validate      PASS
Plan Terraform générique    PASS
Plan AgentCore forcé        PASS
Contrats Botocore réels     PASS
```

### Fonctionnel Memory

Scénario exécuté :

1. utilisateur A déclare trois préférences explicites ;
2. une nouvelle session A les restitue ;
3. un utilisateur B ne reçoit aucune préférence sentinelle de A.

Statut : **PASS déclaré par le testeur**.

Cette validation fonctionnelle doit être complétée par l’archivage des preuves techniques : logs redacted, SHA Git, version Runtime, identifiants de workflow et captures anonymisées.

## Sécurité : état honnête

Les contrôles d’architecture suivants sont implémentés :

- identité dérivée du claim Cognito `sub` côté serveur ;
- rejet des champs d’identité fournis par le navigateur ;
- Runtime accessible uniquement par le rôle de la façade ;
- Gateway MCP accessible uniquement par le rôle Runtime ;
- partition DynamoDB contrainte par l’identité injectée ;
- logs sans prompt, souvenir, JWT ou identifiant personnel brut.

Leur **validation E2E complète** reste conditionnée au passage et à l’archivage des tests négatifs JWT, IAM, CORS et isolation Trips détaillés dans l’annexe.

## Pitch entretien en trois minutes

> « Nous avions un agent de voyage sécurisé sur AgentCore. Les interactions étaient bien sauvegardées, mais l’agent oubliait les préférences dans une nouvelle session. Les logs montraient `memory_saved` sans erreur, mais aucun `memory_retrieved`. J’ai séparé mémoire événementielle et mémoire longue durée, puis identifié l’absence de stratégie `USER_PREFERENCE`.
>
> La difficulté ne se limitait pas au correctif AWS : le premier plan Terraform vert n’activait pas obligatoirement AgentCore, le provisioner pouvait masquer une dérive et les mocks ne validaient pas le vrai schéma Botocore. J’ai donc ajouté une stratégie isolée par `actorId`, verrouillé Boto3, testé les payloads avec Botocore Stubber, forcé un plan AgentCore en PR et rendu le déploiement fail-closed avec un `ensure` puis un `check`.
>
> Le scénario utilisateur A, nouvelle session A, puis utilisateur B a validé fonctionnellement la persistance cross-session et l’absence de fuite de la préférence sentinelle. Les 144 tests et les plans Terraform dédiés sont verts. Les tests de sécurité négatifs restants sont suivis séparément et ne sont pas présentés comme déjà prouvés. »

## Limites à ne pas sur-vendre

- Memory ne garantit pas le rappel exact de toute conversation.
- La V1 mémorise des préférences explicites, pas une histoire conversationnelle complète.
- Les tools Trips enregistrent un projet ; ils ne réservent aucun billet ou hôtel.
- Un test manuel PASS n’équivaut pas à une preuve technique archivée.
- Une CI verte ne suffit pas si le chemin modifié n’apparaît pas réellement dans le plan ou le test E2E.
