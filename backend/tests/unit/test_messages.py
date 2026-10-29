from datetime import date

from casero.reminders.domain.messages import (
    DEFAULT_BODIES,
    day_label,
    period_label,
    render,
    unknown_variables,
    uses_link,
    whatsapp_url,
)
from casero.shared.kernel.periods import Period


def test_the_message_fills_each_variable_and_leaves_other_braces_alone() -> None:
    message = render(
        DEFAULT_BODIES["overdue"] + " {otra}",
        {
            "inquilino": "Ana",
            "monto": "S/ 800.00",
            "periodo": "octubre de 2026",
            "fecha": "05/10/2026",
            "enlace": "https://casero.example/i#t=abc",
        },
    )

    assert message == (
        "Hola Ana, el alquiler de octubre de 2026 por S/ 800.00 está pendiente desde el"
        " 05/10/2026. ¿Me confirmas cuándo podrías pagarlo?"
        " Tu detalle: https://casero.example/i#t=abc. {otra}"
    )


def test_only_the_five_variables_are_allowed() -> None:
    assert [unknown_variables(body) for body in DEFAULT_BODIES.values()] == [[], [], []]
    assert unknown_variables("Hola {nombre}, paga {monto} {}") == ["nombre", ""]
    assert all(uses_link(body) for body in DEFAULT_BODIES.values())
    assert not uses_link("Hola {inquilino}")


def test_the_link_opens_whatsapp_with_the_number_without_plus_and_the_text_encoded() -> None:
    text = "Hola, ¿pagas hoy? S/ 800 & gracias #1"

    assert whatsapp_url("+51987654321", text) == (
        "https://wa.me/51987654321?text=Hola%2C%20%C2%BFpagas%20hoy%3F%20S%2F%20800"
        "%20%26%20gracias%20%231"
    )
    assert whatsapp_url(None, "Hola").startswith("https://wa.me/?text=")


def test_months_read_as_in_peru_and_days_as_dd_mm_yyyy() -> None:
    assert period_label(Period(2026, 9)) == "setiembre de 2026"
    assert period_label(Period(2027, 1)) == "enero de 2027"
    assert day_label(date(2026, 10, 5)) == "05/10/2026"
