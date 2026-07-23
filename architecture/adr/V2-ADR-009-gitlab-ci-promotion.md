# V2-ADR-009 — GitLab CI et promotion

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-007, V2-ADR-008, V2-ADR-010

## Contexte

La V1 dispose de 14 workflows GitHub Actions matures : secret scan (Gitleaks), audits de
dépendances (`pip-audit`, `npm audit`), et surtout un mécanisme de **plan-guard Terraform**
(`scripts/terraform_plan_guard.py`, indépendant de la plateforme CI) qui garantit qu'un `terraform
apply` s'exécute exclusivement sur le plan exact qui a été revu, via vérification de digest
SHA-256 entre les jobs plan et apply. Ce mécanisme est directement réutilisable côté GitLab CI.

À l'inverse, trois éléments sont absents aujourd'hui et doivent être construits :
1. **OIDC AWS** : le provider et le rôle IAM assumés par les workflows GitHub Actions ne sont
   provisionnés nulle part dans ce dépôt (géré hors-repo) ;
2. **Promotion d'artefact** : un seul environnement Terraform existe (`test`), et chaque
   déploiement reconstruit l'image conteneur dans le même run — aucun mécanisme de retag/
   promotion d'une image déjà construite et testée n'existe ;
3. **SBOM, scan d'image, signature** : totalement absents (`--provenance=false` est même
   explicitement passé au build Docker actuel).

Le HLD (§15-16) impose déjà que les workflows GitHub Actions V1 ne soient retirés qu'après
démonstration de parité fonctionnelle et sécuritaire — cet ADR formalise cette coexistence.

## Options

### Option A — Bascule immédiate vers GitLab CI, retrait de GitHub Actions

**Rejet proposé :** viole le principe de coexistence déjà acté au HLD et casserait la continuité
opérationnelle de la V1, encore active.

### Option B — GitLab CI en parallèle, retrait après démonstration de parité

Les mêmes gates (secret scan, audits, tests, plan-guard Terraform) sont exécutées sur les deux CI
pendant une période de coexistence ; GitHub Actions n'est retiré qu'après comparaison des preuves.

### Option C — Rester sur GitHub Actions indéfiniment

**Rejet proposé :** contredit directement la charte, qui fixe GitLab CI avec OIDC AWS comme cible
V2 non négociable.

## Décision proposée

Retenir **l'option B**.

## Pipeline GitLab CI

```text
lint / typecheck
  -> secret-scan (Gitleaks, reconduit tel quel)
  -> dependency-scan (pip-audit, npm audit, reconduits tels quels)
  -> unit-tests
  -> build-image
       -> SBOM (Syft)
       -> scan de vulnérabilités (Trivy, bloquant sur CVE critique)
       -> signature (cosign, keyless via OIDC GitLab)
  -> terraform-plan (terraform_plan_guard.py analyze + record, réutilisé tel quel)
  -> gate manuelle
  -> terraform-apply (terraform_plan_guard.py verify avant apply, réutilisé tel quel)
  -> tests industriels / intégration
  -> publication des preuves
```

## OIDC AWS

Contrairement à la V1, le provider OIDC et le rôle IAM assumé par GitLab CI sont **provisionnés en
Terraform dans ce dépôt** (nouveau module dédié), avec une politique de confiance restreinte au
projet GitLab, à la branche et à l'environnement cible — remplaçant le secret statique
`AWS_ROLE_ARN` GitHub par les `id_tokens:` natifs de GitLab CI. Aucune clé AWS statique, principe
déjà validé par `docs/adr/ADR-005-terraform-github-actions-deployment.md` en V1 et reconduit ici.

## Promotion d'artefact

Une image est construite et scannée **une seule fois** (stage `build-image`), poussée vers ECR
avec un tag immuable dérivé du digest. La promotion vers un environnement suivant retague ce même
digest — elle ne redéclenche jamais un build. Ceci comble le vide identifié en V1, où
l'image est reconstruite dans chaque run et dans le même environnement.

## SBOM, scan et signature

Chantier neuf, absent à 100 % aujourd'hui :

- **SBOM** via Syft (format CycloneDX ou SPDX), généré depuis l'image construite ;
- **scan de vulnérabilités** via Trivy, bloquant sur toute CVE critique (cohérent avec le principe
  fail-closed déjà établi par la suite de tests industriels V1) ;
- **signature** via cosign en mode keyless (identité OIDC GitLab), vérifiée avant tout déploiement
  — un déploiement sans signature valide est refusé.

Outils choisis pour leur statut de standards ouverts, sans dépendance à un service tiers payant.

## Secrets

Aucune clé AWS statique (OIDC uniquement). Les autres secrets (tokens de test, identifiants
Secrets Manager référencés par les scripts applicatifs) utilisent les variables CI/CD masquées de
GitLab, avec permissions de job minimales par défaut — reconduction du principe déjà appliqué aux
`permissions:` GitHub Actions (`contents: read` par défaut, élévation explicite par job).

## Preuves et évidences

Le format JSON déjà établi par `scripts/run_industrial_test_suite.py`
(`schemaVersion`, `gitSha`, `environment`, `suite`, `cases[]`) est conservé sans modification,
publié comme `artifacts:` GitLab CI avec `expire_in` (durées alignées sur les rétentions actuelles :
7/14/90 jours selon le type de preuve), et résumé dans la description de merge request en
complément de l'artefact durable — équivalent du double mécanisme artefact + `$GITHUB_STEP_
SUMMARY` déjà en place.

## Justification des dépendances

- **V2-ADR-007** : le pipeline déploie l'infrastructure réseau/ECS et son rôle OIDC ;
- **V2-ADR-008** : le format des preuves CI reprend les conventions de corrélation/redaction
  décidées pour l'observabilité ;
- **V2-ADR-010** : la gate `terraform-apply` réutilise le plan-guard qui protège les ressources de
  sauvegarde (PITR, versioning) dont la politique est fixée par ce dernier.

## Parité et retrait de GitHub Actions

Critère de sortie de la coexistence : les mêmes gates (secret scan, audits de dépendances, tests
unitaires et industriels, plan-guard Terraform) produisent des résultats équivalents sur les deux
CI pour un même commit, pendant une période définie en `V2-LLD-008`. GitHub Actions n'est retiré
qu'une fois cette parité démontrée et documentée, jamais par défaut.

## Conséquences

- nouveau module Terraform pour le provider OIDC et le rôle IAM GitLab ;
- nouveaux fichiers `.gitlab-ci.yml` et templates associés ;
- double maintenance CI temporaire pendant la coexistence (dette technique assumée, bornée par le
  critère de sortie ci-dessus) ;
- `scripts/terraform_plan_guard.py` reste inchangé (déjà indépendant de la plateforme CI, stdlib
  Python uniquement) — seule son intégration (artifacts inter-jobs) change de syntaxe.

## Preuves attendues

- le pipeline GitLab CI reproduit les gates GitHub Actions existantes avec un résultat équivalent
  sur un même commit ;
- un `terraform apply` s'exécute exclusivement sur le plan vérifié par digest, jamais sur un
  replan silencieux (même garantie que `terraform_plan_guard.py verify` en V1) ;
- toute image conteneur déployée est accompagnée d'un SBOM et d'une signature valide, vérifiée
  avant déploiement ;
- aucune clé AWS statique n'apparaît dans les variables GitLab CI ;
- une promotion vers un environnement suivant ne déclenche aucun rebuild d'image (même digest).

## Références AWS

- AWS IAM OIDC Identity Provider ;
- Amazon ECR ;
- GitLab CI/CD avec `id_tokens` OIDC.
