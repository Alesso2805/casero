from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id
from casero.tenant_portal.domain.links import link_url, token_hash


@dataclass(frozen=True)
class TenantLink:
    id: UUID
    lease_id: UUID
    nonce: bytes
    key_id: str
    created_at: datetime
    last_used_at: datetime | None


class LinkStore(Protocol):
    async def portal_enabled(self, lease_id: UUID, lock: bool) -> bool | None:
        """None when the lease does not exist; False when it lost the portal to the plan."""
        ...

    async def current(self, lease_id: UUID) -> TenantLink | None: ...

    async def add(self, account_id: UUID, link: TenantLink, hashed_token: bytes) -> None: ...

    async def revoke(self, link_id: UUID, at: datetime) -> None: ...


class LinkSigner(Protocol):
    """Signs with the server's HMAC keys; the active key signs new links (CLAUDE.md, rule 10)."""

    def new_secret(self) -> tuple[bytes, str]:
        """A random nonce and the id of the key that signs it."""
        ...

    def token(self, link: TenantLink) -> str: ...

    def knows(self, key_id: str) -> bool:
        """False once the key that signed a link was retired (an incident rotation)."""
        ...


@dataclass(frozen=True)
class LinkView:
    url: str
    created_at: datetime
    last_used_at: datetime | None


@dataclass(frozen=True)
class Links:
    store: LinkStore
    signer: LinkSigner
    public_url: str

    def view(self, link: TenantLink) -> LinkView:
        return LinkView(
            link_url(self.public_url, self.signer.token(link)), link.created_at, link.last_used_at
        )


LinkRefusal = Literal["lease_not_found", "portal_unavailable"]


@dataclass(frozen=True)
class GetLink:
    links: Links

    async def __call__(self, lease_id: UUID) -> LinkView | Literal["lease_not_found"] | None:
        if await self.links.store.portal_enabled(lease_id, lock=False) is None:
            return "lease_not_found"
        current = await self.links.store.current(lease_id)
        if current is None or not self.links.signer.knows(current.key_id):
            return None
        return self.links.view(current)


@dataclass(frozen=True)
class IssueLink:
    """Creates the lease's link, or replaces it: the previous one stops working."""

    links: Links
    entitlements: GetEntitlements
    audit: AuditLog
    clock: Clock

    async def __call__(self, context: AccountContext, lease_id: UUID) -> LinkView | LinkRefusal:
        enabled = await self.links.store.portal_enabled(lease_id, lock=True)
        if enabled is None:
            return "lease_not_found"
        if not enabled or not (await self.entitlements()).allows("tenant_portal"):
            return "portal_unavailable"
        now = self.clock.now()
        current = await self.links.store.current(lease_id)
        if current is not None:
            await self.links.store.revoke(current.id, now)
        nonce, key_id = self.links.signer.new_secret()
        link = TenantLink(new_id(), lease_id, nonce, key_id, now, None)
        hashed = token_hash(self.links.signer.token(link))
        await self.links.store.add(context.account_id, link, hashed)
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "tenant_link.issued",
                "tenant_links",
                link.id,
                ["nonce", "key_id", "token_hash"],
                now,
            )
        )
        return self.links.view(link)


@dataclass(frozen=True)
class LinkInUse:
    """`{enlace}` for the collection messages: the link in use, or a new one (AR-03)."""

    links: Links
    issue: IssueLink

    async def url_for(self, context: AccountContext, lease_id: UUID) -> str | None:
        # Locking first keeps two messages prepared at once from replacing each other's link.
        if not await self.links.store.portal_enabled(lease_id, lock=True):
            return None
        current = await self.links.store.current(lease_id)
        if current is not None and self.links.signer.knows(current.key_id):
            return self.links.view(current).url
        issued = await self.issue(context, lease_id)
        return None if isinstance(issued, str) else issued.url


@dataclass(frozen=True)
class RevokeLink:
    """Revoking is idempotent: without a link in use there is nothing to do."""

    store: LinkStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, lease_id: UUID
    ) -> Literal["lease_not_found"] | None:
        if await self.store.portal_enabled(lease_id, lock=True) is None:
            return "lease_not_found"
        current = await self.store.current(lease_id)
        if current is None:
            return None
        now = self.clock.now()
        await self.store.revoke(current.id, now)
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "tenant_link.revoked",
                "tenant_links",
                current.id,
                ["revoked_at"],
                now,
            )
        )
        return None
