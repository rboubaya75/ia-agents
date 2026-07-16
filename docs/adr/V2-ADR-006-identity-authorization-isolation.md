# V2-ADR-006 — Identité, autorisation et isolation

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-001, V2-ADR-002, V2-ADR-003, V2-ADR-007, V2-ADR-010, V2-ADR-014, V2-ADR-015, V2-ADR-016, V2-ADR-017

## Contexte

La V1 isole les sessions, Memory et données Trips par acteur Cognito. La V2 ajoute des documents, vecteurs, APIs d’administration et potentiellement plusieurs tenants. L’identité ne peut pas être propagée depuis le payload client et l’isolation doit être cohérente entre S3, S3 Vectors, DynamoDB, Memory, Runtime et tools.

## Options

### Option A — Identité utilisateur uniquement

`actorId = sub`, sans notion de tenant.

**Avantages :** simplicité et continuité V1.

**Limites :** insuffisant pour les documents partagés ou l’administration par organisation.

### Option B — Tenant et utilisateur issus directement de claims client

Le frontend transmet ou sélectionne le tenant.

**Rejet proposé :** risque d’escalade horizontale et dépendance à une donnée non fiable.

### Option C — Tenant et utilisateur résolus côté serveur

L’acteur provient du claim Cognito `sub`. Le tenant, les rôles et les droits sont résolus côté serveur à partir de claims autorisés et/ou d’un registre d’autorisation. Le payload métier ne peut pas les surcharger.

## Décision proposée

Retenir **l’option C**.

```text
actorId = Cognito access-token claim sub
subjectId = hash(actorId)
tenantId = résolution serveur contrôlée
roles/scopes = claims autorisés + politique serveur
```

Le modèle doit fonctionner en mode mono-tenant pour le portfolio tout en conservant des clés et contrats compatibles avec une extension multi-tenant.

## Règles de confiance

- API Gateway valide le JWT ;
- FastAPI relit uniquement les claims nécessaires et applique la politique d’autorisation ;
- `actorId`, `tenantId`, rôles, groupes, scopes et clés de partition sont interdits dans le payload métier ;
- Runtime reçoit uniquement une `trustedIdentity` produite par FastAPI ;
- Runtime et les tools écrasent toute identité présente dans les arguments du modèle ;
- aucun token Cognito n’est transmis à Runtime, MCP ou aux tools.

## Modèle d’autorisation

Les décisions sont fondées sur :

1. identité authentifiée ;
2. tenant résolu côté serveur ;
3. action demandée ;
4. type et classification de ressource ;
5. ownership ou partage explicite ;
6. politique de rétention et de conformité.

Un refus est la valeur par défaut lorsqu’une information manque.

## Partitionnement et filtres

### DynamoDB

Les clés incluent le tenant et l’acteur selon le type de donnée. Les accès doivent utiliser des conditions et des clés connues côté serveur, sans scan cross-tenant.

### S3

Les objets utilisent des préfixes et tags dérivés côté serveur. Les URL présignées sont courtes, liées à une opération et limitées à un objet autorisé.

### S3 Vectors

Chaque vecteur porte des métadonnées filtrables minimales telles que `tenantId`, `documentId`, `version` et `status`. Toute requête applique un filtre tenant obligatoire construit côté serveur. Les métadonnées non filtrables peuvent contenir les références ou extraits qui ne servent pas à l’autorisation.

### AgentCore Memory

Le namespace est dérivé de l’identité de confiance et de la politique de mémoire. Memory ne stocke pas les données métier transactionnelles.

### Runtime et MCP

Les resource policies et identités AWS limitent FastAPI vers Runtime, puis Runtime vers Gateway. Les tools reçoivent une identité injectée et ignorent toute identité produite par le modèle.

## Journalisation et confidentialité

- identités et tenants hashés dans les logs ;
- aucun JWT, prompt brut ou document sensible en clair ;
- décisions d’autorisation journalisées avec code de politique et ressource pseudonymisée ;
- audit des changements de partage et d’administration ;
- rétention des traces distincte de celle des documents.

## Suppression

Une suppression utilisateur ou tenant coordonne :

- objets S3 ;
- vecteurs ;
- métadonnées DynamoDB ;
- Memory autorisée ;
- index de recherche et caches ;
- preuves conservées uniquement selon la politique applicable.

## Conséquences

- un registre ou adapter d’autorisation serveur est nécessaire ;
- les filtres S3 Vectors font partie du contrôle d’accès en profondeur mais ne remplacent pas l’autorisation applicative ;
- les schémas de clés doivent être figés avant ingestion à grande échelle ;
- les tests cross-user et cross-tenant deviennent bloquants.

## Preuves attendues

- injection de `actorId` ou `tenantId` refusée ;
- User A ne lit ni ne modifie les ressources de User B ;
- Tenant A ne récupère aucun vecteur de Tenant B ;
- URL présignée inutilisable hors ressource et durée autorisées ;
- Runtime et tools refusent toute identité non injectée ;
- suppression coordonnée source, métadonnées, vecteurs et Memory ;
- logs et traces sans identifiants bruts.

## Références AWS

- Cognito et authorizers JWT API Gateway ;
- S3 Vectors metadata filtering et IAM `s3vectors` ;
- EKS Pod Identity ;
- AgentCore Gateway MCP avec authentification IAM.
