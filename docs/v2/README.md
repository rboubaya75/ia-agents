# Référentiel documentaire — Secure AgentCore V2

- **Branche cible :** `migration/secure-agentcore-v2`
- **Baseline :** Secure AgentCore V1, commit `20d4b12cb4666fe66eefbdf6b1605fe8f74daa03`
- **Statut :** initialisation documentaire
- **Langue de référence :** français

## 1. Objet

Ce répertoire constitue le point d’entrée documentaire de la V2. Il organise les exigences, décisions, vues d’architecture, conceptions détaillées, plans de transition et preuves de réception avant toute implémentation structurante.

La V1 est considérée close par décision projet. Elle reste la baseline fonctionnelle et sécuritaire à préserver tant qu’un ADR V2 n’a pas explicitement remplacé une décision existante.

## 2. Règle de branches

- `migration/secure-agentcore-v1` reste la baseline V1 et ne reçoit aucun document V2 ;
- `migration/secure-agentcore-v2` est la branche d’intégration V2 ;
- chaque lot V2 est développé sur une branche de travail créée depuis `migration/secure-agentcore-v2` ;
- toute pull request V2 cible `migration/secure-agentcore-v2` ;
- aucune PR V2 ne doit cibler la branche V1.

## 3. Principes non négociables

La V2 respecte les choix techniques suivants :

- Python 3.12 et FastAPI pour les services applicatifs ;
- agents custom sous `/agents` ;
- Strands ou LangGraph uniquement derrière un adapter optionnel ;
- Bedrock AgentCore Runtime comme runtime d’exécution uniquement ;
- Bedrock Converse API pour l’accès aux modèles ;
- embeddings Bedrock configurables ;
- RAG applicatif avec S3 Vectors, DynamoDB et S3 ;
- Cognito pour l’authentification ;
- React, TypeScript et Vite ;
- frontend sur S3 privé, CloudFront et WAF ;
- backend applicatif sur EKS ;
- Terraform et Helm ;
- GitLab CI avec OIDC AWS comme cible V2 ;
- OpenTelemetry et CloudWatch ;
- Secrets Manager pour les secrets.

Sont exclus :

- Bedrock managed Agents ;
- Bedrock Knowledge Bases ;
- OpenSearch Serverless.

## 4. Documents de cadrage

| Document | Finalité | Statut initial |
|---|---|---|
| [`V2-CHARTER-FR.md`](V2-CHARTER-FR.md) | Vision, périmètre, exigences, principes et Definition of Done | Draft |
| [`V2-ROADMAP-FR.md`](V2-ROADMAP-FR.md) | Phases, dépendances, gates HLD/LLD et livrables | Draft |
| [`../hld/HLD-Secure-AgentCore-V2-FR.md`](../hld/HLD-Secure-AgentCore-V2-FR.md) | Architecture cible haut niveau | Draft 0.1 |
| [`../lld/LLD-V2-INDEX-FR.md`](../lld/LLD-V2-INDEX-FR.md) | Catalogue canonique des dix LLD et de leurs dépendances ADR | Draft |
| [`../adr/V2-ADR-BACKLOG-FR.md`](../adr/V2-ADR-BACKLOG-FR.md) | Backlog des décisions structurantes à instruire | Draft |
| [`../adr/V2-ADR-002-fastapi-agentcore-responsibilities.md`](../adr/V2-ADR-002-fastapi-agentcore-responsibilities.md) | Décision : répartition FastAPI / AgentCore Runtime (option retenue, principes, conséquences) | Draft 0.4 |
| [`../hld/capability-allocation-matrix.md`](../hld/capability-allocation-matrix.md) | **Capability Allocation Matrix (CAM)** — attribution des capacités par domaine, portée par V2-ADR-002 | Draft 0.1 |
| [`../hld/runtime-contract.md`](../hld/runtime-contract.md) | Contrat interne FastAPI → AgentCore Runtime dérivé de la CAM | Draft 0.1 |

> V2-ADR-002 est le seul ADR listé individuellement ci-dessus : c'est la décision qui institue la
> CAM comme référentiel d'autorité. La CAM et le contrat qui en découlent sont désormais des
> artefacts de conception (HLD) séparés, pour que l'ADR reste centré sur le *pourquoi* et non sur
> le détail d'implémentation. Les autres ADR déjà instruits (`V2-ADR-001`, `V2-ADR-006`, statut
> `Proposed`) restent référencés dans le backlog ci-dessus jusqu'à leur passage en `Accepted`.

## 5. Cycle de gouvernance

La hiérarchie de traçabilité V2 structure le corpus documentaire du cadrage jusqu'aux preuves
de réception. La **Capability Allocation Matrix** (CAM, portée par V2-ADR-002) occupe le niveau
intermédiaire entre les principes d'architecture et les décisions d'implémentation. Toute capacité
doit être traçable jusqu'à une exigence métier et jusqu'à un test de réception.

```text
Business Requirements
        │
        ▼
Architecture Principles          (V2-CHARTER-FR.md — section 5)
        │
        ▼
Capability Model                 (domaines fonctionnels)
        │
        ▼
Capability Allocation Matrix     (../hld/capability-allocation-matrix.md, décidée par V2-ADR-002)
        │
        ├──► Architecture Decision Records   (V2-ADR-001 à V2-ADR-018)
        │
        ├──► High Level Design               (HLD-Secure-AgentCore-V2-FR.md)
        │
        ├──► Low Level Design par domaine    (V2-LLD-001 à V2-LLD-010)
        │
        ├──► Implementation
        │
        ├──► Industrial Test Suite
        │
        └──► Acceptance Evidence
```

Règles découlant de la CAM :

- chaque capacité a un unique propriétaire (Single Capability Ownership) ;
- aucune capacité n'est implémentée par deux composants (No Capability Duplication) ;
- toutes les interactions passent par des contrats versionnés (Explicit Contracts) ;
- les capacités sont décrites indépendamment de leur technologie (Technology Independence) ;
- chaque capacité est reliée aux ADR, HLD, LLD, tests et exigences (Traceability).

Aucun composant structurant ne doit être implémenté avant validation du HLD et du LLD qui le
gouvernent. Une divergence significative entre conception et implémentation exige un ADR nouveau
ou amendé. Une capacité non attribuée dans la CAM est un écart de gouvernance bloquant.

## 6. Statuts documentaires

- `Draft` : document en construction, non utilisable comme autorisation d’implémenter ;
- `In Review` : contenu complet soumis à revue ;
- `Approved` : gate franchie, implémentation autorisée dans le périmètre défini ;
- `As-Built` : document aligné sur l’implémentation réceptionnée ;
- `Superseded` : remplacé par une décision ou une version ultérieure.

## 7. Gates documentaires

### Gate V2-G0 — Baseline et cadrage

- baseline V1 identifiée ;
- périmètre V2 défini ;
- contraintes et exclusions enregistrées ;
- roadmap et backlog ADR disponibles ;
- catalogue canonique des dix LLD disponible.

### Gate V2-G1 — Architecture HLD

- ADR structurants instruits ;
- HLD complet et revu ;
- flux, zones de confiance, données, résilience et exploitation couverts ;
- analyse As-Is / To-Be et trajectoire de transition documentées.

### Gate V2-G2 — Conception LLD

Les dix LLD canoniques sont :

1. `V2-LLD-001` — plateforme AWS, réseau, EKS et FastAPI ;
2. `V2-LLD-002` — RAG et ingestion documentaire ;
3. `V2-LLD-003` — agents et orchestration ;
4. `V2-LLD-004` — AgentCore Gateway MCP et tools ;
5. `V2-LLD-005` — identité, sécurité et conformité ;
6. `V2-LLD-006` — données, mémoire, rétention et restauration ;
7. `V2-LLD-007` — observabilité, SLO et FinOps ;
8. `V2-LLD-008` — CI/CD, Terraform, Helm et promotion ;
9. `V2-LLD-009` — stratégie de tests et preuves ;
10. `V2-LLD-010` — frontend React V2.

La gate est franchie lorsque les LLD nécessaires à la tranche sont `Approved`, que leurs contrats et exigences de test sont traçables et que les risques résiduels sont acceptés ou traités.

## 8. Discipline de livraison

Chaque phase doit produire :

- un plan avant modification ;
- la liste des fichiers modifiés ;
- les validations exécutées ;
- les échecs ou limites constatés ;
- une demande de validation avant passage à la phase suivante.
