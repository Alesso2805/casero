from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

import structlog

from casero.shared.kernel.clock import Clock
from casero.shared.kernel.email import Email

STUCK_AFTER = timedelta(minutes=10)
FAILURE_WINDOW = timedelta(days=1)
MONTHS = 12
RUC_GROUPS = 7
# From November the next year's SUNAT schedule should already be loaded (SPEC, CS-26).
NEXT_YEAR_FROM_MONTH = 11

log = structlog.get_logger()


@dataclass(frozen=True)
class Alert:
    key: str
    event: str
    subject: str
    text: str
    tags: dict[str, str] = field(default_factory=dict)


class OpsReadings(Protocol):
    async def stuck_email_runs(self, started_before: datetime) -> list[tuple[str, str]]:
        """Complaint email runs still `running`, as (job, run_key)."""
        ...

    async def schedule_rows(self, year: int) -> int: ...

    async def failed_runs_since(self, since: datetime) -> dict[str, int]: ...


class AlertLog(Protocol):
    async def claim(self, key: str, now: datetime) -> bool:
        """True only the first time, so each alert goes out once."""
        ...


class AlertMailer(Protocol):
    async def send(self, email: Email) -> None: ...


def schedule_years(today: date) -> list[int]:
    if today.month >= NEXT_YEAR_FROM_MONTH:
        return [today.year, today.year + 1]
    return [today.year]


@dataclass(frozen=True)
class RaiseAlerts:
    """Tells the owner what needs a hand: by error log (Sentry) and by email if configured.

    Alerts carry job names, years and counts, never personal data (rule 8).
    """

    readings: OpsReadings
    alerts: AlertLog
    mailer: AlertMailer
    inbox: str | None
    clock: Clock

    async def __call__(self) -> None:
        for alert in await self._pending():
            if not await self.alerts.claim(alert.key, self.clock.now()):
                continue
            log.error(alert.event, **alert.tags)
            if self.inbox:
                await self.mailer.send(Email(self.inbox, alert.subject, alert.text))

    async def _pending(self) -> list[Alert]:
        now, today = self.clock.now(), self.clock.today_lima()
        pending = [
            Alert(
                key=f"stuck:{job}:{run_key}",
                event="complaint_email.stuck",
                subject="Casero: un correo de reclamo sigue sin enviarse",
                text=(
                    f"La tarea {job} lleva más de 10 minutos en curso. Revisa el worker y, si "
                    "hace falta, reenvía la copia con make complaint-copy (docs/ops/complaints.md)."
                ),
                tags={"job": job},
            )
            for job, run_key in await self.readings.stuck_email_runs(now - STUCK_AFTER)
        ]
        for year in schedule_years(today):
            if await self.readings.schedule_rows(year) < MONTHS * RUC_GROUPS:
                pending.append(
                    Alert(
                        key=f"schedule:{today}:{year}",
                        event="tax.schedule_missing",
                        subject=f"Casero: falta el cronograma de SUNAT de {year}",
                        text=(
                            f"El cronograma de vencimientos de {year} no está completo. Agrega "
                            "el YAML del año y cárgalo con make load-tax-config "
                            "(docs/ops/tax-config.md)."
                        ),
                        tags={"year": str(year)},
                    )
                )
        failed = await self.readings.failed_runs_since(now - FAILURE_WINDOW)
        if failed:
            summary = ", ".join(f"{job} ({count})" for job, count in sorted(failed.items()))
            pending.append(
                Alert(
                    key=f"failed:{today}",
                    event="worker.jobs_failed",
                    subject="Casero: tareas fallidas en las últimas 24 horas",
                    text=f"Tareas con fallas: {summary}. Los detalles están en Sentry.",
                    tags={"jobs": ",".join(sorted(failed))},
                )
            )
        return pending
