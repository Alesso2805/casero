from datetime import UTC, date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today_lima(self) -> date: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today_lima(self) -> date:
        return self.now().astimezone(LIMA).date()
