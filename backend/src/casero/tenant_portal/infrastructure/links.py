import os
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.crypto import HmacKeyring
from casero.tenant_portal.application.links import TenantLink
from casero.tenant_portal.domain.links import NONCE_BYTES, encode_token, signed_message

PORTAL_ENABLED = text("SELECT tools_enabled FROM leases WHERE id = :lease_id")
LOCKED_PORTAL_ENABLED = text("SELECT tools_enabled FROM leases WHERE id = :lease_id FOR UPDATE")
CURRENT = text(
    "SELECT id, lease_id, nonce, key_id, created_at, last_used_at FROM tenant_links"
    " WHERE lease_id = :lease_id AND revoked_at IS NULL"
)
ADD = text(
    "INSERT INTO tenant_links (id, account_id, lease_id, nonce, key_id, token_hash, created_at)"
    " VALUES (:id, :account_id, :lease_id, :nonce, :key_id, :token_hash, :created_at)"
)
REVOKE = text("UPDATE tenant_links SET revoked_at = :at WHERE id = :id AND revoked_at IS NULL")


class SqlLinks:
    """Reads under RLS: only the account in context is visible."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def portal_enabled(self, lease_id: UUID, lock: bool) -> bool | None:
        query = LOCKED_PORTAL_ENABLED if lock else PORTAL_ENABLED
        result = await self._connection.execute(query, {"lease_id": lease_id})
        enabled: bool | None = result.scalar_one_or_none()
        return enabled

    async def current(self, lease_id: UUID) -> TenantLink | None:
        row = (await self._connection.execute(CURRENT, {"lease_id": lease_id})).first()
        if row is None:
            return None
        return TenantLink(
            row.id, row.lease_id, bytes(row.nonce), row.key_id, row.created_at, row.last_used_at
        )

    async def add(self, account_id: UUID, link: TenantLink, hashed_token: bytes) -> None:
        await self._connection.execute(
            ADD,
            {
                "id": link.id,
                "account_id": account_id,
                "lease_id": link.lease_id,
                "nonce": link.nonce,
                "key_id": link.key_id,
                "token_hash": hashed_token,
                "created_at": link.created_at,
            },
        )

    async def revoke(self, link_id: UUID, at: datetime) -> None:
        await self._connection.execute(REVOKE, {"id": link_id, "at": at})


class HmacLinkSigner:
    def __init__(self, keyring: HmacKeyring) -> None:
        self._keyring = keyring

    def new_secret(self) -> tuple[bytes, str]:
        return os.urandom(NONCE_BYTES), self._keyring.active_key_id

    def token(self, link: TenantLink) -> str:
        return encode_token(self._keyring.sign(link.key_id, signed_message(link.id, link.nonce)))
