from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.entitlements import GetEntitlements
from casero.ledger.application.payments import GetStatement, Statement
from casero.shared.kernel.clock import Clock
from casero.tenant_portal.domain.links import token_hash, well_formed


@dataclass(frozen=True)
class TenantLease:
    account_id: UUID
    lease_id: UUID


class TenantGate(Protocol):
    async def resolve(self, hashed_token: bytes, today: date) -> TenantLease | None:
        """A link in use, of an account not being deleted, up to 90 days after the lease ends."""
        ...

    async def enter(self, lease: TenantLease) -> None:
        """Scopes every following read to the tenant's lease (rule 3, AR-16)."""
        ...

    async def portal_enabled(self, lease_id: UUID) -> bool: ...

    async def touch(self, lease_id: UUID, at: datetime) -> None: ...


PortalRefusal = Literal["link_not_found", "portal_unavailable"]


@dataclass(frozen=True)
class OpenPortal:
    """Who the token belongs to; an unknown token and an expired one look the same."""

    gate: TenantGate
    entitlements: GetEntitlements
    clock: Clock

    async def __call__(self, token: str) -> TenantLease | PortalRefusal:
        if not well_formed(token):
            return "link_not_found"
        lease = await self.gate.resolve(token_hash(token), self.clock.today_lima())
        if lease is None:
            return "link_not_found"
        await self.gate.enter(lease)
        enabled = await self.gate.portal_enabled(lease.lease_id)
        if not enabled or not (await self.entitlements()).allows("tenant_portal"):
            return "portal_unavailable"
        await self.gate.touch(lease.lease_id, self.clock.now())
        return lease


@dataclass(frozen=True)
class PortalHeader:
    landlord_name: str
    renter_name: str
    unit: str


class PortalReader(Protocol):
    async def header(self, lease_id: UUID) -> PortalHeader | None: ...


@dataclass(frozen=True)
class TenantStatement:
    header: PortalHeader
    statement: Statement


@dataclass(frozen=True)
class GetTenantStatement:
    """What the tenant sees: who rents, what is owed and paid; never the landlord's RUC,
    email or notes (CS-18)."""

    reader: PortalReader
    statements: GetStatement

    async def __call__(self, lease: TenantLease) -> TenantStatement | None:
        header = await self.reader.header(lease.lease_id)
        statement = await self.statements(lease.lease_id)
        if header is None or statement is None:
            return None
        return TenantStatement(header, statement)
