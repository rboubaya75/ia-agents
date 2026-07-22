# V2-ADR-008 — Observabilité et contexte distribué

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-002, V2-ADR-006, V2-ADR-007

## Contexte

La CAM (Domaine 9 — Observability, déjà décidée par `V2-ADR-002`) attribue les métriques et le
tracing distribué (`traceId`, `spanId`, W3C Trace Context) à OpenTelemetry, les Business
Correlation IDs (`operationId`, `requestId`) à FastAPI, et les logs structurés/audit/dashboards/
alertes à CloudWatch. Cet ADR ne redécide pas cette répartition, il décide du mécanisme
d'instrumentation et des garanties opérationnelles (redaction, échantillonnage, rétention, SLO).

L'observabilité V2 (OpenTelemetry, traceId/spanId) est **entièrement à créer** : la V1 n'a aucune
dépendance OTel, seulement du logging JSON structuré avec identifiants hashés
(`safe_hash()`, SHA-256 tronqué) et une corrélation `requestId`/`operationId` déjà propagée bout
en bout. Point notable : le rôle IAM AgentCore Runtime porte déjà les permissions X-Ray
(`xray:PutTraceSegments`, `PutTelemetryRecords`, `GetSamplingRules`, `GetSamplingTargets`,
`infra/modules/agentcore_runtime/iam.tf`) — provisionnées par anticipation mais jamais exploitées.

## Options

### Option A — AWS X-Ray natif (SDK X-Ray, pas OpenTelemetry)

**Rejet proposé :** la charte impose explicitement OpenTelemetry comme choix technique non
négociable ; X-Ray direct ne le respecte pas, même si les permissions IAM existent déjà.

### Option B — OpenTelemetry avec collector auto-hébergé et backend tiers

Collector OTel sur EKS, export vers Jaeger/Tempo auto-géré.

**Rejet proposé :** ajoute un service tiers à opérer et un coût d'exploitation supplémentaire non
justifiés, alors qu'un export natif vers les services AWS déjà provisionnés est disponible.

### Option C — AWS Distro for OpenTelemetry (ADOT)

SDK OpenTelemetry standard, collector ADOT sur EKS, export des traces vers X-Ray (réutilisant les
permissions IAM déjà en place) et des métriques/logs vers CloudWatch.

## Décision proposée

Retenir **l'option C**. ADOT est un collector conforme au standard OpenTelemetry qui exporte vers
des backends AWS managés : il satisfait l'exigence de la charte (SDK OTel standard) sans introduire
de nouveau service à opérer, et réutilise directement les permissions X-Ray déjà provisionnées et
inutilisées en V1.

```text
FastAPI (SDK OTel) --traceparent (W3C)--> AgentCore Runtime --traceparent--> Tools MCP
     │                                          │                                │
     └──────────────────── collector ADOT (EKS) ─────────────────────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                       ▼
                     AWS X-Ray            Amazon CloudWatch (métriques, logs)
```

## Propagation et corrélation

- propagation W3C Trace Context (`traceparent`) de FastAPI jusqu'aux tools MCP ;
- AgentCore Runtime étant un service managé, la propagation native du header `traceparent` à
  travers son SDK est à vérifier en LLD-007 ; si elle n'est pas supportée nativement, la
  corrélation de repli s'appuie sur `operationId`/`requestId` (déjà portés par
  `operationContext` du contrat interne, `architecture/hld/runtime-contract.md`) recoupés dans
  CloudWatch Logs Insights entre les segments de trace disponibles ;
- les Business Correlation IDs (`operationId`, `requestId`) restent distincts du tracing
  technique (`traceId`, `spanId`), conformément à la CAM — ils ne se substituent pas l'un à
  l'autre, ils se complètent.

## Redaction

Le mécanisme V1 (`safe_hash()` — SHA-256 tronqué à 12 caractères pour les identifiants sensibles)
est étendu à tous les identifiants de corrélation : `traceId`, `spanId`, `operationId`,
`requestId`, `sessionId`, `tenantId`/`actorId`. Aucun JWT, prompt brut, réponse brute ou secret
n'apparaît en clair dans les traces, métriques ou logs — reconduction stricte de l'interdiction
déjà en vigueur en V1 (`docs/hld/HLD-WildRydes-Agentic-AI-FR.md` §8).

## Échantillonnage

Échantillonnage parent-based avec sur-échantillonnage systématique des erreurs (100 % des traces
en erreur conservées, taux réduit configurable pour les succès). Le taux précis pour les succès
est fixé en LLD-007 selon le volume observé, pas dans cet ADR.

## Rétention

30 jours par défaut pour les CloudWatch Log Groups, reconduisant la valeur déjà en place et
homogène en V1 (`agent_api_facade`, `trip_tools`, API Gateway access logs — tous à 30 jours) ; les
traces suivent la rétention X-Ray par défaut sauf export ciblé pour investigation. Une révision à
la hausse pour des besoins de conformité est possible mais doit être justifiée en LLD-007, pas
appliquée par défaut (impact coût direct).

## SLO et error budgets

Le mécanisme est fixé ici, pas les seuils chiffrés (la charte ne fixe aucun budget numérique
aujourd'hui, délégué à `V2-LLD-007`) : métriques OTel exportées vers CloudWatch alimentent des
dashboards et alarmes par chemin critique (latence P95 conversation, latence P95 retrieval, taux
d'erreur des appels tool). Les métriques minimales attendues (reprises du HLD §13) : time-to-
first-token, latence totale et par composant, tokens entrée/sortie, coût estimé, embeddings
générés, qualité et latence du retrieval, saturation EKS, throttling, erreurs/refus/dégradations,
volume et coût de stockage.

## Conséquences

- déploiement du collector ADOT sur EKS (Helm chart ou addon EKS, impact Terraform/Helm) ;
- dashboards et alarmes CloudWatch définis en Terraform ou Helm, pas manuellement ;
- les permissions IAM X-Ray déjà provisionnées en V1 sont enfin exploitées, aucun changement IAM
  majeur nécessaire au-delà de l'extension aux nouveaux workloads EKS (Pod Identity, `V2-ADR-007`) ;
- le catalogue d'événements V1 (`facade_invocation`, `agent_invocation`, etc.) est étendu, pas
  remplacé, pour couvrir FastAPI, retrieval et l'ensemble de la chaîne V2.

## Preuves attendues

- un `traceId` W3C est visible bout en bout dans X-Ray pour un parcours complet (FastAPI →
  Runtime → tool), ou la corrélation par `operationId` est démontrée si la propagation directe
  n'est pas supportée par Runtime ;
- aucun identifiant brut, JWT, prompt ou secret n'apparaît en clair dans les traces, métriques ou
  logs (test de non-régression) ;
- une alerte se déclenche lors d'un dépassement de SLO simulé ;
- les dashboards affichent les métriques minimales listées au HLD §13.

## Références AWS

- AWS Distro for OpenTelemetry (ADOT) ;
- AWS X-Ray ;
- Amazon CloudWatch (Logs, Metrics, Dashboards, Alarms).
