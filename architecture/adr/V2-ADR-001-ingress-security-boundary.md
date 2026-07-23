# V2-ADR-001 — Ingress et frontière de sécurité

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-002, V2-ADR-006, V2-ADR-011, V2-ADR-016

## Contexte

La V1 utilise API Gateway, une Lambda Security Facade et AgentCore Runtime IAM-only. La V2 introduit FastAPI sur ECS/Fargate pour les APIs conversationnelles, documentaires et administratives. La frontière de sécurité doit rester côté serveur, préserver l’identité de confiance et permettre à terme le streaming.

## Exigences

- API Gateway reste le front-door web ;
- le navigateur ne connaît jamais l’URL AgentCore Runtime ;
- l’identité, les deadlines, quotas et champs internes sont construits côté serveur ;
- Runtime reste IAM-only ;
- le chemin doit supporter auth, CORS, WAF, throttling, observabilité et rollback ;
- aucune identité ou configuration de modèle/tool fournie par le client n’est acceptée.

## Options

### Option A — Conserver la façade Lambda pour la conversation

API Gateway appelle la façade Lambda pour `/agent/invoke` et FastAPI uniquement pour les APIs documentaires.

**Avantages :** compatibilité V1 et rollback simple.

**Limites :** deux frontières applicatives, logique dupliquée et streaming plus complexe.

### Option B — FastAPI devient la frontière applicative

API Gateway appelle FastAPI sur ECS/Fargate par intégration privée. FastAPI valide le contrat, résout l’autorisation, construit l’identité de confiance et invoque AgentCore Runtime avec IAM.

**Avantages :** frontière unique, contrats homogènes, meilleure intégration du retrieval et du streaming.

**Limites :** dépendance accrue à ECS/Fargate et migration plus structurante.

### Option C — Routage hybride durable

API Gateway conserve deux chemins permanents, Lambda pour les conversations et FastAPI pour les documents.

**Avantages :** séparation immédiate des capacités.

**Limites :** complexité durable, observabilité fragmentée et duplication des politiques.

## Décision proposée

Retenir **l’option B comme cible**, avec une transition contrôlée :

```text
Browser
  -> CloudFront + WAF
  -> API Gateway + Cognito JWT
  -> intégration privée VPC Link
  -> load balancer interne
  -> FastAPI sur ECS/Fargate
  -> AgentCore Runtime IAM-only
```

La façade Lambda V1 reste disponible uniquement comme mécanisme de rollback pendant la migration. Elle n’est pas une seconde frontière nominale V2.

## Contrôles obligatoires

FastAPI doit :

- appliquer une allowlist stricte des routes et champs ;
- dériver l’identité depuis le contexte JWT validé et une source serveur ;
- rejeter `actorId`, `tenantId`, `trustedIdentity`, `modelOverride`, `systemPrompt` et `toolName` côté client ;
- produire `requestId`, `operationId` contrôlé et deadline ;
- appliquer quotas et limites de taille ;
- invoquer Runtime avec une identité AWS dédiée au workload ;
- normaliser les erreurs sans exposer les détails internes ;
- journaliser uniquement des identifiants hashés et données redacted.

## Conséquences

- ECS/Fargate et son chemin privé deviennent critiques pour les conversations ; le
  dimensionnement précis (launch type, sécurité réseau, coût) est décidé par `V2-ADR-007`, qui
  réalise physiquement le chemin décidé ici — la dépendance ne va que dans ce sens (007 dépend de
  001, pas l'inverse) ;
- la disponibilité et le coût minimum du chemin doivent être acceptés, y compris le load balancer
  interne lui-même (composant always-on, facturé indépendamment du trafic — pas seulement le
  calcul ECS/Fargate) ;
- le LLD plateforme doit détailler VPC Link, load balancer, health checks et egress ;
- une campagne de non-régression doit comparer les chemins V1 et V2 ;
- le rollback consiste à réorienter la route conversation vers la façade V1.

## Preuves attendues

- JWT invalide, mauvais client et identité injectée refusés ;
- Runtime direct refusé ;
- appels ECS vers Runtime limités par IAM/resource policy ;
- CORS et WAF validés ;
- corrélation bout en bout ;
- test de bascule vers le chemin V1 ;
- latence et coût comparés aux parcours V1.

## Références AWS

- API Gateway private integrations et VPC Link ;
- Amazon ECS (launch type Fargate) avec IAM Task Roles ;
- Amazon Bedrock AgentCore Runtime avec authentification IAM.
