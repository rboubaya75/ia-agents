# Charte de cadrage — Secure AgentCore V2

- **Version :** 0.1
- **Branche :** `migration/secure-agentcore-v2`
- **Baseline :** V1 au commit `20d4b12cb4666fe66eefbdf6b1605fe8f74daa03`
- **Statut :** Draft

## 1. Finalité

La V2 transforme le socle agentique V1 en plateforme applicative Data et IA générative plus complète, exploitable et gouvernable. Elle ajoute un backend applicatif sur EKS, un RAG applicatif fondé sur S3 Vectors, une architecture d’agents custom, une observabilité distribuée et une chaîne CI/CD cible GitLab CI avec OIDC AWS.

La V2 doit conserver les garanties acquises en V1 : frontière d’identité serveur, IAM least privilege, tools gouvernés, idempotence des mutations, redaction des logs et traçabilité des preuves.

## 2. Baseline V1 réutilisée

La baseline comprend notamment :

- frontend React/TypeScript/Vite sur S3 privé et CloudFront ;
- Cognito ;
- API Gateway ;
- Lambda Security Facade ;
- AgentCore Runtime IAM-only ;
- Bedrock via modèle européen ;
- AgentCore Memory ;
- AgentCore Gateway MCP ;
- tools Trips ;
- DynamoDB ;
- Terraform ;
- tests unitaires, sécurité et qualité industrielle.

La V1 n’est pas modifiée rétroactivement. Les changements V2 sont introduits sur une branche dédiée et par décisions explicites.

## 3. Objectifs V2

### 3.1 Objectifs fonctionnels

- ingérer et administrer des documents ;
- indexer les documents dans S3 Vectors ;
- répondre avec retrieval, citations et provenance ;
- orchestrer des agents custom spécialisés ;
- étendre les tools MCP sans dégrader les garanties V1 ;
- fournir une expérience frontend avec streaming, sources, suivi d’ingestion et confirmations ;
- gérer mémoire, documents et données métier selon des politiques distinctes.

### 3.2 Objectifs techniques

- introduire FastAPI sur EKS ;
- utiliser Bedrock Converse API ;
- rendre les embeddings Bedrock configurables ;
- isoler le code métier des frameworks d’agents ;
- instrumenter les flux avec OpenTelemetry ;
- centraliser métriques, traces et logs dans CloudWatch ;
- déployer via Terraform, Helm et GitLab CI avec OIDC AWS ;
- produire des preuves de sécurité, qualité, performance, coût et résilience.

### 3.3 Objectifs d’architecture d’entreprise

- fournir des architectures de référence réutilisables ;
- expliciter les compromis de sécurité, disponibilité, complexité et coûts ;
- produire une trajectoire As-Is vers To-Be ;
- maintenir des ADR et des runbooks exploitables ;
- définir des standards de développement, de tests et d’exploitation.

## 4. Périmètre

### 4.1 Inclus

- cadrage et gouvernance V2 ;
- HLD et LLD par domaine ;
- backend FastAPI sur EKS ;
- agents custom sous `/agents` ;
- adapter optionnel Strands ou LangGraph ;
- AgentCore Runtime comme runtime d’exécution ;
- Bedrock Converse API ;
- RAG applicatif S3, S3 Vectors et DynamoDB ;
- pipeline d’ingestion documentaire ;
- AgentCore Gateway MCP et tools V2 ;
- frontend V2 ;
- WAF ;
- observabilité OpenTelemetry/CloudWatch ;
- sécurité, FinOps, sauvegarde et restauration ;
- Terraform, Helm et GitLab CI OIDC ;
- tests industriels et réception.

### 4.2 Hors périmètre initial

- Bedrock managed Agents ;
- Bedrock Knowledge Bases ;
- OpenSearch Serverless ;
- engagement de production réel ;
- organisation ou gouvernance client inventée ;
- multi-région actif/actif tant qu’aucune exigence ne le justifie ;
- intégration à un système de paiement ou de réservation externe ;
- migration irréversible de la V1 sans stratégie de rollback.

## 5. Exigences d’architecture initiales

| ID | Exigence |
|---|---|
| V2-ARCH-001 | API Gateway demeure le front-door web tant qu’un ADR approuvé n’en décide autrement. |
| V2-ARCH-002 | Le navigateur ne produit jamais l’identité de confiance et ne connaît pas l’URL technique AgentCore Runtime. |
| V2-ARCH-003 | AgentCore Runtime est utilisé uniquement comme runtime d’exécution d’agents custom. |
| V2-ARCH-004 | Les frameworks d’agents sont encapsulés derrière un adapter optionnel. |
| V2-ARCH-005 | Le backend applicatif cible FastAPI sur EKS. |
| V2-ARCH-006 | Le RAG est applicatif et repose sur S3 Vectors, DynamoDB et S3. |
| V2-ARCH-007 | Les modèles sont invoqués via Bedrock Converse API. |
| V2-ARCH-008 | Les tools sont exposés et gouvernés via AgentCore Gateway MCP. |
| V2-ARCH-009 | Terraform et Helm sont les mécanismes déclaratifs de référence. |
| V2-ARCH-010 | GitLab CI avec OIDC AWS est la cible de CI/CD V2. |

## 6. Exigences non fonctionnelles initiales

Ces valeurs sont des exigences à instruire dans le HLD et les LLD. Elles ne constituent pas encore des engagements de production.

### Sécurité

- isolation stricte par utilisateur ou tenant ;
- IAM least privilege ;
- chiffrement en transit et au repos ;
- secrets dans Secrets Manager ;
- défense contre prompt injection, data poisoning et exfiltration par tool ;
- logs sans secrets, tokens, prompts ou données sensibles en clair ;
- traçabilité des décisions agentiques et appels de tools.

### Disponibilité et résilience

- workloads EKS répartis sur plusieurs zones de disponibilité ;
- health checks, readiness et graceful shutdown ;
- reprise idempotente de l’ingestion ;
- dégradation contrôlée en cas d’indisponibilité RAG, Memory, Gateway ou modèle ;
- sauvegarde et restauration testées.

### Performance

- budgets de timeout explicites par composant ;
- mesure du time-to-first-token et de la durée totale ;
- limitation des tours agentiques et des appels de tools ;
- objectifs de latence définis par parcours dans le HLD.

### FinOps

- mesure des tokens, appels modèle, embeddings, stockage et calcul ;
- quotas et limites configurables ;
- dashboards de coût estimé par parcours ou environnement ;
- arbitrages modèle/qualité/coût documentés.

### Exploitabilité

- traces distribuées OpenTelemetry ;
- logs et métriques CloudWatch ;
- SLO et error budgets ;
- runbooks d’incident, rollback, restauration et réindexation.

## 7. Livrables obligatoires

- charte et roadmap V2 ;
- architecture As-Is V1 ;
- architecture To-Be V2 ;
- analyse des écarts ;
- ADR structurants ;
- HLD V2 approuvé ;
- LLD plateforme, RAG, agents, MCP, sécurité, observabilité et CI/CD ;
- modèle de données ;
- contrats OpenAPI et MCP ;
- threat model ;
- stratégie de tests ;
- matrice de traçabilité ;
- stratégie de migration et rollback ;
- runbooks ;
- dossier de réception et preuves.

## 8. Definition of Done V2

La V2 est clôturable lorsque :

- le HLD et les LLD sont en statut `As-Built` ;
- les ADR structurants sont approuvés ;
- l’environnement est reproductible par Terraform et Helm ;
- les agents custom, le RAG et les tools respectent leurs contrats ;
- les tests de qualité, sécurité, isolation, charge, résilience et restauration sont passés ;
- les évaluations RAG utilisent un dataset versionné ;
- la traçabilité bout en bout est démontrée ;
- les coûts et performances sont mesurés ;
- les preuves sont archivées ;
- les runbooks et procédures de rollback sont vérifiés.

## 9. Risques initiaux

| Risque | Effet potentiel | Réponse attendue |
|---|---|---|
| Complexité excessive du multi-agent | Latence, coût et faible testabilité | Commencer par un orchestrateur minimal et justifier chaque agent spécialisé. |
| Mauvaise qualité du retrieval | Réponses non fondées | Dataset d’évaluation, métriques de retrieval et citations obligatoires. |
| Prompt injection documentaire | Détournement des agents ou tools | Contenu RAG traité comme donnée non fiable et filtrage des actions. |
| Couplage au framework agentique | Migration difficile | Adapter obligatoire et contrats applicatifs indépendants. |
| Ingestion non idempotente | Doublons et index incohérent | Identifiants déterministes, état DynamoDB et reprise contrôlée. |
| Dérive des coûts Bedrock/EKS | Budget imprévisible | Quotas, télémétrie de coût et tests de charge. |
| Migration CI/CD prématurée | Perte des gates V1 | Parité démontrée avant retrait des workflows existants. |

## 10. Gate de sortie du cadrage

La Gate `V2-G0` est franchie lorsque cette charte, la roadmap, le HLD initial, le catalogue LLD et le backlog ADR sont disponibles et revus. Le franchissement de cette gate n’autorise pas encore l’implémentation des composants structurants ; il autorise l’instruction détaillée des ADR et du HLD.
