# V1 — Validation sécurité négative Phase 3

> Périmètre : JWT, champs de confiance injectés par le client, CORS et frontière IAM du Runtime.
>
> La PR prépare les contrats et le workflow. Elle ne lance aucun test actif AWS, aucun déploiement et aucun `terraform apply`.

## 1. Objectif

La Phase 3 doit démontrer que le chemin public reste strictement limité à :

```text
Browser
  -> API Gateway HTTP API + Cognito JWT
  -> Lambda Security Facade
  -> AgentCore Runtime IAM-only
```

Les propriétés recherchées sont :

- un appel sans JWT ou avec un JWT mal formé est rejeté ;
- un ID token Cognito ne remplace pas un access token ;
- le navigateur ne peut fournir aucune identité ou configuration d’exécution de confiance ;
- seule l’origine CloudFront configurée reçoit l’autorisation CORS ;
- un rôle AWS autre que celui de la façade ne peut pas invoquer directement le Runtime ;
- les preuves ne contiennent aucun JWT, prompt, identifiant utilisateur ou erreur AWS brute.

## 2. Cas couverts

Le catalogue automatisé comprend :

```text
http_no_jwt
http_malformed_jwt
http_id_token
cors_allowed_preflight
cors_forbidden_preflight
runtime_direct_invoke_denied
inject_actorId
inject_userId
inject_trustedIdentity
inject_requestId
inject_deadlineEpochMs
inject_groups
inject_modelOverride
inject_systemPrompt
inject_toolName
```

Les champs injectés doivent être rejetés en HTTP 400 avant toute invocation du Runtime.

## 3. Deux niveaux de validation

### 3.1 Gate de PR hors ligne

Le job `Security Negative Contracts` :

1. installe le SDK de déploiement verrouillé ;
2. compile la façade, le harness et les tests ;
3. rejoue les tests de régression de la façade ;
4. vérifie les quatorze cas HTTP/CORS du harness avec un transport contrôlé ;
5. vérifie statiquement que CORS n’autorise pas `*` et que la route utilise un authorizer JWT ;
6. prouve que le rapport ne conserve ni token ni valeur injectée ;
7. archive les logs et le catalogue complet pendant 90 jours.

Ces preuves valident le **contrat**, pas encore l’environnement AWS déployé.

### 3.2 Workflow E2E manuel

Le job `Security Negative E2E Test` ne démarre que lorsque :

```text
run_e2e=true
confirm_e2e=true
branche=migration/secure-agentcore-v1
```

Il lit les outputs Terraform existants sans les modifier, échange un refresh token Cognito contre des tokens courts, exécute les probes, puis archive uniquement un résultat redacted.

Aucun access token ou ID token n’est passé dans les arguments du script. Ils sont fournis par variables d’environnement au seul processus de validation et masqués dans GitHub Actions.

## 4. Secret de test requis

L’entrée `refresh_token_secret_id` désigne un secret AWS Secrets Manager contenant soit :

```text
<refresh-token-brut>
```

soit :

```json
{
  "refreshToken": "<refresh-token>"
}
```

Le refresh token appartient à un utilisateur Cognito de test sans privilège. Sa durée de vie est limitée par la configuration du User Pool Client. Il doit être révoqué ou remplacé après la campagne de recette.

Le workflow ne publie jamais le contenu du secret. La requête Cognito est construite dans un fichier temporaire en mode `0600`, supprimé à la fin du job.

## 5. Preuve CORS

Deux preflights `OPTIONS` sont exécutés :

- origine CloudFront : statut 200/204, origine exacte et méthode `POST` autorisée ;
- origine arbitraire : absence de correspondance et absence de wildcard `*`.

Un statut HTTP seul ne suffit pas : la validation inspecte explicitement `Access-Control-Allow-Origin`.

## 6. Preuve JWT et identité

Les probes HTTP vérifient :

| Cas | Résultat attendu |
|---|---|
| aucun header `Authorization` | 401/403 |
| bearer mal formé | 401/403 |
| ID token Cognito | 401/403 |
| champ de confiance injecté avec access token valide | 400 |

La façade reste responsable des contrôles `token_use=access`, `client_id` attendu et `sub` non vide. Les contrats unitaires couvrent également le mauvais `client_id` et l’absence de `sub`.

## 7. Preuve IAM Runtime

Le rôle OIDC de la CI tente un appel direct `InvokeAgentRuntime` avec un payload syntaxiquement valide.

Le résultat accepté est uniquement un code de type :

```text
AccessDenied
AccessDeniedException
ForbiddenException
UnauthorizedException
```

Une invocation réussie est un échec bloquant. Une autre erreur n’est pas convertie artificiellement en succès, car elle ne prouve pas la frontière IAM.

## 8. Format des preuves

Le rapport JSON contient uniquement :

- SHA Git ;
- date UTC ;
- hôte API et empreinte du chemin ;
- origine CloudFront publique ;
- nom du cas ;
- statut PASS, FAIL ou SKIP ;
- statut HTTP ;
- empreinte éventuelle du `requestId` ;
- valeur CORS publique ;
- détail constant non sensible.

Il ne contient jamais :

```text
Authorization
JWT
refresh token
prompt utilisateur
corps de requête
actorId brut
sessionId brut
operationId brut
réponse du modèle
message AWS brut
```

## 9. Statut avant exécution AWS

| Domaine | Contrat PR | AWS E2E |
|---|---|---|
| façade JWT et champs interdits | à valider par la CI de la PR | NON TESTÉ E2E |
| CORS CloudFront/arbitraire | à valider par la CI de la PR | NON TESTÉ E2E |
| refus Runtime direct | à valider par la CI de la PR | NON TESTÉ E2E |
| rapport redacted | à valider par la CI de la PR | NON TESTÉ E2E |

Aucun statut ne doit passer à `PASS PROUVÉ E2E` avant l’exécution manuelle et l’archivage de l’artefact correspondant.

## 10. Limites et suite

Cette phase ne prouve pas encore :

- le refus du Gateway MCP pour un rôle autre que le Runtime ;
- la simulation IAM des accès à une autre table DynamoDB ou à un autre modèle ;
- l’absence de données sensibles dans les logs CloudWatch déployés ;
- le renouvellement automatique 401 dans un navigateur réel ;
- la reconnexion MCP et la latence E2E.

Ces éléments restent dans les phases de réception suivantes. Aucun déploiement, `terraform apply`, `terraform destroy` ou merge automatique n’est inclus ici.
