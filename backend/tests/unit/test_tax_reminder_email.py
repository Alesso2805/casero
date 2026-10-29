from datetime import date

import pytest

from casero.reminders.domain.tax_reminders import (
    DueMonth,
    OwedDeclaration,
    reminder_due,
    tax_reminder_email,
)
from casero.shared.kernel.periods import Period

MONTH = DueMonth(
    Period(2026, 10),
    date(2026, 11, 19),
    [OwedDeclaration("Ana Quispe", 2_800, False), OwedDeclaration("Rosa Huamán", 1_500, True)],
)


def email_on(today: date) -> tuple[str, str, str | None]:
    email = tax_reminder_email(
        "casera@example.com",
        "Casera",
        MONTH,
        today,
        "https://casero.example/",
        "https://casero.example/baja?u=1",
        "https://casero.example/api/public/unsubscribe?u=1",
    )
    return email.subject, email.text, email.unsubscribe_url


def test_five_days_before_it_lists_what_is_owed_and_asks_for_a_missing_document() -> None:
    subject, text, one_click = email_on(date(2026, 11, 14))

    assert subject == "Tus formularios 1683 de octubre de 2026 vencen el 19/11/2026"
    assert text == "\n".join(
        [
            "Hola, Casera:",
            "",
            "El 19/11/2026 vence el pago de tus formularios 1683 de octubre de 2026."
            " Esto es lo que falta pagar:",
            "",
            "- Ana Quispe: S/ 28.00",
            "- Rosa Huamán: S/ 15.00. Falta su documento: complétalo en Casero para poder"
            " presentarlo.",
            "",
            "Total: S/ 43.00",
            "",
            "Tienes los datos listos para copiar en https://casero.example/app/impuestos.",
            "",
            "Casero no presenta ni paga por ti, y nunca te pide tu Clave SOL.",
            "",
            "Para no recibir más estos recordatorios: https://casero.example/baja?u=1",
        ]
    )
    assert one_click == "https://casero.example/api/public/unsubscribe?u=1"


def test_the_day_before_it_says_tomorrow() -> None:
    subject, text, _ = email_on(date(2026, 11, 18))

    assert subject == "Mañana vencen tus formularios 1683 de octubre de 2026"
    assert "Mañana vence el pago de tus formularios 1683 de octubre de 2026." in text


@pytest.mark.parametrize(
    ("days_left", "first_sent", "due"),
    [
        (6, False, False),
        (5, False, True),
        (4, False, True),
        (2, False, True),
        (4, True, False),
        (2, True, False),
        (1, True, True),
        (1, False, True),
        (0, False, False),
    ],
)
def test_the_first_reminder_catches_up_until_two_days_before_and_the_last_is_the_day_before(
    days_left: int, first_sent: bool, due: bool
) -> None:
    assert reminder_due(days_left, first_sent) == due
