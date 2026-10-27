from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.domain.profile import Profile, TaxpayerKind, is_valid_ruc, ruc_group
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.ids import new_id


class Profiles(Protocol):
    async def current(self) -> Profile: ...

    async def lock_current(self) -> Profile: ...

    async def save(self, account_id: UUID, profile: Profile) -> None: ...


@dataclass(frozen=True)
class GetProfile:
    profiles: Profiles

    async def __call__(self) -> Profile:
        return await self.profiles.current()


@dataclass(frozen=True)
class ProfileChange:
    display_name: str
    taxpayer_kind: TaxpayerKind
    ruc: str | None
    good_taxpayer: bool
    daily_digest: bool


@dataclass(frozen=True)
class UpdateProfile:
    profiles: Profiles
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, change: ProfileChange
    ) -> Profile | Literal["invalid_ruc"]:
        if change.ruc is not None and not is_valid_ruc(change.ruc):
            return "invalid_ruc"
        updated = Profile(
            display_name=change.display_name,
            taxpayer_kind=change.taxpayer_kind,
            ruc=change.ruc,
            ruc_group=None if change.ruc is None else ruc_group(change.ruc, change.good_taxpayer),
            daily_digest=change.daily_digest,
        )
        previous = await self.profiles.lock_current()
        changed = previous.changed_fields(updated)
        if changed:
            await self.profiles.save(context.account_id, updated)
            await self.audit.record(
                AuditEntry(
                    id=new_id(),
                    account_id=context.account_id,
                    actor_user_id=context.user_id,
                    action="account.profile_updated",
                    entity="accounts",
                    entity_id=context.account_id,
                    changed_fields=tuple(changed),
                    at=self.clock.now(),
                )
            )
        return updated
