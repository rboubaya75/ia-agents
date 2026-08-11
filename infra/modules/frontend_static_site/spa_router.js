// Routage des liens profonds du SPA, associé au seul comportement par défaut.
//
// Il remplace la bascule `custom_error_response` 403/404 → 200, qui se règle au niveau
// de la distribution et s'appliquait donc aussi au comportement `/api/*` : une erreur de
// la passerelle y était réécrite en 200 + `index.html`, et le front recevait du HTML là
// où il attendait un flux SSE. L'erreur devenait « issue inconnue » côté navigateur et
// 200 côté `curl`, alors que la passerelle avait refusé.
//
// Ici la réécriture est décidée à l'entrée, sur la seule forme du chemin, et ne dépend
// plus du code de réponse de l'origine. Les erreurs traversent intactes, sur tous les
// comportements.
//
// Le runtime `cloudfront-js-2.0` n'expose pas tout ES6 : ce code s'en tient à ES5.
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // Un dernier segment sans point désigne une route applicative, pas un fichier :
  // « / », « /conversations », « /conversations/abc123 ». Un segment avec point est un
  // actif (« /assets/app.4f2c.js ») et doit atteindre S3 tel quel — s'il manque, la
  // réponse d'erreur doit rester une erreur.
  var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);

  if (lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }

  return request;
}
