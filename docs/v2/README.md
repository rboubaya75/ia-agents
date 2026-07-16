# Référentiel documentaire — Secure AgentCore V2

- **Branche :** `migration/secure-agentcore-v2`
- **Baseline :** Secure AgentCore V1, commit `20d4b12cb4666fe66eefbdf6b1605fe8f74daa03`
- **Statut :** initialisation documentaire
- **Langue de référence :** français

## 1. Objet

Ce répertoire constitue le point d’entrée documentaire de la V2. Il organise les exigences, décisions, vues d’architecture, conceptions détaillées, plans de transition et preuves de réception avant toute implémentation structurante.

La V1 est considérée close par décision projet. Elle reste la baseline fonctionnelle et sécuritaire à préserver tant qu’un ADR V2 n’a pas explicitement remplacé une décision existante.

## 2. Principes non négociables

- Python 3.12 et FastAPI pour les services applicatifs ;
- agents custom sous `/agents` ;
- Strands ou LangGraph uniquement derrière un adapter optionnel ;
- Bedrock AgentCore Runtime comme runtime d’exécution uniquement ;
- Bedrock Converse API pour les modèles ;
- embeddings Bedrock configurables ;
- RAG applicatif avec S3 Vectors, DynamoDB et S3 ;
- Cognito, React, TypeScript et Vite ;
- frontend sur S3 privé, CloudFront et WAF ;
- backend applicatif sur EKS ;
- Terraform, Helm et GitLab CI avec OIDC AWS ;
- OpenTelemetry, CloudWatch et Secrets Manager.

Sont exclus : Bedrock managed Agents, Bedrock Knowledge Bases et OpenSearch Serverless.

## 3. Documents de cadrage

| Document | Finalité | Statut initial |
|---|---|---|
| [`V2-CHARTER-FR.md`](V2-CHARTER-FR.md) | Vision, périmètre, exigences et Definition of Done | Draft |
| [`V2-ROADMAP-FR.md`](V2-ROADMAP-FR.md) | Phases, dépendances et gates | Draft |
| [`../hld/HLD-Secure-AgentCore-V2-FR.md`](../hld/HLD-Secure-AgentCore-V2-FR.md) | Architecture cible haut niveau | Draft 0.1 |
| [`../lld/LLD-V2-INDEX-FR.md`](../lld/LLD-V2-INDEX-FR.md) | Catalogue canonique des dix LLD | Draft |
| [`../adr/V2-ADR-BACKLOG-FR.md`](../adr/V2-ADR-BACKLOG-FR.md) | Backlog canonique des ADR | Draft |

## 4. Cycle de gouvernance

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

Aucun composant structurant ne doit être implémenté avant validation du HLD et du LLD qui le gouvernent.

## 5. Statuts documentaires

- `Draft` : en construction ;
- `In Review` : soumis à revue ;
- `Approved` : gate franchie ;
- `As-Built` : aligné sur l’implémentation réceptionnée ;
- `Superseded` : remplacé.

## 6. Gates

### V2-G0 — Baseline et cadrage

- baseline V1 identifiée ;
- périmètre et exclusions définis ;
- roadmap, HLD initial, backlog ADR et catalogue LLD disponibles.

### V2-G1 — Architecture HLD

- ADR structurants instruits ;
- HLD complet et revu ;
- flux, zones de confiance, données, résilience, coûts et transition couverts.

### V2-G2 — Conception LLD

Les dix LLD canoniques doivent être traités selon la tranche :

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

La gate exige des contrats techniques et critères de test traçables, ainsi que des risques résiduels acceptés ou traités.

## 7. Discipline de livraison

Chaque phase doit produire un plan, la liste des fichiers modifiés, les validations exécutées, les échecs ou limites constatés et une demande de validation avant la phase suivante.
