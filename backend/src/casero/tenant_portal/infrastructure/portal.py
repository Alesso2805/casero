from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.database import set_tenant_context
from casero.tenant_portal.application.portal import PortalHeader, TenantLease

RESOLVE = text("SELECT account_id, lease_id FROM app_resolve_tenant_token(:hash, :today)")
PORTAL_ENABLED = text("SELECT tools_enabled FROM leases WHERE id = :lease_id")
TOUCH = text(
    "UPDATE tenant_links SET last_used_at = :at WHERE lease_id = :lease_id AND revoked_at IS NULL"
)
HEADER = text(
    "SELECT a.display_name, r.full_name, u.name AS unit, p.name AS property FROM leases l"
    " JOIN accounts a ON a.id = l.account_id"
    " JOIN renters r ON r.account_id = l.account_id AND r.id = l.renter_id"
    " JOIN units u ON u.account_id = l.account_id AND u.id = l.unit_id"
    " JOIN properties p ON p.account_id = u.account_id AND p.id = u.property_id"
    " WHERE l.id = :lease_id"
)


class SqlTenantGate:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def resolve(self, hashed_token: bytes, today: date) -> TenantLease | None:
        row = (
            await self._connection.execute(RESOLVE, {"hash": hashed_token, "today": today})
        ).first()
        return None if row is None else TenantLease(row.account_id, row.lease_id)

    async def enter(self, lease: TenantLease) -> None:
        await set_tenant_context(self._connection, lease.account_id, lease.lease_id)

    async def portal_enabled(self, lease_id: UUID) -> bool:
        result = await self._connection.execute(PORTAL_ENABLED, {"lease_id": lease_id})
        return bool(result.scalar_one_or_none())

    async def touch(self, lease_id: UUID, at: datetime) -> None:
        await self._connection.execute(TOUCH, {"lease_id": lease_id, "at": at})


class SqlPortalReader:
    """Reads in the tenant context: RLS shows only the tenant's lease and what it needs."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def header(self, lease_id: UUID) -> PortalHeader | None:
        row = (await self._connection.execute(HEADER, {"lease_id": lease_id})).first()
        if row is None:
            return None
        return PortalHeader(row.display_name, row.full_name, f"{row.unit} · {row.property}")
