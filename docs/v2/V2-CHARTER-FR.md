# Charte de cadrage — Secure AgentCore V2

- **Version :** 0.2
- **Branche :** `migration/secure-agentcore-v2`
- **Baseline :** V1 au commit `20d4b12cb4666fe66eefbdf6b1605fe8f74daa03`
- **Statut :** Draft

## 1. Finalité

La V2 transforme le socle agentique V1 en plateforme applicative Data et IA générative plus complète, exploitable et gouvernable. Elle ajoute FastAPI sur EKS, un RAG applicatif S3 Vectors, des agents custom, une observabilité distribuée et une cible GitLab CI avec OIDC AWS.

Les garanties V1 restent applicables tant qu’un ADR V2 ne les remplace pas explicitement : identité construite côté serveur, Runtime IAM-only, tools gouvernés, idempotence, logs redacted et preuves traçables.

## 2. Objectifs

- ingestion, administration et suppression de documents ;
- retrieval avec citations et provenance ;
- agents custom découplés du framework ;
- extension sécurisée des tools MCP ;
- frontend avec streaming, sources, suivi d’ingestion et confirmations ;
- Terraform, Helm et GitLab CI OIDC ;
- sécurité, observabilité, performance, coûts et restauration mesurables.

## 3. Périmètre

Sont inclus : HLD, ADR, dix LLD, EKS/FastAPI, RAG S3/S3 Vectors/DynamoDB, agents custom sous `/agents`, Bedrock Converse API, AgentCore Runtime comme runtime uniquement, Gateway MCP, frontend React, WAF, OpenTelemetry, CloudWatch, Secrets Manager, Terraform, Helm et tests industriels.

Sont exclus : Bedrock managed Agents, Bedrock Knowledge Bases, OpenSearch Serverless, production réelle, gouvernance client inventée et migration irréversible sans rollback.

## 4. Exigences d’architecture initiales

| ID | Exigence |
|---|---|
| V2-ARCH-001 | API Gateway demeure le front-door web tant qu’un ADR approuvé n’en décide autrement. |
| V2-ARCH-002 | Le navigateur ne produit jamais l’identité de confiance et ne connaît pas l’URL Runtime. |
| V2-ARCH-003 | AgentCore Runtime sert uniquement à l’exécution des agents custom. |
| V2-ARCH-004 | Strands ou LangGraph sont encapsulés derrière un adapter. |
| V2-ARCH-005 | Le backend applicatif cible FastAPI sur EKS. |
| V2-ARCH-006 | Le RAG applicatif repose sur S3, S3 Vectors et DynamoDB. |
| V2-ARCH-007 | Les modèles utilisent Bedrock Converse API. |
| V2-ARCH-008 | Les tools sont gouvernés via AgentCore Gateway MCP. |
| V2-ARCH-009 | Terraform et Helm sont les mécanismes déclaratifs de référence. |
| V2-ARCH-010 | GitLab CI avec OIDC AWS est la cible CI/CD. |

## 5. Exigences non fonctionnelles

- isolation utilisateur ou tenant ;
- IAM least privilege, chiffrement, Secrets Manager et redaction ;
- défense contre prompt injection, data poisoning et exfiltration par tool ;
- EKS multi-AZ, graceful shutdown et reprise idempotente ;
- budgets de timeout, tokens, tours et tools ;
- OpenTelemetry, CloudWatch, SLO et error budgets ;
- mesure des coûts Bedrock, embeddings, stockage et calcul ;
- sauvegarde, restauration, rollback et réhydratation testés.

## 6. Livrables obligatoires

### Architecture et gouvernance

- charte, roadmap, As-Is, To-Be et analyse des écarts ;
- catalogue d’exigences et matrice de traçabilité ;
- ADR structurants ;
- HLD approuvé puis As-Built ;
- threat model, modèle de données, contrats OpenAPI/MCP et runbooks.

### Dix LLD canoniques

1. `V2-LLD-001` Plateforme AWS, réseau, EKS et FastAPI ;
2. `V2-LLD-002` RAG et ingestion documentaire ;
3. `V2-LLD-003` Agents et orchestration ;
4. `V2-LLD-004` AgentCore Gateway MCP et tools ;
5. `V2-LLD-005` Identité, sécurité et conformité ;
6. `V2-LLD-006` Données, mémoire, rétention et restauration ;
7. `V2-LLD-007` Observabilité, SLO et FinOps ;
8. `V2-LLD-008` CI/CD, Terraform, Helm et promotion ;
9. `V2-LLD-009` Stratégie de tests et preuves ;
10. `V2-LLD-010` Frontend React V2.

Le catalogue `docs/lld/LLD-V2-INDEX-FR.md` constitue la source canonique des identifiants et dépendances.

## 7. Definition of Done V2

La V2 est clôturable lorsque les ADR sont décidés, le HLD et les LLD sont As-Built, l’environnement est reproductible, le RAG est évalué sur dataset versionné, l’isolation et la sécurité négative sont prouvées, les coûts et performances sont mesurés, la restauration est testée et les preuves sont archivées.

## 8. Risques initiaux

| Risque | Réponse attendue |
|---|---|
| Complexité multi-agent | Orchestrateur minimal et justification de chaque agent. |
| Retrieval insuffisant | Dataset, métriques et citations obligatoires. |
| Prompt injection documentaire | Contenus traités comme données non fiables. |
| Couplage framework | Adapter obligatoire. |
| Ingestion non idempotente | Identifiants déterministes et état DynamoDB. |
| Dérive des coûts | Quotas, télémétrie et tests de charge. |
| Migration CI prématurée | Parité avant retrait des workflows existants. |

## 9. Gate V2-G0

La gate est franchie lorsque la charte, la roadmap, le HLD initial, le catalogue des dix LLD et le backlog ADR sont disponibles et revus. Elle autorise l’instruction des ADR et du HLD, pas l’implémentation structurante.
