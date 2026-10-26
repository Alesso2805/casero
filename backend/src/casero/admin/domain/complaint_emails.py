from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from casero.admin.domain.complaints import (
    Complaint,
    ComplaintKind,
    DocumentType,
    ItemKind,
    ResponseChannel,
)
from casero.shared.kernel.clock import LIMA
from casero.shared.kernel.email import Email
from casero.shared.kernel.money import format_soles

KIND_LABELS: dict[ComplaintKind, str] = {"claim": "Reclamo", "complaint": "Queja"}
KIND_NOUNS: dict[ComplaintKind, str] = {"claim": "reclamo", "complaint": "queja"}
DOCUMENT_LABELS: dict[DocumentType, str] = {"dni": "DNI", "ce": "CE", "passport": "Pasaporte"}
ITEM_LABELS: dict[ItemKind, str] = {"product": "Producto", "service": "Servicio"}
CHANNEL_LABELS: dict[ResponseChannel, str] = {
    "email": "correo electrónico",
    "letter": "carta al domicilio indicado",
}
EMPTY = "—"

# Definitions and notices that Anexo I (D.S. N.° 101-2022-PCM) requires on the sheet.
DEFINITIONS = (
    "RECLAMO: Disconformidad relacionada a los productos o servicios.",
    "QUEJA: Disconformidad no relacionada a los productos o servicios; o, malestar o"
    " descontento respecto a la atención al público.",
)
NOTICES = (
    "La formulación del reclamo no impide acudir a otras vías de solución de controversias"
    " ni es requisito previo para interponer una denuncia ante el INDECOPI.",
    "El proveedor debe dar respuesta al reclamo o queja en un plazo no mayor a quince (15)"
    " días hábiles, el cual es improrrogable.",
)


CopyState = Literal["sent", "failed", "unfinished", "no_email"]


@dataclass(frozen=True)
class CopyStatus:
    state: CopyState
    error_code: str | None = None


COPY_STATUS_LINES: dict[CopyState, str] = {
    "sent": "Copia al consumidor: enviada.",
    "failed": "Copia al consumidor: no se pudo enviar ({error_code})."
    " Envíala tú desde este correo.",
    "unfinished": "Copia al consumidor: el envío no terminó. Revisa docs/ops/complaints.md y,"
    " si no llegó, envíala tú desde este correo.",
    "no_email": "Copia al consumidor: no dejó correo; responde por carta.",
}


@dataclass(frozen=True)
class BusinessIdentity:
    name: str
    ruc: str
    address: str
    complaints_inbox: str


def lima_timestamp(moment: datetime) -> str:
    return moment.astimezone(LIMA).strftime("%d/%m/%Y %H:%M")


def day(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def or_empty(value: str | None) -> str:
    return value or EMPTY


def sheet_lines(complaint: Complaint, business: BusinessIdentity) -> list[str]:
    sheet = complaint.sheet
    lines = [
        "LIBRO DE RECLAMACIONES",
        f"HOJA DE RECLAMACIÓN N.° {complaint.number}",
        f"Fecha y hora de presentación: {lima_timestamp(complaint.created_at)} (hora de Lima)",
        f"Proveedor: {business.name}, RUC {business.ruc}",
        f"Domicilio del proveedor: {business.address}",
        "",
        "1. Identificación del consumidor reclamante",
        f"Nombre: {sheet.full_name}",
        f"{DOCUMENT_LABELS[sheet.document_type]}: {sheet.document_number}",
        f"Domicilio: {or_empty(sheet.address)}",
        f"Teléfono: {or_empty(sheet.phone)}",
        f"Correo electrónico: {or_empty(sheet.email)}",
    ]
    if sheet.guardian:
        guardian = sheet.guardian
        lines += [
            f"Padre, madre o representante: {guardian.full_name}",
            f"Su domicilio: {or_empty(guardian.address)}",
            f"Su teléfono: {or_empty(guardian.phone)}",
            f"Su correo electrónico: {or_empty(guardian.email)}",
        ]
    amount = sheet.claimed_amount_cents
    lines += [
        "",
        "2. Identificación del bien contratado",
        f"Tipo: {ITEM_LABELS[sheet.item_kind]}",
        f"Monto reclamado: {format_soles(amount) if amount is not None else EMPTY}",
        f"Descripción: {or_empty(sheet.item_description)}",
        "",
        "3. Detalle de la reclamación y pedido del consumidor",
        f"Tipo: {KIND_LABELS[sheet.kind]}",
        f"Detalle: {sheet.detail}",
        f"Pedido: {or_empty(sheet.request)}",
        "",
        f"Respuesta por: {CHANNEL_LABELS[sheet.response_channel]}",
        "",
        *DEFINITIONS,
        "",
        *NOTICES,
    ]
    return lines


def consumer_copy(complaint: Complaint, business: BusinessIdentity) -> Email:
    sheet = complaint.sheet
    if sheet.email is None:
        raise ValueError("A complaint copy needs the consumer's email")
    noun = KIND_NOUNS[sheet.kind]
    intro = [
        f"Hola, {sheet.full_name}:",
        "",
        f"Recibimos tu {noun} en el Libro de Reclamaciones de Casero. Esta es la copia de tu"
        " Hoja de Reclamación. Te responderemos por"
        f" {CHANNEL_LABELS[sheet.response_channel]} a más tardar el {day(complaint.due_on)}.",
        "",
    ]
    return Email(
        to=sheet.email,
        subject=f"Copia de tu {noun} N.° {complaint.number}",
        text="\n".join(intro + sheet_lines(complaint, business)) + "\n",
        reply_to=business.complaints_inbox,
    )


def inbox_notice(complaint: Complaint, business: BusinessIdentity, copy: CopyStatus) -> Email:
    sheet = complaint.sheet
    article = "un reclamo" if sheet.kind == "claim" else "una queja"
    lines = [
        f"Llegó {article} al Libro de Reclamaciones.",
        "",
        f"Número: {complaint.number}",
        f"Presentado: {lima_timestamp(complaint.created_at)} (hora de Lima)",
        f"Responder a más tardar el: {day(complaint.due_on)}",
        f"Respuesta por: {CHANNEL_LABELS[sheet.response_channel]}",
        COPY_STATUS_LINES[copy.state].format(error_code=copy.error_code),
        "",
        "El detalle está en la tabla complaints. Cómo leerlo y responderlo:"
        " docs/ops/complaints.md.",
    ]
    return Email(
        to=business.complaints_inbox,
        subject=f"{KIND_LABELS[sheet.kind]} N.° {complaint.number}: responder antes del"
        f" {day(complaint.due_on)}",
        text="\n".join(lines) + "\n",
    )
