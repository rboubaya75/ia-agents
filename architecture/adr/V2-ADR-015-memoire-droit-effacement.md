# V2-ADR-015 — Politique de mémoire et droit à l'effacement

- **Statut :** Draft (propositions — en attente de revue et de validation)
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-006` (isolation et suppression coordonnée), `V2-ADR-010` (PITR,
  versioning et restauration), `V2-ADR-014` (une demande d'effacement est une action mutante),
  `V2-ADR-002` (Memory est une donnée non fiable), `V2-ADR-005` (usage de Memory par les agents)
- **Préconditions bloquantes :** existence et sémantique des API de suppression et d'expiration
  d'AgentCore Memory — leur absence fait basculer sur l'option C ; indépendance du journal d'audit
  servant au rejeu vis-à-vis du périmètre de restauration — son absence n'a pas de repli (voir
  « Préconditions »).
- **Documents impactés :** `V2-ADR-006`, `V2-ADR-010` ; `capability-allocation-matrix.md`
  Domaine 6 ; `V2-LLD-006` §2, §6.2, §8.3, §8.4, §9.2, §10, §13.3, §13.4, §16 ; `V2-LLD-003` §2.5 ;
  `LLD-V2-INDEX-FR.md` (portée `V2-LLD-005`) — voir « Écarts à corriger dans le corpus ».

## Contexte

`V2-LLD-006` fixe la mécanique de bas niveau de la suppression et laisse explicitement quatre
questions ouvertes pour cet ADR (§1.3, §8.1, §8.4, §9) :

> « Portée exacte du droit à l'effacement, délais légaux applicables, cycle de vie Memory »

et, sur la séquence d'effacement utilisateur :

> « Ce que le LLD-006 ne préempte pas : délai maximum entre requête et complétion, communication
> utilisateur, portée exacte (Memory ? conversations ? logs redacted ?), obligations légales. »

Le corpus dispose donc d'une mécanique — supprimer les documents d'un utilisateur, écrire une trace
dans `users` — sans politique qui dise ce que cette mécanique garantit. Cet ADR tranche trois
questions :

1. **ce qu'un effacement garantit et à quelle échéance**, face aux mécanismes de durabilité que le
   corpus impose par ailleurs ;
2. **le statut de la mémoire agentique** — donnée volatile hors périmètre, ou donnée personnelle
   dans le périmètre ;
3. **le cycle de vie de la mémoire**, que ni `V2-LLD-006` ni `V2-LLD-003` ne fixent.

## Exigences

| Référence | Exigence |
|---|---|
| `V2-ADR-006` | une suppression coordonne S3, vecteurs, métadonnées DynamoDB, Memory, index et caches |
| `V2-ADR-006` | un refus est la valeur par défaut lorsqu'une information manque |
| `V2-ADR-010` | le PITR DynamoDB et le versioning S3 sont non désactivables et gardés par `terraform_plan_guard.py` |
| `V2-ADR-010` | une restauration ne réintroduit jamais un état incohérent entre magasins |
| `V2-ADR-014` | une action mutante est matérialisée, confirmée hors du chemin du modèle, puis exécutée |
| `V2-ADR-002` | le contenu de Memory est une donnée non fiable |
| Charte §4.2 | aucune organisation ni gouvernance client inventée n'entre dans le périmètre |
| Charte §6 Sécurité | logs sans données sensibles en clair ; rétention des traces distincte de celle des documents |
| HLD §11 | chaque catégorie de donnée dispose d'une rétention, d'un mécanisme de suppression et d'un test |

## Le fait déterminant — la durabilité décidée par `V2-ADR-010` fixe un plancher à l'effacement

`V2-ADR-010` impose le PITR DynamoDB sur `Trips`, `documents`, `users` et le ledger, avec une
fenêtre de 35 jours, et fait garder cette activation par `terraform_plan_guard.py` : un plan qui la
désactiverait est bloqué. La décision est justifiée — elle sert le RPO « quasi nul » du tableau
RTO/RPO. Elle a une conséquence que l'ADR n'énonce pas.

Le PITR est une sauvegarde continue restaurable vers une table neuve. Il n'expose aucune opération
de rédaction : on ne peut pas retirer un item d'une fenêtre PITR. Tant que la fenêtre couvre
l'instant qui précède un effacement, une copie exploitable de la donnée effacée existe, et une
opération de restauration parfaitement légitime la réintroduit.

**La profondeur de restauration et la fenêtre résiduelle d'effacement ne sont pas deux paramètres :
c'est le même paramètre, lu dans deux sens opposés.** Réduire la fenêtre PITR raccourcit le résidu
d'effacement et dégrade le RPO ; l'allonger fait l'inverse. Aucune politique d'effacement ne peut
promettre une échéance inférieure à cette fenêtre sans contredire `V2-ADR-010`.

`V2-LLD-006` §8.4 écrit pourtant `users.erasureCompletedAt = now` à l'étape 4 de la séquence, juste
après la suppression des documents. À l'instant où cet horodatage est écrit, l'affirmation qu'il
porte est fausse pour une durée pouvant atteindre 35 jours.

## Ce que le corpus décompose mal — « volatile » qualifie la sauvegarde, pas la rétention

La `capability-allocation-matrix.md` et `V2-LLD-006` §9 qualifient AgentCore Memory de « volatile
par conception » et en tirent trois conséquences : aucune sauvegarde, aucun RTO/RPO engagé,
effacement au best-effort. Les deux premières sont correctes. La troisième ne suit pas.

`V2-LLD-006` §8.3 énonce l'argument sous sa forme la plus explicite :

> « pas de sauvegarde donc pas de résidu »

L'implication est invalide. L'absence de sauvegarde signifie qu'aucune **copie** ne survit ; elle ne
dit rien de la durée de vie de l'**original**. Une donnée peut n'être sauvegardée nulle part et
demeurer indéfiniment dans son magasin primaire. « Volatile » qualifie ici la stratégie de
sauvegarde, et le corpus l'a lu comme une propriété de rétention.

La V1 fournit le contre-exemple, dans le corpus lui-même.
`docs/validation/V1-MEMORY-SECURITY-SUMMARY-FR.md` documente que l'objet du correctif V1 était
précisément de faire **survivre les préférences à la session**. Il distingue deux natures de
contenu :

> « les **événements de mémoire**, écrits par `create_event` ; les **enregistrements longue durée**,
> produits uniquement lorsqu'une stratégie Memory les extrait. »

et décrit la stratégie retenue :

```text
Nom       : TravelPreferences
Type      : USER_PREFERENCE
Namespace : /travel/{actorId}/preferences
Statut    : ACTIVE
```

Aucune durée d'expiration n'est configurée sur cette mémoire, ni en V1 ni dans le corpus V2. Les
enregistrements longue durée sont donc, en l'état, la donnée personnelle **la plus durable du
système** : ils survivent à la session, n'ont pas de TTL, sont dérivés du contenu conversationnel de
l'utilisateur, et ne sont couverts par aucune procédure d'effacement vérifiée.

Le corpus traite comme négligeable la seule donnée pour laquelle il n'a fixé aucune borne.

## Inventaire des résidus après un effacement logique

L'effacement logique désigne l'état atteint à la fin de `V2-LLD-006` §8.4 : plus aucun magasin
interrogé en ligne ne retourne la donnée. Ce tableau énumère ce qui subsiste au-delà.

| Magasin | Donnée concernée | Résidu après effacement logique | Borne |
|---|---|---|---|
| DynamoDB `documents`, `Trips`, `users`, ledger | métadonnées, données métier, trace | **oui** — la fenêtre PITR contient l'état antérieur, non rédactible | fenêtre PITR (35 jours, `V2-ADR-010`) |
| S3 `sources/` | contenu documentaire | **non**, à condition de supprimer chaque version et non de poser un marqueur de suppression | immédiat si la condition est tenue |
| S3 Vectors | chunks et extraits | **non** — état dérivé, retiré par la resynchronisation, vérifié en §8.2 étape 4 | immédiat après vérification |
| AgentCore Memory — enregistrements longue durée | préférences extraites | **oui aujourd'hui** — ni TTL, ni suppression vérifiée | non borné en l'état |
| AgentCore Memory — événements de session | tours de conversation | **oui aujourd'hui** — aucune durée d'expiration configurée | non borné en l'état |
| Ledger d'idempotence | références de mutations | non au-delà du TTL | 7 jours, inclus dans la fenêtre PITR |
| Journaux et traces | identifiants hashés, jamais de contenu en clair (`V2-ADR-006`) | pseudonymisé, conservé délibérément | rétention d'audit (`V2-LLD-007`) |
| État Terraform, artefacts CI | aucune donnée personnelle | sans objet | sans objet |

Deux résidus seulement demandent une décision : la fenêtre PITR, qui est une contrainte imposée par
`V2-ADR-010`, et la mémoire, qui est aujourd'hui non bornée par omission.

## Choix du modèle d'effacement

### Option A — Effacement immédiat et total (statu quo implicite de `V2-LLD-006` §8.4)

`erasureCompletedAt` signifie que plus aucune copie de la donnée n'existe nulle part.

**Rejet.** L'option est irréalisable sous `V2-ADR-010` : elle exigerait de désactiver le PITR, ce
que `terraform_plan_guard.py` bloque, ou de rédiger une fenêtre PITR, ce que le service ne permet
pas. Elle ne serait pas seulement imprécise, elle serait fausse — et une trace d'audit qui atteste
un fait faux est pire que l'absence de trace.

### Option B — Effacement logique immédiat, fenêtre résiduelle bornée et déclarée

L'effacement retire immédiatement la donnée de tous les magasins interrogés en ligne. Le système
déclare explicitement une fenêtre résiduelle pendant laquelle une restauration légitime peut encore
exposer la donnée, et se dote du mécanisme qui neutralise cette réintroduction.

**Avantages :** l'affirmation portée par l'audit devient vraie ; la fenêtre est calculable à partir
de paramètres déjà décidés ; aucun conflit avec `V2-ADR-010`.

**Limites :** la garantie offerte est plus faible qu'un effacement total ; elle doit être énoncée
plutôt que sous-entendue, ce qui est un coût de documentation et de communication.

### Option C — Effacement cryptographique par clé utilisateur

Chaque utilisateur dispose d'une clé de chiffrement dédiée. L'effacement détruit la clé : toutes les
copies, y compris celles contenues dans les fenêtres PITR et les versions S3, deviennent
indéchiffrables sans être touchées.

**Rejet.** L'option résout réellement le problème de la sauvegarde, et resterait la réponse
pertinente si une exigence légale opposable apparaissait. Elle est disproportionnée ici pour trois
raisons cumulatives. DynamoDB chiffre au niveau de la table, pas de l'item : une clé par utilisateur
impose un chiffrement côté client sur les attributs concernés, donc une bibliothèque de chiffrement
applicative, une gestion de clés de données et la perte des requêtes sur les attributs chiffrés. Le
coût KMS devient proportionnel au nombre d'utilisateurs, sur un projet dont la Charte exclut tout
engagement de production réel. Enfin la destruction d'une clé KMS impose un délai d'attente
minimal de sept jours : l'effacement ne serait pas instantané non plus, seulement borné plus court.

## Décision — Modèle d'effacement

Retenir **l'option B**.

Trois horodatages sont distingués sur l'entrée `users`, là où `V2-LLD-006` §6.2 en prévoit deux :

```text
erasureRequestedAt   demande acceptée et matérialisée
erasureCompletedAt   effacement logique atteint — aucun magasin en ligne ne retourne la donnée
erasureDurableAt     erasureCompletedAt + residualWindowDays — plus aucune copie restaurable
```

`erasureDurableAt` est une valeur **calculée**, pas le résultat d'un traitement : la fenêtre PITR
s'écoule d'elle-même. Aucun job n'est requis à cette échéance.

```text
residualWindowDays = max(fenêtres PITR des tables couvertes par V2-ADR-010)
                     Trips, documents, users, ledger — 35 jours en l'état
```

Le maximum, et non la valeur commune : le PITR se configure table par table. Les quatre tables
partagent aujourd'hui la même fenêtre, mais une seule d'entre elles dont la fenêtre serait allongée
étendrait le résidu réel sans que la constante déclarée le reflète. La fenêtre résiduelle est une
propriété du système, pas d'une table.

Les autres résidus du tableau ci-dessus sont soit immédiats, soit strictement inclus dans cette
fenêtre — le ledger expire en 7 jours, S3 est purgé version par version, S3 Vectors est vérifié à
zéro. La fenêtre résiduelle est donc entièrement déterminée par un paramètre déjà décidé ailleurs.

Deux règles en découlent, qui sont la contrepartie de la décision :

- **la suppression S3 supprime chaque version.** Un marqueur de suppression laisse les versions
  antérieures accessibles et rendrait S3 résiduel pendant 90 jours (`V2-LLD-006` §10). L'effacement
  utilisateur exige une suppression permanente de toutes les versions, vérifiée par le comptage
  déjà prévu en §8.2 étape 4 ;
- **`erasureCompletedAt` n'est plus présenté comme la fin de l'effacement.** Il atteste l'effacement
  logique. La fin est `erasureDurableAt`, et c'est cette date qui est communiquée si une demande
  d'attestation est formulée.

## Choix du statut de la mémoire longue durée

### Option A — Mémoire volatile, effacement au best-effort (statu quo `V2-LLD-006` §8.3)

Memory ne bloque pas la suppression coordonnée ; l'expiration naturelle suffit.

**Rejet.** L'« expiration naturelle » invoquée n'existe pas : aucune durée d'expiration n'est
configurée, ni en V1 ni en V2. L'option laisse la donnée personnelle la moins bornée du système hors
de toute procédure d'effacement, en contradiction directe avec `V2-ADR-006`, qui exige la
coordination de Memory dans la suppression, et avec HLD §11, qui exige un mécanisme de suppression
par catégorie de donnée.

### Option B — La mémoire longue durée est une donnée personnelle, effacée et vérifiée

Les enregistrements produits par une stratégie Memory sont traités comme les autres données
personnelles : rétention explicite, suppression obligatoire lors d'un effacement, vérification
post-suppression.

**Avantages :** aligne Memory sur l'exigence déjà écrite de `V2-ADR-006` ; supprime la seule
catégorie de donnée non bornée ; conserve la valeur fonctionnelle de la mémoire longue durée
construite en V1.

**Limites :** dépend de l'existence d'API de suppression et d'expiration côté AgentCore Memory, non
vérifiées à ce stade. Fait de Memory un magasin dont l'échec de suppression doit être traité, alors
qu'il était réputé sans conséquence.

### Option C — Préférences déportées en DynamoDB, mémoire purement conversationnelle

Les préférences durables migrent vers une table DynamoDB ; Memory ne porte plus que l'état de
session.

**Rejet comme décision V2.** L'option rend l'effacement trivial — la mécanique documentaire
s'applique telle quelle — mais retire à AgentCore Runtime la capacité `Memory Persistence` dont la
CAM le déclare propriétaire (Domaine 6), ce qui constitue un amendement à `V2-ADR-002`. Elle est
retenue comme **repli conditionnel** : si la précondition sur les API de suppression Memory n'est
pas satisfaite, cette option devient la seule conforme, et l'ADR bascule dessus plutôt que de
tolérer une donnée personnelle ineffaçable.

## Décision — Statut de la mémoire

Retenir **l'option B**, avec l'option C comme repli conditionnel explicite.

La règle qui tranche est fail-closed et se formule sans ambiguïté :

> **AgentCore Memory ne peut contenir une donnée personnelle que si sa suppression est prouvée.**
> Tant que la suppression n'est pas démontrée par un test, aucune stratégie de mémoire longue durée
> n'est activée en V2.

Cette règle est la transposition à Memory du principe déjà retenu par `V2-ADR-006` — le refus est la
valeur par défaut lorsqu'une information manque. Elle rend la précondition bloquante au lieu de
laisser un doute se propager jusqu'à l'exploitation.

## Les deux mémoires et leur cycle de vie

Le corpus emploie « Memory » pour deux objets dont les profils de rétention n'ont rien de commun.
Cet ADR les sépare et fixe le cycle de vie que `V2-LLD-006` §9 laisse ouvert.

| | Mémoire de session | Mémoire longue durée |
|---|---|---|
| Contenu | tours de conversation écrits au fil de l'invocation | préférences extraites par une stratégie |
| Portée | une session | toutes les sessions d'un acteur |
| Écriture | au fil de l'invocation | après le dernier tour réussi (`V2-LLD-003` §2.5) |
| Rétention | durée d'expiration explicite, paramètre Terraform | pas d'expiration automatique |
| Suppression sur effacement | couverte par l'expiration si elle est inférieure à la fenêtre résiduelle ; suppression explicite sinon | **explicite et vérifiée**, sans exception |
| Sauvegarde | aucune | aucune |
| Restauration | aucune | aucune |

Deux points méritent d'être énoncés plutôt que déduits.

La mémoire longue durée **n'a délibérément pas d'expiration automatique** : une préférence qui
s'effacerait seule au bout de N jours détruirait la fonctionnalité que la V1 a construite. Sa borne
n'est pas temporelle, elle est l'effacement — ce qui est précisément pourquoi l'effacement doit être
prouvé.

La mémoire de session reçoit **une durée d'expiration explicite**, choisie inférieure à la fenêtre
résiduelle. Ce choix n'est pas cosmétique : il fait entrer la mémoire de session dans le résidu déjà
borné par le PITR, au lieu d'en constituer un second, non borné et de nature différente.

L'absence de sauvegarde de Memory reste acquise et n'est pas rediscutée. Elle a une conséquence
utile ici : la mémoire ne figure dans aucune procédure de restauration, donc dans aucun rejeu.

## L'obligation de rejeu après restauration

C'est la contrepartie opérationnelle du modèle retenu, et le point que le corpus traite aujourd'hui
de façon incorrecte.

`V2-LLD-006` §13.4 examine le cas et conclut qu'il n'y a pas de problème :

> « Une entrée `users.erasureCompletedAt` restaurée par PITR **ne réintroduit pas** les documents
> effacés (ils ont été supprimés, pas archivés). »

Le raisonnement ne porte que sur la table `users`. Il est exact pour elle, et sans objet pour le
reste. Une restauration PITR de `documents` à un instant T antérieur à un effacement réintroduit les
entrées de métadonnées de l'utilisateur effacé — nom de fichier, tenant, classification, versions.
Pire, la séquence de restauration cohérente de `V2-LLD-006` §13.3 déclenche à l'étape 5 une
ré-ingestion ciblée sur les documents en `status = indexed` : elle tenterait de réindexer des
documents effacés. Les objets S3 ayant été supprimés, la ré-ingestion échouerait — mais les
métadonnées, elles, seraient bel et bien revenues.

**Règle retenue.** Toute restauration ramenant un magasin à un instant T est suivie, avant remise en
service, du **rejeu de tous les effacements dont `erasureCompletedAt` est postérieur à T**.

La source du rejeu ne peut pas être la table `users` : elle est elle-même soumise au PITR et peut
avoir été ramenée en arrière. La source autoritative est le **journal d'audit** émis à l'étape 5 de
`V2-LLD-006` §8.4, en append-only, hors du périmètre de restauration des tables. Une contrainte en
découle :

```text
rétention(événements d'audit d'effacement) >= fenêtre PITR
```

Sans cette inégalité, une restauration au bord de la fenêtre PITR pourrait ne plus disposer de la
liste des effacements à rejouer.

Une seconde contrainte, plus forte, porte sur le magasin lui-même. `V2-LLD-006` §8.4 émet à
l'étape 5 un « événement d'audit » sans en fixer la destination : en l'état, rien n'interdit qu'il
atterrisse dans une table DynamoDB, donc sous PITR. **Une source de rejeu restaurable en même temps
que les tables qu'elle sert à corriger n'est pas une source.** Le journal d'effacement ne peut donc
pas être porté par une ressource couverte par le PITR de `V2-ADR-010`.

Un magasin append-only hors du périmètre des restaurations de tables — groupe de journaux CloudWatch
dédié avec rétention explicite, ou équivalent — satisfait les deux contraintes. Le choix du médium
revient à `V2-LLD-006` ; l'indépendance et la rétention sont des intrants de ce choix, pas des
préférences.

## La séquence d'un effacement

La séquence complète `V2-LLD-006` §8.4 sans la remplacer. Les étapes 3 à 6 y figurent déjà ; les
autres sont ajoutées par cet ADR.

```text
1. Matérialisation
     La demande d'effacement est une action mutante au sens de V2-ADR-014 :
     elle est matérialisée en commande, confirmée hors du chemin du modèle,
     puis exécutée par référence. Un modèle ne déclenche jamais un effacement
     sur la seule foi d'un tour de conversation.

2. Acceptation
     users.erasureRequestedAt = now ; erasureOperationId = uuid
     Événement d'audit émis (append-only).

3. Suppression documentaire
     Pour chaque documentId de l'utilisateur : séquence V2-LLD-006 §8.2,
     avec suppression permanente de chaque version S3 (pas de marqueur).

4. Suppression mémoire
     Enregistrements longue durée du namespace de l'acteur : suppression
     explicite, puis vérification par relecture (résultat attendu : vide).
     Mémoire de session : couverte par la durée d'expiration configurée.

5. Vérification d'absence
     S3 : comptage par préfixe = 0, toutes versions.
     S3 Vectors : Retrieve filtré = 0.
     Memory : relecture du namespace = 0 enregistrement.
     Une vérification non concluante interdit l'étape 6.

6. Clôture logique
     users.erasureCompletedAt = now
     users.erasureDurableAt   = now + residualWindowDays
     Événement d'audit émis (append-only) — source du rejeu §restauration.
```

L'étape 5 est la garde du modèle : `erasureCompletedAt` n'est écrit qu'après vérification, jamais
par simple succès des appels de suppression. C'est la même discipline que `V2-LLD-006` §8.2 applique
déjà au passage en `status = deleted`, étendue à l'effacement utilisateur et à Memory.

## L'effacement incomplet est un état, pas un échec silencieux

Rendre la suppression Memory bloquante crée un état que le corpus ne connaissait pas : une entrée
`users` porte `erasureRequestedAt` et `erasureOperationId`, mais pas `erasureCompletedAt`. Les
documents sont partis, les vecteurs aussi ; la mémoire est encore là. Cet état est la conséquence
directe et voulue de la décision, et il doit être traité comme un état nommé plutôt que comme une
anomalie.

Trois propriétés le rendent exploitable.

**Il est observable.** L'absence de `erasureCompletedAt` sur une entrée dont `erasureRequestedAt`
est renseigné est la définition de l'effacement en cours ; elle est interrogeable sans journal
annexe. Une alerte d'exploitation est levée lorsque cet état se prolonge au-delà du seuil défini
plus bas, et non lorsqu'un appel échoue — un échec suivi d'une reprise réussie n'est pas un
incident.

**Il est reprenable.** Chaque étape de la séquence se termine par une vérification par relecture,
donc chaque étape est rejouable sans effet de bord : supprimer ce qui est déjà supprimé et relire un
namespace vide sont des opérations idempotentes. La reprise reprend la séquence à l'étape 3, sans
état intermédiaire à conserver, et sans nouvelle confirmation `V2-ADR-014` — la commande a déjà été
confirmée, `erasureOperationId` en est la trace. En V2 la reprise est manuelle, déclenchée par
l'opérateur via le runbook `V2-LLD-006` §18.3.

**Il ne rend rien à l'utilisateur.** L'effacement en cours n'est pas un rollback : les données déjà
supprimées ne reviennent pas, et l'accès reste refusé. Le système ne repasse jamais d'un effacement
partiel à un état nominal ; il n'avance que vers la clôture.

## Ce que l'effacement ne couvre pas

Énoncer ces exclusions fait partie de la décision : un effacement dont le périmètre est implicite ne
peut être ni testé ni attesté.

- **Les journaux et traces** conservent des identifiants hashés (`V2-ADR-006`) et aucun contenu en
  clair. Ils ne sont pas purgés par un effacement : ils sont pseudonymisés par construction et
  conservés selon la rétention d'audit de `V2-LLD-007`. La correspondance permettant la
  ré-identification est l'entrée `users`, dont le contenu personnel a précisément été retiré.
- **La trace d'effacement elle-même** est conservée (`V2-LLD-006` §8.5). Elle ne contient que
  l'identifiant, le tenant et les horodatages. La supprimer rendrait l'effacement invérifiable, donc
  contraire à l'exigence de preuve.
- **Le journal d'audit des effacements** est conservé au-delà de la fenêtre PITR, par la contrainte
  de rejeu établie plus haut.
- **Les données agrégées non ré-identifiables** — métriques de volume, comptages, coûts — ne sont
  pas concernées.
- **Les sauvegardes déjà écrites** ne sont pas rédigées ; elles expirent. C'est l'objet même de la
  fenêtre résiduelle.

## Le délai d'effacement est un paramètre, pas une obligation inventée

La Charte §4.2 exclut du périmètre toute « organisation ou gouvernance client inventée ». Fixer dans
un ADR un délai présenté comme une obligation légale reviendrait à inventer l'exigence d'un client
qui n'existe pas, et à transformer une hypothèse en engagement.

Cet ADR ne fixe donc aucun délai légal. Il fixe :

- un **plancher technique**, qui n'est pas négociable et se déduit de `V2-ADR-010` :

```text
delaiEffacementAnnonce >= residualWindowDays
```

- un **paramètre Terraform** `erasure_sla_days`, sans valeur imposée par l'architecture, dont toute
  valeur inférieure au plancher est refusée à la validation du plan. Sa sémantique est celle d'un
  **délai annonçable** : la durée maximale entre `erasureRequestedAt` et `erasureDurableAt` que le
  système s'engage à tenir. Elle se décompose en une part pilotable — les étapes 1 à 6, de l'ordre
  de la minute lorsqu'elles réussissent — et une part subie, la fenêtre résiduelle, qui n'est pas
  raccourcissable. Le paramètre est consommé à deux endroits, et à deux seulement : la garde de
  plan, et l'alerte d'exploitation qui se déclenche lorsqu'un effacement encore incomplet met le
  délai annoncé hors d'atteinte, soit à `erasureRequestedAt + erasure_sla_days -
  residualWindowDays`. Un `erasure_sla_days` fixé au plancher exact réduit ce seuil d'alerte à
  zéro : tout effacement non clôturé immédiatement alerte. C'est cohérent, et c'est la raison
  d'être de la marge que l'exploitant choisit d'ajouter au plancher ;
- une **règle de cohérence** : si un délai plus court devenait exigible, le seul levier conforme est
  la réduction de la fenêtre PITR, au prix documenté du RPO, ou la bascule vers l'effacement
  cryptographique de l'option C. Aucun autre chemin ne raccourcit le résidu.

Cette formulation laisse la décision de politique à qui exploite le système, tout en rendant
impossible l'annonce d'un délai que l'architecture ne peut pas tenir.

## Réalisation par phase

| | V2 | Cible V3 |
|---|---|---|
| Effacement utilisateur | composition de suppressions documentaires (`V2-LLD-006` §8.4) | saga applicative sur trois magasins (`V2-ADR-019`) |
| Suppression vectorielle | resynchronisation KB puis vérification | suppression directe S3 Vectors |
| Suppression mémoire | appel explicite + relecture de vérification | inchangé |
| Rejeu après restauration | procédure d'exploitation documentée, exécutée au DR drill | automatisé depuis le journal d'audit |
| Fenêtre résiduelle | fenêtre PITR, déclarée | inchangée sauf décision de politique |

Le rejeu reste manuel en V2 : il est rare, il suit une restauration qui est elle-même une opération
encadrée, et son automatisation prématurée introduirait un traitement destructeur déclenché
automatiquement — risque supérieur au gain.

## Écarts à corriger dans le corpus

Ces corrections découlent de l'acceptation de l'ADR et ne sont pas appliquées par lui.

| Document | Écart | Correction attendue |
|---|---|---|
| `capability-allocation-matrix.md` Domaine 6 | « Memory est volatile » sans distinguer session et longue durée | distinguer les deux natures ; la longue durée est durable et effaçable |
| `V2-ADR-006` §Suppression | « Memory autorisée » ne dit pas ce qui est vérifié | renvoyer à la vérification d'absence de cet ADR |
| `V2-ADR-010` | le PITR est décidé sans énoncer son effet sur l'effacement | ajouter la conséquence : la fenêtre PITR est le plancher de l'effacement |
| `V2-LLD-006` §2 | ligne `Memory` : « volatile ; expiration naturelle » | remplacer par les deux lignes session / longue durée avec leurs rétentions |
| `V2-LLD-006` §8.3 | « pas de sauvegarde donc pas de résidu » et effacement best-effort | remplacer par la suppression explicite vérifiée |
| `V2-LLD-006` §8.4 | `erasureCompletedAt` présenté comme la fin de l'effacement | ajouter `erasureDurableAt` et la vérification d'absence en garde |
| `V2-LLD-006` §8.4 étape 5 | « événement d'audit émis » sans destination : rien n'interdit une table sous PITR | fixer le médium du journal d'effacement, hors périmètre PITR, avec rétention >= fenêtre résiduelle |
| `V2-LLD-006` §6.2 | schéma `users` sans `erasureDurableAt` | ajouter l'attribut |
| `V2-LLD-006` §9.2 | « Memory incluse au best-effort » | aligner sur la suppression vérifiée |
| `V2-LLD-006` §10 | ligne `Memory` : « volatil / expiration naturelle » | deux lignes avec la durée d'expiration paramétrée |
| `V2-LLD-006` §13.3 et §13.4 | la restauration ne rejoue pas les effacements ; §13.4 ne raisonne que sur `users` | ajouter l'étape de rejeu avant remise en service |
| `V2-LLD-006` §16 | les règles du guard sont toutes booléennes (PITR activé, versioning actif, chiffrement présent) | ajouter deux règles de borne : `erasure_sla_days >= residualWindowDays` et rétention du journal d'effacement >= fenêtre PITR — un mode de contrôle nouveau pour ce script |
| `V2-LLD-006` §18.3 | le runbook d'effacement ne couvre pas la reprise d'un effacement incomplet | ajouter la reprise à l'étape 3, idempotente, sans nouvelle confirmation |
| `V2-LLD-006` §17.2 | le DR drill ne comporte pas d'effacement | ajouter le scénario effacement → restauration antérieure → rejeu, avec le volet sans rejeu |
| `V2-LLD-003` §2.5 | le contrat d'usage Memory ne mentionne ni rétention ni effacement | renvoyer explicitement à cet ADR |
| `LLD-V2-INDEX-FR.md` | portée de `V2-LLD-005` sans le rejeu ni la rétention d'audit | ajouter la contrainte de rétention du journal d'effacement |

## Préconditions

Cinq points doivent être établis avant implémentation. **Trois sont bloquants**, avec deux
conséquences d'échec distinctes : l'échec de la précondition 1 ou 2 fait basculer la décision sur
l'option C ; l'échec de la précondition 3 n'a pas de repli.

1. **Suppression Memory — bloquante, repli option C.** Existence d'une opération de suppression des
   enregistrements longue durée d'un namespace, et d'une relecture permettant de vérifier l'absence.
   `V2-LLD-003` §9 signale déjà que les préfixes IAM AgentCore ont évolué et sont « à confirmer
   nominativement » : la même prudence s'applique ici, l'API doit être vérifiée sur le service, pas
   supposée.
2. **Expiration Memory — bloquante, repli option C.** Existence d'une durée d'expiration
   configurable sur les événements de session, et valeur maximale admise. Si l'expiration n'est pas
   configurable, la mémoire de session devient un résidu non borné et relève du même repli.
3. **Indépendance du journal d'audit — bloquante, sans repli.** Le journal servant au rejeu doit
   être en append-only, hors du périmètre des restaurations de tables, et retenu au moins aussi
   longtemps que la fenêtre résiduelle. Sans lui, le rejeu perd sa source autoritative et la fenêtre
   résiduelle cesse d'être fermée par un mécanisme : elle redevient une déclaration invérifiable,
   c'est-à-dire exactement ce que cet ADR corrige. Contrairement aux deux premières, cette
   précondition n'admet aucune option de repli — aucune décision de cet ADR ne rend le rejeu
   superflu. Tant qu'elle n'est pas satisfaite, une restauration PITR reste techniquement possible
   mais réintroduit des données effacées sans moyen de les retirer : elle doit alors être traitée
   comme interdite, non comme dégradée.
4. **Fenêtre PITR effective.** Confirmer la valeur retenue et sa configurabilité, puisqu'elle
   détermine `residualWindowDays` et donc le plancher annonçable.
5. **Suppression permanente S3 par version.** Vérifier que la séquence de suppression retire chaque
   version et ne pose pas de marqueur, faute de quoi S3 constituerait un résidu de 90 jours,
   supérieur à la fenêtre PITR et donc non couvert par la fenêtre déclarée.

## Périmètre exclu

- **Le régime juridique applicable**, la base légale des traitements et le registre associé : la
  Charte exclut toute gouvernance client inventée. Cet ADR fournit un mécanisme et un plancher, pas
  une qualification juridique.
- **Le droit d'accès et la portabilité** : mécanismes distincts, non instruits ici.
- **La classification documentaire** et les règles d'accès par niveau : `V2-ADR-017`.
- **La rétention des traces et l'échantillonnage** : `V2-ADR-008` et `V2-LLD-007`.
- **La forme de la confirmation** de la demande d'effacement : `V2-ADR-014`, appliqué tel quel.
- **La réplication cross-région**, qui ajouterait un résidu supplémentaire : hors périmètre projet
  (`V2-ADR-010`), à réinstruire si elle était introduite.

## Conséquences

- La fenêtre résiduelle devient une **propriété déclarée du système**, calculée depuis un paramètre
  existant, testable et opposable. Elle cesse d'être un angle mort.
- `V2-ADR-010` acquiert une conséquence qu'il n'avait pas énoncée : le choix de la profondeur PITR
  est aussi un choix de politique d'effacement, et ne peut plus être arbitré sur le seul RPO.
- La mémoire longue durée entre dans le périmètre des données personnelles, avec le coût associé —
  suppression, vérification, test d'isolation. La contrepartie est la disparition de la seule
  catégorie de donnée sans borne du corpus.
- Une suppression Memory qui échoue devient **bloquante** : `erasureCompletedAt` n'est pas écrit, et
  l'effacement reste en cours. C'est un changement d'exploitation réel par rapport au best-effort de
  `V2-LLD-006` §8.3, qui ne produisait aucune alerte. L'exploitation gagne un état à surveiller et
  un geste de reprise à documenter — c'est le prix assumé de la garantie.
- Toute restauration acquiert une étape supplémentaire obligatoire. Le DR drill trimestriel de
  `V2-ADR-010` doit désormais inclure un effacement, une restauration antérieure et le rejeu.
- Le journal d'audit d'effacement devient une **ressource d'architecture contrainte** — médium hors
  PITR, rétention minimale — là où `V2-LLD-006` §8.4 n'émettait qu'un événement sans destination.
- Si la précondition 1 ou 2 échoue, la décision bascule sur l'option C : les préférences quittent
  Memory pour DynamoDB, ce qui constitue un amendement à la CAM Domaine 6 et donc à `V2-ADR-002`.
  Ce chemin est prévu, pas subi.
- `terraform_plan_guard.py` doit apprendre un **mode de contrôle qu'il n'a pas** : ses règles
  existantes et celles que `V2-LLD-006` §16 lui prévoit sont toutes booléennes — une ressource
  détruite, un drapeau désactivé. Vérifier `erasure_sla_days >= residualWindowDays` et la rétention
  du journal exige de comparer des valeurs numériques dans le plan. Sans cette extension, le
  plancher pourrait être franchi par un simple changement de variable.

## Preuves attendues

- un effacement utilisateur ne laisse aucun objet S3 sous le préfixe de l'utilisateur, **toutes
  versions confondues**, et aucun marqueur de suppression masquant une version conservée ;
- un `Retrieve` filtré sur le tenant et l'utilisateur effacé renvoie zéro chunk ;
- une relecture du namespace Memory de l'acteur effacé renvoie zéro enregistrement longue durée ;
- un échec simulé de la suppression Memory laisse l'effacement en cours et **n'écrit pas**
  `erasureCompletedAt` ; l'alerte d'exploitation se déclenche au seuil attendu, et la reprise après
  rétablissement du magasin conduit à la clôture sans nouvelle confirmation ni effet de bord ;
- **preuve centrale, portée par le DR drill trimestriel** (`V2-ADR-010`, `V2-LLD-006` §17.2) : une
  restauration PITR à un instant antérieur à un effacement, suivie du rejeu, ne réintroduit aucune
  métadonnée de l'utilisateur effacé — et la même restauration **sans** rejeu la réintroduit. Le
  second volet n'est pas facultatif : sans lui, le test passe tout aussi bien lorsque le rejeu ne
  fait rien, et n'atteste que l'absence de donnée. C'est la seule preuve du corpus qui démontre que
  la fenêtre résiduelle est fermée par un mécanisme et non par une déclaration ;
- la rétention configurée du journal d'audit d'effacement est supérieure ou égale à la fenêtre PITR,
  et le journal n'est porté par aucune ressource couverte par le PITR — les deux vérifiées sur le
  plan Terraform ;
- un plan fixant `erasure_sla_days` sous le plancher est bloqué par `terraform_plan_guard.py` ;
- les événements de session dépassant la durée d'expiration configurée ne sont plus lisibles ;
- deux acteurs distincts ne partagent aucun enregistrement de mémoire longue durée, avant comme
  après un effacement de l'un des deux.

## Références

- `V2-ADR-006` — isolation, suppression coordonnée, journalisation pseudonymisée ;
- `V2-ADR-010` — PITR, versioning, cohérence et DR drills ;
- `V2-ADR-014` — matérialisation et confirmation des actions mutantes ;
- `V2-LLD-006` — mécanique de suppression, schéma `users`, rétention et restauration ;
- `V2-LLD-003` §2.5 — contrat d'usage de Memory par le code agent ;
- `docs/validation/V1-MEMORY-SECURITY-SUMMARY-FR.md` — distinction événements / enregistrements
  longue durée et stratégie `USER_PREFERENCE` de la V1 ;
- Amazon DynamoDB Point-in-Time Recovery — sauvegarde continue, restauration vers table neuve,
  absence d'opération de rédaction ;
- Amazon S3 Versioning — suppression par version contre marqueur de suppression ;
- AWS KMS — délai d'attente minimal avant destruction d'une clé (option C).
