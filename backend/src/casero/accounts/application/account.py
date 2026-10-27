from dataclasses import dataclass
from typing import Protocol

from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.domain.entitlements import Entitlements


class AccountNames(Protocol):
    async def display_name(self) -> str: ...


@dataclass(frozen=True)
class AccountSummary:
    display_name: str
    entitlements: Entitlements


@dataclass(frozen=True)
class GetAccountSummary:
    names: AccountNames
    entitlements: GetEntitlements

    async def __call__(self) -> AccountSummary:
        return AccountSummary(await self.names.display_name(), await self.entitlements())
