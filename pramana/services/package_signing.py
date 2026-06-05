"""Concrete signature verification for incoming Consumable Packages.

The domain (:mod:`pramana.domain.consumable_package`) defines the
:class:`~pramana.domain.consumable_package.SignatureVerifier` protocol but
deliberately holds no keys. This module supplies a concrete verifier; key
custody and the choice of scheme live here, at the infrastructure edge
(Mentible ADR-011 §10 leaves the signing scheme open — HMAC-SHA256 over a
shared secret is the v1 default).
"""

from __future__ import annotations

import hmac
from hashlib import sha256


class HmacSignatureVerifier:
    """Verify a package signature as ``hex(HMAC-SHA256(secret, payload))``.

    Mentible signs the canonical manifest bytes (the manifest minus its
    ``signature`` field) with the same shared secret; Pramana recomputes and
    compares in constant time. Implements
    :class:`~pramana.domain.consumable_package.SignatureVerifier`.
    """

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError(
                "HMAC signing secret is empty; refusing to verify packages "
                "with an empty key (set MENTIBLE_PACKAGE_HMAC_SECRET)."
            )
        self._secret = secret.encode("utf-8")

    def verify(self, *, signed_payload: bytes, signature: str) -> bool:
        expected = hmac.new(self._secret, signed_payload, sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def sign(self, payload: bytes) -> str:
        """Produce a signature for ``payload``.

        Not used in production ingestion (Mentible signs), but lets tests and
        local tooling mint valid packages without duplicating the scheme.
        """
        return hmac.new(self._secret, payload, sha256).hexdigest()
