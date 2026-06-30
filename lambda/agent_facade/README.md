# Lambda Agent Invocation Facade

Squelette documentaire.

La Lambda Facade sera implémentée dans une PR ultérieure.

Responsabilités cibles :

- lire les claims validés par API Gateway ;
- dériver `actorId` depuis `claims.sub` ;
- rejeter les champs d’identité fournis par le client ;
- invoquer AgentCore Runtime ;
- normaliser la réponse.
