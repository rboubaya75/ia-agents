"""Contrat de validation du jeton — V2-LLD-005 §3.5, realise par V2-LLD-001 §7.1.3.

Ce fichier est la forme executable de la table de §3.5. Il existe parce que la porte de
qualite V2 neutralise `bearer_claims` par le point d'extension de FastAPI : le harnais
prouve le contrat de routes et le contrat SSE, mais aucune de ses requetes ne traverse
`verify_token`. La validation du jeton n'etait donc verifiee nulle part, et c'est ainsi
qu'un service refusant tout jeton d'acces Cognito a pu etre deploye.

Les jetons sont signes localement par une paire RSA jetable : le JWKS est substitue, le
reseau n'est pas le sujet. Ce qui est teste est la decision d'acceptation, pas le
transport du keyset.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import unittest

os.environ.setdefault("SSE_KEEPALIVE_SECONDS", "15")
os.environ.setdefault("COGNITO_ISSUER", "https://cognito-idp.eu-west-3.amazonaws.com/eu-west-3_TEST")
os.environ.setdefault("COGNITO_APP_CLIENT_ID", "3n4k5clientid")
os.environ.setdefault("JWKS_CACHE_TTL_SECONDS", "300")
os.environ.setdefault("JWKS_STALE_TOLERANCE_SECONDS", "3600")
os.environ.setdefault("JWKS_REFRESH_MIN_INTERVAL_SECONDS", "30")

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app import auth  # noqa: E402

ISSUER = os.environ["COGNITO_ISSUER"]
CLIENT_ID = os.environ["COGNITO_APP_CLIENT_ID"]

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_FOREIGN_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update(kid="k1", alg="RS256", use="sig")
_JWKS = {"keys": [_JWK]}

# Un jeton d'acces Cognito ne porte pas `aud` mais `client_id` ; un jeton d'identite
# porte `aud`. La valeur designee est la meme dans les deux cas.
ACCESS_TOKEN_CLAIMS = {
    "token_use": "access",
    "client_id": CLIENT_ID,
    "scope": "aws.cognito.signin.user.admin",
}
ID_TOKEN_CLAIMS = {
    "token_use": "id",
    "aud": CLIENT_ID,
    "email": "utilisateur@example.invalid",
}


def _mint(overrides: dict, signer=_KEY, kid: str = "k1") -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "iat": now, "exp": now + 600, "sub": "8a1b-utilisateur"}
    claims.update(overrides)
    return jwt.encode(claims, signer, algorithm="RS256", headers={"kid": kid})


class TokenValidationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        async def _jwks(force: bool = False) -> dict:
            return _JWKS

        self._original = auth._get_jwks
        auth._get_jwks = _jwks

    def tearDown(self) -> None:
        auth._get_jwks = self._original

    def _accepts(self, overrides: dict, **kwargs) -> bool:
        try:
            asyncio.run(auth.verify_token(_mint(overrides, **kwargs)))
            return True
        except HTTPException:
            return False

    # --- Les deux types de jeton sont acceptes ------------------------------------

    def test_cognito_access_token_is_accepted(self) -> None:
        # La regression exacte qui rendait le MVP inutilisable : le front presente ce
        # jeton, et un `aud` exige le refusait a chaque requete.
        self.assertTrue(self._accepts(ACCESS_TOKEN_CLAIMS))

    def test_cognito_id_token_is_accepted(self) -> None:
        self.assertTrue(self._accepts(ID_TOKEN_CLAIMS))

    def test_audience_may_be_a_list_containing_the_client(self) -> None:
        # Cognito emet une chaine, la RFC 7519 autorise une liste.
        self.assertTrue(self._accepts({"token_use": "id", "aud": [CLIENT_ID, "autre"]}))

    def test_absent_nbf_is_not_required(self) -> None:
        # Cognito n'emet pas de `nbf` : l'exiger refuserait tous ses jetons.
        self.assertNotIn("nbf", ACCESS_TOKEN_CLAIMS)
        self.assertTrue(self._accepts(ACCESS_TOKEN_CLAIMS))

    # --- L'audience est comparee, jamais constatee --------------------------------

    def test_access_token_of_another_client_is_refused(self) -> None:
        self.assertFalse(self._accepts({**ACCESS_TOKEN_CLAIMS, "client_id": "autre-client"}))

    def test_id_token_of_another_client_is_refused(self) -> None:
        self.assertFalse(self._accepts({**ID_TOKEN_CLAIMS, "aud": "autre-client"}))

    def test_access_token_without_client_id_is_refused(self) -> None:
        self.assertFalse(self._accepts({"token_use": "access"}))

    def test_id_token_without_aud_is_refused(self) -> None:
        self.assertFalse(self._accepts({"token_use": "id"}))

    # --- token_use ferme la table --------------------------------------------------

    def test_missing_token_use_is_refused(self) -> None:
        # Sans `token_use`, aucun claim d'audience ne peut etre designe : accepter
        # reviendrait a ne comparer l'audience de personne.
        self.assertFalse(self._accepts({"aud": CLIENT_ID}))

    def test_unexpected_token_use_is_refused(self) -> None:
        self.assertFalse(self._accepts({"token_use": "refresh", "aud": CLIENT_ID}))

    # --- Reste de la table de §3.5 --------------------------------------------------

    def test_empty_subject_is_refused(self) -> None:
        self.assertFalse(self._accepts({**ACCESS_TOKEN_CLAIMS, "sub": "   "}))

    def test_foreign_issuer_is_refused(self) -> None:
        self.assertFalse(self._accepts({**ACCESS_TOKEN_CLAIMS, "iss": "https://evil.invalid/pool"}))

    def test_expired_token_is_refused(self) -> None:
        self.assertFalse(self._accepts({**ACCESS_TOKEN_CLAIMS, "exp": int(time.time()) - 3600}))

    def test_not_yet_valid_token_is_refused(self) -> None:
        self.assertFalse(self._accepts({**ACCESS_TOKEN_CLAIMS, "nbf": int(time.time()) + 3600}))

    def test_token_signed_by_another_key_is_refused(self) -> None:
        self.assertFalse(self._accepts(ACCESS_TOKEN_CLAIMS, signer=_FOREIGN_KEY))

    def test_unknown_kid_is_refused(self) -> None:
        self.assertFalse(self._accepts(ACCESS_TOKEN_CLAIMS, kid="rotated-away"))

    def test_alg_none_is_refused(self) -> None:
        # La liste blanche est positive : interdire `none` seul laisserait passer HS256,
        # signable avec la cle publique du JWKS.
        now = int(time.time())
        forged = jwt.encode(
            {"iss": ISSUER, "sub": "x", "iat": now, "exp": now + 600, **ACCESS_TOKEN_CLAIMS},
            key=None,
            algorithm="none",
            headers={"kid": "k1"},
        )
        with self.assertRaises(HTTPException):
            asyncio.run(auth.verify_token(forged))


if __name__ == "__main__":
    unittest.main(verbosity=2)
