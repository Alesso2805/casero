import base64
import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.identity.domain.email_suppressions import ScheduledEmailKind

EMAIL_OF = text("SELECT email FROM users WHERE id = :id AND deleted_at IS NULL")


class HmacUnsubscribeTokens:
    """Reusable tokens that are never stored, so mail scanners that open links can't spend them."""

    def __init__(self, key: bytes) -> None:
        self._key = key

    def token(self, user_id: UUID, kind: ScheduledEmailKind) -> str:
        digest = hmac.new(self._key, f"{user_id}:{kind}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def valid(self, user_id: UUID, kind: ScheduledEmailKind, token: str) -> bool:
        return hmac.compare_digest(self.token(user_id, kind), token)


@dataclass(frozen=True)
class UnsubscribeLinks:
    page: str
    one_click: str


def unsubscribe_links(
    public_url: str, tokens: HmacUnsubscribeTokens, user_id: UUID, kind: ScheduledEmailKind
) -> UnsubscribeLinks:
    query = urlencode({"u": str(user_id), "k": kind, "t": tokens.token(user_id, kind)})
    base = public_url.rstrip("/")
    return UnsubscribeLinks(
        page=f"{base}/baja?{query}", one_click=f"{base}/api/public/unsubscribe?{query}"
    )


class SqlUserEmails:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def email_of(self, user_id: UUID) -> str | None:
        result = await self._connection.execute(EMAIL_OF, {"id": user_id})
        email: str | None = result.scalar_one_or_none()
        return email
