# WildRydes — Secure AgentCore V2

- **Branche :** `migration/secure-agentcore-v2`
- **Baseline V1 :** `20d4b12cb4666fe66eefbdf6b1605fe8f74daa03`
- **Statut V2 :** cadrage et architecture documentaire
- **Environnement initial :** `test`
- **Principe :** aucun développement structurant avant validation du HLD et des LLD concernés

## Démarrage V2

La V1 est considérée close par décision projet et devient la baseline de la V2. Les garanties V1 restent applicables tant qu’un ADR V2 n’a pas explicitement remplacé une décision : identité de confiance construite côté serveur, Runtime IAM-only, tools MCP gouvernés, idempotence des mutations, logs redacted et tests industriels.

Le référentiel V2 commence ici :

- [`architecture/README.md`](architecture/README.md) — index et gouvernance documentaire ;
- [`architecture/governance/V2-CHARTER-FR.md`](architecture/governance/V2-CHARTER-FR.md) — vision, périmètre, exigences et Definition of Done ;
- [`architecture/governance/V2-ROADMAP-FR.md`](architecture/governance/V2-ROADMAP-FR.md) — phases et gates ;
- [`architecture/hld/HLD-Secure-AgentCore-V2-FR.md`](architecture/hld/HLD-Secure-AgentCore-V2-FR.md) — HLD initial ;
- [`architecture/lld/LLD-V2-INDEX-FR.md`](architecture/lld/LLD-V2-INDEX-FR.md) — catalogue des LLD obligatoires ;
- [`architecture/adr/V2-ADR-BACKLOG-FR.md`](architecture/adr/V2-ADR-BACKLOG-FR.md) — backlog des décisions structurantes.

## Cycle de gouvernance V2

```text
Exigences
  -> options et ADR
  -> HLD
  -> validation HLD
  -> LLD par domaine
  -> validation LLD
  -> implémentation
  -> tests et preuves
  -> documentation As-Built
  -> réception
```

## Cible technique V2

- Python 3.12 et FastAPI ;
- backend applicatif sur ECS/Fargate ;
- agents custom sous `/agents` ;
- Strands ou LangGraph derrière un adapter optionnel ;
- Bedrock AgentCore Runtime comme runtime d’exécution uniquement ;
- Bedrock Converse API ;
- embeddings Bedrock configurables ;
- RAG applicatif avec S3 Vectors, DynamoDB et S3 ;
- Cognito ;
- React, TypeScript et Vite ;
- frontend S3 privé, CloudFront et WAF ;
- AgentCore Gateway MCP ;
- Terraform ;
- GitLab CI avec OIDC AWS comme cible ;
- OpenTelemetry et CloudWatch ;
- Secrets Manager et KMS.

Sont explicitement exclus :

- Bedrock managed Agents ;
- Bedrock Knowledge Bases ;
- OpenSearch Serverless.

## Architecture To-Be initiale

```text
Browser / React
  -> CloudFront + WAF
       -> S3 privé
       -> API Gateway + Cognito
            -> frontière applicative à décider par ADR
                 -> FastAPI sur ECS/Fargate
                      -> APIs conversation et documents
                      -> ingestion et retrieval applicatifs
                 -> AgentCore Runtime IAM-only
                      -> agents custom
                      -> Bedrock Converse API
                      -> AgentCore Memory
                      -> AgentCore Gateway MCP
                           -> tools métier

Données
  -> S3 : documents sources
  -> S3 Vectors : index vectoriel
  -> DynamoDB : métadonnées, états et données métier
  -> CloudWatch : logs, métriques et traces OpenTelemetry
```

Cette vue est un point de départ. Le chemin d’ingress, la répartition FastAPI/Runtime, le modèle d’isolation et le pipeline d’ingestion restent soumis aux ADR V2.

## Gates documentaires

### V2-G0 — Baseline et cadrage

- baseline V1 référencée ;
- charte et roadmap disponibles ;
- HLD initial disponible ;
- catalogue LLD et backlog ADR disponibles.

### V2-G1 — HLD approuvé

- exigences majeures traçables ;
- ADR structurants décidés ;
- flux, zones de confiance, données, disponibilité, coûts et migration documentés.

### V2-G2 — LLD approuvés

- conception détaillée disponible pour chaque domaine de la tranche ;
- contrats, IAM, réseau, erreurs, tests et rollback détaillés ;
- aucun choix critique implicite.

## Catalogue LLD initial

1. plateforme AWS, réseau, ECS et FastAPI ;
2. RAG et ingestion documentaire ;
3. agents et orchestration ;
4. AgentCore Gateway MCP et tools ;
5. identité, sécurité et conformité ;
6. données, mémoire, rétention et restauration ;
7. observabilité, SLO et FinOps ;
8. CI/CD, Terraform et promotion ;
9. stratégie de tests et preuves ;
10. frontend React V2.

## Baseline V1 conservée

```text
Browser / React
  -> CloudFront / S3 privé
  -> Cognito
  -> API Gateway HTTP API
  -> Lambda Security Facade
  -> AgentCore Runtime IAM-only
       -> Bedrock
       -> AgentCore Memory
       -> AgentCore Gateway MCP
            -> Trip Tools Lambda
            -> DynamoDB Trips
```

Le navigateur ne connaît jamais l’URL technique AgentCore Runtime. L’identité de confiance provient des claims Cognito validés et est reconstruite côté serveur. Runtime écrase l’identité et le contexte avant les appels aux tools.

Les quatre tools V1 restent :

```text
create_trip
get_trips
get_trip
update_trip
```

La documentation V1 reste disponible :

- [`docs/hld/HLD-WildRydes-Agentic-AI-FR.md`](docs/hld/HLD-WildRydes-Agentic-AI-FR.md) ;
- [`docs/lld/LLD-WildRydes-Agentic-AI-FR.md`](docs/lld/LLD-WildRydes-Agentic-AI-FR.md) ;
- [`docs/adr/ADR-0005-lambda-security-facade-agentcore-runtime-iam.md`](docs/adr/ADR-0005-lambda-security-facade-agentcore-runtime-iam.md) ;
- [`docs/adr/ADR-0006-idempotency-deadline-mcp-lifecycle.md`](docs/adr/ADR-0006-idempotency-deadline-mcp-lifecycle.md) ;
- [`tests/README.md`](tests/README.md) — stratégie et matrice des tests industriels.

## Discipline de livraison

Pour chaque phase :

1. présenter le plan ;
2. limiter les modifications au périmètre validé ;
3. résumer les fichiers changés ;
4. exécuter lint, typecheck et tests pertinents ;
5. signaler tous les échecs et limites ;
6. attendre validation avant la phase suivante.

Aucun déploiement, `terraform apply`, `terraform destroy`, merge ou changement d’environnement ne doit être implicite.
