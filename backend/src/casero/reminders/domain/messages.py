import re
from collections.abc import Mapping
from typing import Literal
from urllib.parse import quote

TemplateKind = Literal["friendly", "due_today", "overdue"]
TEMPLATE_KINDS: tuple[TemplateKind, ...] = ("friendly", "due_today", "overdue")
VARIABLES = ("inquilino", "monto", "periodo", "fecha", "enlace")
MAX_BODY_LENGTH = 1000

DEFAULT_BODIES: dict[TemplateKind, str] = {
    "friendly": (
        "Hola {inquilino}, te recuerdo que el {fecha} vence el alquiler de {periodo} por"
        " {monto}. Puedes ver tu detalle aquí: {enlace}. ¡Gracias!"
    ),
    "due_today": (
        "Hola {inquilino}, hoy vence el alquiler de {periodo} por {monto}."
        " Tu detalle está aquí: {enlace}."
    ),
    "overdue": (
        "Hola {inquilino}, el alquiler de {periodo} por {monto} está pendiente desde el"
        " {fecha}. ¿Me confirmas cuándo podrías pagarlo? Tu detalle: {enlace}."
    ),
}

PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


def unknown_variables(body: str) -> list[str]:
    return [name for name in PLACEHOLDER.findall(body) if name not in VARIABLES]


def uses_link(body: str) -> bool:
    return "{enlace}" in body


def render(body: str, values: Mapping[str, str]) -> str:
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), body)


def whatsapp_url(phone_e164: str | None, message: str) -> str:
    """A `https://wa.me/` link the landlord opens on their phone (CLAUDE.md, rule 9).

    Without a number, WhatsApp asks which chat to send it to.
    """
    number = phone_e164.removeprefix("+") if phone_e164 else ""
    return f"https://wa.me/{number}?text={quote(message, safe='')}"
