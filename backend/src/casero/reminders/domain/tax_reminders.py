from dataclasses import dataclass
from datetime import date

from casero.reminders.domain.messages import day_label, period_label
from casero.shared.kernel.email import Email
from casero.shared.kernel.money import format_soles
from casero.shared.kernel.periods import Period

REMINDER_DAYS_BEFORE = (5, 1)


@dataclass(frozen=True)
class OwedDeclaration:
    renter_name: str
    pending_cents: int
    missing_document: bool


@dataclass(frozen=True)
class DueMonth:
    period: Period
    due_on: date
    owed: list[OwedDeclaration]


def owed_line(owed: OwedDeclaration) -> str:
    line = f"- {owed.renter_name}: {format_soles(owed.pending_cents)}"
    if owed.missing_document:
        line += ". Falta su documento: complétalo en Casero para poder presentarlo."
    return line


def tax_reminder_email(
    to: str,
    display_name: str,
    month: DueMonth,
    today: date,
    app_url: str,
    unsubscribe_page: str,
    unsubscribe_one_click: str,
) -> Email:
    """SPEC's tax reminder, 5 days and 1 day before the due date, with one-click unsubscribe."""
    period = period_label(month.period)
    tomorrow = (month.due_on - today).days == 1
    when = "Mañana" if tomorrow else f"El {day_label(month.due_on)}"
    subject = (
        f"Mañana vencen tus formularios 1683 de {period}"
        if tomorrow
        else f"Tus formularios 1683 de {period} vencen el {day_label(month.due_on)}"
    )
    lines = [
        f"Hola, {display_name}:",
        "",
        f"{when} vence el pago de tus formularios 1683 de {period}. Esto es lo que falta pagar:",
        "",
        *(owed_line(owed) for owed in month.owed),
        "",
        f"Total: {format_soles(sum(owed.pending_cents for owed in month.owed))}",
        "",
        f"Tienes los datos listos para copiar en {app_url.rstrip('/')}/app/impuestos.",
        "",
        "Casero no presenta ni paga por ti, y nunca te pide tu Clave SOL.",
        "",
        f"Para no recibir más estos recordatorios: {unsubscribe_page}",
    ]
    return Email(to, subject, "\n".join(lines), unsubscribe_url=unsubscribe_one_click)
