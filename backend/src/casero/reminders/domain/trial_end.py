from dataclasses import dataclass
from datetime import date, timedelta

from casero.reminders.domain.messages import day_label, period_label
from casero.shared.kernel.email import Email
from casero.shared.kernel.money import format_soles
from casero.shared.kernel.periods import Period


@dataclass(frozen=True)
class PendingDue:
    period: Period
    due_on: date
    pending_cents: int


def trial_ended_email(
    to: str,
    display_name: str,
    ended_on: date,
    free_from: date,
    pending: list[PendingDue],
    app_url: str,
) -> Email:
    """SPEC's single notice when the trial ends, with what's still to pay to SUNAT."""
    lines = [
        f"Hola, {display_name}:",
        "",
        f"Tu prueba gratis de Casero terminó el {day_label(ended_on)}. Puedes seguir usando todo"
        f" hasta el {day_label(free_from - timedelta(days=1))}. Después tu cuenta pasa al plan"
        " Gratis, sin los Formularios de SUNAT ni sus recordatorios. Tus datos no se borran.",
    ]
    if pending:
        lines += [
            "",
            "Todavía tienes formularios 1683 por pagar:",
            "",
            *(
                f"- {period_label(due.period)}: {format_soles(due.pending_cents)},"
                f" vencen el {day_label(due.due_on)}"
                for due in pending
            ),
            "",
            "Estos pagos a SUNAT siguen siendo tuyos aunque cambies de plan.",
        ]
    lines += ["", f"Para seguir con el plan Casero: {app_url.rstrip('/')}/app/plan"]
    return Email(to, "Terminó tu prueba de Casero", "\n".join(lines))
