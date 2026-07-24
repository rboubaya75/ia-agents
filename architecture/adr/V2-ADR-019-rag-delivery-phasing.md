# V2-ADR-019 — Phasage de livraison du RAG (Knowledge Bases en V2, pipeline applicatif en V3)

- **Statut :** Accepted
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-002, V2-ADR-003, V2-ADR-004, V2-ADR-006
- **Supersede (périmètre V2 uniquement) :** l'implémentation V2 décrite par `V2-ADR-003` et
  `V2-ADR-004` (voir « Relation avec V2-ADR-003 et V2-ADR-004 »).

## Contexte

`V2-ADR-003` et `V2-ADR-004` ont décidé un RAG entièrement applicatif : FastAPI est propriétaire du
parsing, du chunking versionné, des embeddings, de l'écriture S3 Vectors, des métadonnées DynamoDB,
de la suppression coordonnée et du retrieval. Ce choix maximise la maîtrise et l'auditabilité, mais
il déplace vers l'équipe un volume de code de fiabilité important : parsing multi-format (PDF
natif/scanné, DOCX, tableaux), machine à états d'ingestion, saga de suppression coordonnée sur trois
magasins sans transaction distribuée, et surtout la gestion d'une migration de modèle d'embedding
(réindexation de l'intégralité du corpus lorsqu'un modèle est déprécié).

Deux éléments nouveaux justifient de rouvrir la décision **pour la phase V2** :

1. **Bedrock Knowledge Bases peut désormais s'adosser à S3 Vectors** comme magasin vectoriel
   sous-jacent (référence AWS ci-dessous). Le principal grief de coût contre KB — l'obligation
   d'OpenSearch Serverless, facturé à quelques centaines de dollars par mois même sans trafic —
   disparaît. KB adossé à S3 Vectors reste dans l'empreinte de stockage déjà retenue par la charte.
2. **Le périmètre V2 est un portfolio**, pas une production multi-tenant à grande échelle. Les
   besoins qui justifient le pipeline applicatif (RGPD réel avec effacement coordonné, audit fin du
   retrieval, corpus > 50 000 chunks, migration d'embeddings planifiée) sont des besoins de la
   phase suivante, pas de la livraison V2.

Cet ADR arbitre explicitement entre la maîtrise maximale (coûteuse à construire) et la vitesse de
livraison V2 (déléguée à un service managé), et fixe le chemin de migration vers la cible
applicative.

## Exigences concernées

- livrer une capacité RAG fonctionnelle en V2 sans mobiliser l'équipe sur ~4 000 lignes de code de
  fiabilité (parsing, chunking, saga de suppression, migration d'embeddings) ;
- préserver l'isolation multi-tenant : aucun chunk d'un tenant ne doit atteindre un autre ;
- conserver FastAPI comme frontière et propriétaire applicatif du retrieval (cohérence CAM) ;
- garder AgentCore Runtime hors du retrieval et de l'indexation (`V2-ADR-002`) ;
- ne pas fermer la porte au pipeline applicatif, retenu comme cible d'évolution.

## Options

### Option A — Pipeline applicatif dès la V2 (statu quo `V2-ADR-003` / `V2-ADR-004`)

FastAPI implémente l'intégralité du pipeline en V2.

**Avantages :** maîtrise et auditabilité maximales immédiates ; isolation garantie par
construction ; portabilité du magasin vectoriel.

**Limites :** ~4 000 lignes de code de fiabilité à écrire, tester et exploiter avant toute autre
tranche ; parsing multi-format comme premier point de défaillance ; migration d'embeddings à
outiller dès le départ. Ce coût retarde les autres domaines structurants (identité, CI/CD,
observabilité, frontend) pour des besoins qui n'existent pas encore à l'échelle V2.

### Option B — Knowledge Bases adossé à S3 Vectors en V2, pipeline applicatif en cible V3

KB assure parsing, chunking, embeddings, indexation et suppression ; le magasin vectoriel reste
S3 Vectors. FastAPI conserve la frontière : il déclenche l'ingestion, appelle l'API `Retrieve` (et
non `RetrieveAndGenerate`), **applique le filtrage tenant/ACL côté serveur après retrieval**,
construit le `retrievalContext` borné et résout les citations. Le pipeline applicatif de
`V2-ADR-003` / `V2-ADR-004` devient la cible V3.

**Avantages :** ~2 700 lignes de code de fiabilité non écrites en V2 (parsing, chunking, saga de
suppression, migration d'embeddings) ; time-to-market ; S3 Vectors validé par AWS comme backend de
KB ; coût V2 comparable au pipeline applicatif (pas d'OpenSearch Serverless).

**Limites :** modèle d'ingestion asynchrone de KB (`StartIngestionJob`) — latence post-ingestion en
minutes, non en secondes ; gouvernance du retrieval interne à KB moins fine ; le filtrage tenant en
V2 repose sur la configuration KB + le post-filtrage FastAPI, non sur une garantie par construction.

### Option C — Knowledge Bases comme cible permanente

Abandonner définitivement le pipeline applicatif.

**Rejet proposé :** ferme la porte aux besoins de la phase suivante (audit fin, effacement RGPD
coordonné, portabilité totale) déjà instruits par `V2-ADR-003`, `V2-ADR-004` et `V2-ADR-006`, sans
gain par rapport à un phasage explicite.

## Décision

Retenir **l'option B**.

```text
Phase V2 (livraison portfolio)
  Upload (FastAPI)
    -> S3 source (préfixe géré côté serveur)
    -> déclenchement ingestion KB (StartIngestionJob)
    -> KB : parsing, chunking, embeddings, indexation dans S3 Vectors
  Question (FastAPI)
    -> KB Retrieve (candidats + scores)
    -> FastAPI : filtrage tenant + ACL (obligatoire, côté serveur)
    -> FastAPI : construction du retrievalContext borné + citations
    -> AgentCore Runtime (IAM-only, ne fait jamais de retrieval)

Phase V3 (cible, V2-ADR-003 / V2-ADR-004)
  FastAPI reprend parsing, chunking, embeddings, saga de suppression et retrieval directs sur
  S3 Vectors ; l'adapter de magasin vectoriel est le seul point d'échange.
```

Le passage à KB pour la V2 est conditionné à une **précondition de vérification** : disponibilité de
Bedrock Knowledge Bases adossé à S3 Vectors dans la région `eu-west-3`. Si cette disponibilité n'est
pas confirmée, l'option A (pipeline applicatif) reste la décision par défaut, sans nouvel ADR.

## Ce que FastAPI conserve en V2 (non négociable)

Même avec KB, FastAPI reste la frontière et le propriétaire applicatif du retrieval dans la CAM :

- **filtrage tenant et ACL après retrieval** — un chunk retourné par KB n'atteint jamais le modèle
  sans que FastAPI ait vérifié `tenantId` et les droits d'accès côté serveur ; l'API `Retrieve` est
  utilisée, jamais `RetrieveAndGenerate` (qui injecterait le contexte sans point de contrôle) ;
- **construction du `retrievalContext` borné** (`ok | degraded | skipped`), conforme à
  `architecture/hld/runtime-contract.md` ;
- **résolution des citations** vers des sources réelles et autorisées via DynamoDB ;
- **traitement du contenu documentaire comme donnée non fiable** (principe `V2-ADR-002`).

Ces contrôles sont identiques en V2 et V3 : ils ne dépendent pas du moteur d'ingestion et survivent
à la migration.

## Trade-offs et coûts assumés

Cet arbitrage a un coût explicite, assumé pour la phase V2 :

- **Latence d'ingestion.** `StartIngestionJob` est asynchrone : un document uploadé n'est pas
  requêtable en quelques secondes mais après le job KB (ordre de la minute). Le suivi d'état exposé
  à l'utilisateur (`architecture/hld` §6.2) doit refléter cette latence. En V3, S3 Vectors en
  écriture directe rétablit une cohérence quasi immédiate.
- **Gouvernance du retrieval moins fine.** KB masque une partie des décisions internes (stratégie
  de chunking par défaut, ranking). L'audit détaillé « pourquoi ce chunk, quel score, quel filtre »
  est partiel en V2 ; il devient complet en V3. L'auditabilité de l'**autorisation** reste totale
  dès la V2, car le filtrage tenant/ACL est côté FastAPI.
- **Isolation configurée, pas garantie par construction.** En V2, l'isolation repose sur la
  configuration KB *et* le post-filtrage FastAPI. Le post-filtrage FastAPI est la ligne de défense
  qui doit être testée en priorité (test cross-tenant bloquant). En V3, le filtre `tenantId`
  construit côté serveur avant la requête S3 Vectors rend l'omission impossible par design.
- **Migration d'embeddings déléguée.** En V2, un changement de modèle d'embedding est géré par KB
  (resynchronisation). En V3, cette responsabilité revient à l'équipe (`V2-ADR-013`), avec suivi de
  `embeddingModelId` / `embeddingVersion` par chunk (déjà prévus par `V2-ADR-003`).
- **Dépendance à un service managé supplémentaire.** KB devient une dépendance d'exploitation V2
  (quotas, disponibilité régionale, évolutions d'API). La portabilité totale n'est retrouvée qu'en
  V3.

En contrepartie, ~2 700 lignes de code de fiabilité (parsing multi-format, chunking, saga de
suppression, jobs de migration et de réconciliation) ne sont ni écrites, ni testées, ni exploitées
en V2, ce qui libère la capacité de l'équipe pour les autres domaines structurants.

## Chemin de migration V2 vers V3

- FastAPI accède au retrieval via un **adapter de magasin vectoriel** unique. En V2, l'adapter
  appelle `KB Retrieve` ; en V3, il interroge S3 Vectors directement. FastAPI, AgentCore Runtime,
  les agents, les tools MCP, le HLD et la CAM ne changent pas — seul l'adapter change.
- Les schémas de métadonnées de chunk (`tenantId`, `documentId`, `version`, `status`) fixés par
  `V2-ADR-006` et `V2-ADR-003` sont respectés dès la V2, y compris dans la configuration KB, pour
  que la migration ne réécrive pas les contrats d'isolation.
- La bascule V3 réutilise le pipeline d'ingestion applicatif de `V2-ADR-004` (SQS + worker ECS),
  déjà décidé et documenté ; elle n'invente pas de nouveau mécanisme.

## Relation avec V2-ADR-003 et V2-ADR-004

`V2-ADR-003` et `V2-ADR-004` restent `Accepted` en tant que **cible V3 documentée**. Le présent ADR
supersede leur volet « implémentation V2 » : pendant la phase V2, l'ingestion, le chunking, les
embeddings et l'indexation sont assurés par KB, et non par le pipeline SQS + worker ECS. Les
garanties d'isolation, de citations et de suppression sans résidu qu'ils exigent restent
applicables ; leur réalisation technique diffère selon la phase.

## Impacts gouvernance

- **Charte** — `architecture/governance/V2-CHARTER-FR.md` est amendée : Bedrock Knowledge Bases
  adossé à S3 Vectors entre dans le périmètre pour la phase V2 ; OpenSearch Serverless reste hors
  périmètre ; `V2-ARCH-006` est reformulée pour distinguer l'implémentation V2 (KB) de la cible V3
  (applicative).
- **HLD** — le principe « Bedrock Knowledge Bases n'est pas utilisé » est reformulé, et le flux
  d'ingestion §6.2 précise la réalisation V2 par KB.
- **CAM** — la ligne listant la dépendance à Knowledge Bases comme violation est reformulée : KB
  est autorisé en V2 sous réserve que FastAPI conserve la propriété du retrieval et du filtrage.

## Conséquences

- une dépendance d'exploitation à Bedrock Knowledge Bases est introduite pour la V2 (quotas,
  disponibilité `eu-west-3`, redéclenchement de synchronisation) ;
- le pipeline SQS + worker ECS `ingestion` de `V2-ADR-004` n'est pas provisionné en V2 (impact
  Terraform : le module ingestion applicatif est différé à la V3) ;
- l'adapter de magasin vectoriel FastAPI devient un point de conception critique pour garantir la
  réversibilité V2 → V3 ;
- le test cross-tenant sur le post-filtrage FastAPI devient bloquant dès la V2 ;
- le suivi d'ingestion exposé à l'utilisateur doit intégrer la latence asynchrone de KB.

## Preuves attendues

- disponibilité de Knowledge Bases adossé à S3 Vectors en `eu-west-3` vérifiée avant bascule ;
- une requête ne retourne jamais de chunk d'un autre tenant, le post-filtrage FastAPI étant la
  ligne de défense testée (prolonge les preuves de `V2-ADR-006`) ;
- `RetrieveAndGenerate` n'est jamais appelé ; seul `Retrieve` l'est, suivi du filtrage FastAPI ;
- chaque citation renvoyée est résolvable vers une source réelle et autorisée ;
- `retrievalContext.status = degraded` renvoyé lorsque KB ou S3 Vectors est indisponible, sans
  échec de la conversation ;
- l'adapter de magasin vectoriel est remplaçable par une implémentation S3 Vectors directe sans
  modification de FastAPI hors adapter (preuve de réversibilité V3).

## Références AWS

- Amazon Bedrock Knowledge Bases avec Amazon S3 Vectors comme magasin vectoriel ;
- Amazon Bedrock Knowledge Bases API `Retrieve` (récupération sans génération) ;
- Amazon S3 Vectors (stockage et filtrage de métadonnées) ;
- Amazon Bedrock (modèles d'embedding configurables).
