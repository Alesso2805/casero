import base64
import hashlib
import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENVELOPE_VERSION = "v1"
KEY_BYTES = 32
NONCE_BYTES = 12
MIN_HMAC_KEY_BYTES = 32


class EnvelopeError(ValueError):
    pass


def b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def field_context(table: str, column: str, account_id: UUID) -> str:
    """Associated data that ties a ciphertext to its row's account and column (ADR-0007)."""
    return f"{table}.{column}:{account_id}"


@dataclass(frozen=True)
class FieldCipher:
    """AES-256-GCM in the `v1:<key_id>:<nonce>:<ciphertext>` envelope of ADR-0007."""

    keys: Mapping[str, bytes]
    active_key_id: str

    def __post_init__(self) -> None:
        if self.active_key_id not in self.keys:
            raise ValueError("the active encryption key is not among the keys")
        for key_id, key in self.keys.items():
            if ":" in key_id or len(key) != KEY_BYTES:
                raise ValueError(
                    f"encryption key {key_id!r} must be {KEY_BYTES} bytes, id without ':'"
                )

    def encrypt(self, plaintext: str, context: str) -> str:
        nonce = os.urandom(NONCE_BYTES)
        sealed = AESGCM(self.keys[self.active_key_id]).encrypt(
            nonce, plaintext.encode(), context.encode()
        )
        return ":".join((ENVELOPE_VERSION, self.active_key_id, b64encode(nonce), b64encode(sealed)))

    def decrypt(self, envelope: str, context: str) -> str:
        parts = envelope.split(":")
        if len(parts) != 4 or parts[0] != ENVELOPE_VERSION or parts[1] not in self.keys:
            raise EnvelopeError("unknown envelope or key")
        _, key_id, nonce, sealed = parts
        try:
            plaintext = AESGCM(self.keys[key_id]).decrypt(
                b64decode(nonce), b64decode(sealed), context.encode()
            )
        except (InvalidTag, ValueError) as error:
            raise EnvelopeError("the envelope does not open in this context") from error
        return plaintext.decode()


def parse_keys(value: str) -> dict[str, bytes]:
    """Reads `id:base64url,id:base64url`, the format of CASERO_ENCRYPTION_KEYS."""
    keys: dict[str, bytes] = {}
    for item in filter(None, (part.strip() for part in value.split(","))):
        key_id, _, encoded = item.partition(":")
        keys[key_id] = b64decode(encoded)
    return keys


@dataclass(frozen=True)
class DocumentHasher:
    """HMAC-SHA256 of `type:normalized_number` with the permanent key of ADR-0007."""

    key: bytes

    def __post_init__(self) -> None:
        if len(self.key) < MIN_HMAC_KEY_BYTES:
            raise ValueError(f"the document HMAC key must have at least {MIN_HMAC_KEY_BYTES} bytes")

    def digest(self, doc_type: str, normalized_number: str) -> bytes:
        message = f"{doc_type}:{normalized_number}".encode()
        return hmac.new(self.key, message, hashlib.sha256).digest()
