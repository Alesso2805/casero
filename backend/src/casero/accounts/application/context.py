from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class AccountContext:
    account_id: UUID
    user_id: UUID


class Memberships(Protocol):
    async def account_of(self, user_id: UUID) -> UUID | None: ...


class AccountScope(Protocol):
    async def enter(self, account_id: UUID) -> None: ...


@dataclass(frozen=True)
class OpenAccount:
    """Scopes the transaction to the user's account; RLS does the rest (rule 3)."""

    memberships: Memberships
    scope: AccountScope

    async def __call__(self, user_id: UUID) -> AccountContext | None:
        account_id = await self.memberships.account_of(user_id)
        if account_id is None:
            return None
        await self.scope.enter(account_id)
        return AccountContext(account_id, user_id)
