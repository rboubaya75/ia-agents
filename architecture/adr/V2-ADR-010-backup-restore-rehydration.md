# V2-ADR-010 — Sauvegarde, restauration et réhydratation

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-003, V2-ADR-004, V2-ADR-006, V2-ADR-007

## Contexte

La V1 a déjà activé le versioning S3 (chiffrement AES256) et le PITR DynamoDB (`pitr_enabled =
true` par défaut dans `infra/modules/dynamodb_trips`). Le HLD (section 14) laisse explicitement
ouverts le RTO/RPO et la stratégie de réhydratation S3 Vectors — c'est l'objet de cet ADR. La
suppression coordonnée entre S3, S3 Vectors, DynamoDB et Memory est déjà exigée par `V2-ADR-006` ;
la restauration en est le problème miroir et doit respecter la même cohérence.

## Options pour la réhydratation S3 Vectors

### Option A — Sauvegarde native de l'index vectoriel

Export/snapshot périodique de l'index S3 Vectors lui-même, restauré directement en cas de sinistre.

**Rejet proposé :** aucune capacité d'export/snapshot native n'est confirmée pour S3 Vectors dans
le périmètre de ce projet ; s'appuyer dessus introduit une dépendance technique non vérifiée. À
revérifier en LLD-006 si l'API évolue ; non retenu comme décision d'architecture tant que non
confirmé.

### Option B — Reconstruction applicative depuis la source

L'index S3 Vectors est traité comme un état dérivé, jamais sauvegardé directement. La source de
vérité durable est S3 (documents) + DynamoDB (métadonnées). Un sinistre sur S3 Vectors se répare
par ré-ingestion complète via le pipeline idempotent (`V2-ADR-004`).

## Décision proposée

Retenir **l'option B**. Cette décision découle naturellement du principe déjà acté que le contenu
documentaire est une donnée non fiable et régénérable (contrairement aux données métier
transactionnelles de la table `Trips`, qui exigent une vraie garantie de sauvegarde/restauration).

## RTO / RPO par catégorie de donnée

| Donnée | RPO | RTO | Mécanisme |
|---|---|---|---|
| DynamoDB (`Trips`, `documents`, ledger d'idempotence) | quasi nul (PITR, jusqu'à la seconde, 35 jours) | quelques minutes | restauration PITR vers une table neuve, bascule Terraform |
| S3 (documents sources, frontend) | nul (chaque écriture versionnée) | immédiat | version précédente déjà accessible ; en cas de perte du bucket entier, recréation + restauration depuis réplication ou reconstruction depuis la CI pour le frontend |
| S3 Vectors (index) | temps écoulé depuis le dernier batch d'ingestion réussi | borné par le volume du corpus à réindexer (cible initiale : sous 4 heures pour le corpus de démonstration, à réviser en LLD-006 à l'échelle) | ré-ingestion complète via `V2-ADR-004` |
| AgentCore Memory | non applicable par conception | non applicable par conception | dégradation déjà actée (« poursuite sans mémoire durable » si indisponible, `capability-allocation-matrix.md`) |
| Configuration Terraform | nulle (source = dépôt git) | immédiat (redéploiement depuis git) | backend d'état versionné séparément |

## Cohérence de restauration

Une restauration ne réintroduit jamais S3 Vectors sans que les objets S3 et les métadonnées
DynamoDB correspondants soient d'abord restaurés à un point mutuellement cohérent — sinon des
vecteurs orphelins pointeraient vers des documents inexistants. La séquence de restauration est :
1) restaurer DynamoDB (PITR) à l'horodatage cible ; 2) confirmer la cohérence avec les versions S3
disponibles à ce même horodatage ; 3) déclencher une ré-ingestion ciblée sur les documents dont
l'état DynamoDB restauré indique `indexed` mais dont les vecteurs sont absents.

## Tests de restauration

Un exercice de restauration (DR drill) est exécuté à fréquence trimestrielle ou avant chaque
release majeure : restauration PITR vers une table de test, ré-ingestion d'un échantillon,
vérification des comptages et des métriques de qualité retrieval (`V2-ADR-003`). Les preuves sont
publiées selon le même format que `scripts/run_industrial_test_suite.py` (JSON, SHA Git,
horodatage, durée, statut).

## Conséquences

- `scripts/terraform_plan_guard.py` doit être étendu pour bloquer tout plan qui désactiverait le
  PITR DynamoDB, le versioning S3, ou détruirait ces ressources sans confirmation explicite ;
- l'estimation de RTO pour S3 Vectors dépend directement du débit du pipeline d'ingestion
  (`V2-ADR-004`) et de la capacité EKS disponible (`V2-ADR-007`) — un sinistre majeur doit pouvoir
  mobiliser temporairement plus de workers que le régime nominal ;
- aucune sauvegarde dédiée n'est requise pour AgentCore Memory, cohérent avec sa nature de donnée
  non durable déjà actée.

## Preuves attendues

- restauration PITR vérifiée : comptage d'items identique à un instantané de référence connu ;
- ré-ingestion complète depuis S3+DynamoDB restaurés reproduit des métriques de qualité retrieval
  équivalentes à l'état pré-sinistre (à ±marge définie en LLD-006) ;
- `terraform_plan_guard.py` bloque un plan désactivant PITR ou versioning, ou détruisant la table
  `Trips`/`documents` ou un bucket S3 versionné sans confirmation explicite ;
- RTO mesuré lors d'un exercice de restauration documenté et comparé à la cible du tableau
  ci-dessus ;
- aucun vecteur orphelin ne subsiste après une restauration partielle.

## Références AWS

- Amazon DynamoDB Point-in-Time Recovery ;
- Amazon S3 Versioning ;
- Amazon S3 Vectors (reconstruction applicative, pas de sauvegarde native retenue) ;
- Amazon Bedrock (ré-embedding lors de la ré-ingestion).
