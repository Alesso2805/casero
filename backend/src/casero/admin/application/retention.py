from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog

from casero.shared.kernel.clock import Clock

WAITLIST_YEARS = 1
# The minimum of the Reglamento del Libro de Reclamaciones, art. 12 (SPEC, "Retención de datos").
COMPLAINT_YEARS = 2

log = structlog.get_logger()


def years_before(moment: datetime, years: int) -> datetime:
    try:
        return moment.replace(year=moment.year - years)
    except ValueError:
        return moment.replace(year=moment.year - years, day=28)


class RetentionStore(Protocol):
    async def forget_waitlist_before(self, cutoff: datetime) -> int: ...

    async def forget_complaints_before(self, cutoff: datetime) -> int: ...


@dataclass(frozen=True)
class ForgetExpiredData:
    """Deletes what SPEC keeps only for a while; the log has counts, never who (rule 8)."""

    store: RetentionStore
    clock: Clock

    async def __call__(self) -> None:
        now = self.clock.now()
        waitlist = await self.store.forget_waitlist_before(years_before(now, WAITLIST_YEARS))
        complaints = await self.store.forget_complaints_before(years_before(now, COMPLAINT_YEARS))
        if waitlist or complaints:
            log.info("retention.deleted", waitlist=waitlist, complaints=complaints)
