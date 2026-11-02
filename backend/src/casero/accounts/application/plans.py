from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PlanOffer:
    code: str
    name: str
    price_month_cents: int
    price_year_cents: int
    max_active_leases: int


class PlanOffers(Protocol):
    async def offers(self) -> list[PlanOffer]: ...
