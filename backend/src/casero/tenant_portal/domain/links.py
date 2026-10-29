import base64
import hashlib
from uuid import UUID

NONCE_BYTES = 16


def signed_message(link_id: UUID, nonce: bytes) -> bytes:
    """The token is HMAC(key, link id ‖ nonce): the server can rebuild it, a leak cannot."""
    return link_id.bytes + nonce


def encode_token(mac: bytes) -> str:
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def token_hash(token: str) -> bytes:
    """What the database keeps and looks up; never the token (CLAUDE.md, rule 10)."""
    return hashlib.sha256(token.encode()).digest()


def link_url(public_url: str, token: str) -> str:
    """The token travels in the fragment, which browsers never send to a server."""
    return f"{public_url.rstrip('/')}/i#t={token}"
