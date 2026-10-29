import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from casero.accounts.application.entitlements import GetEntitlements
from casero.leases.application.leases import LeaseStore
from casero.leases.application.renters import RenterDocuments
from casero.ledger.application.collected import received_payments
from casero.ledger.application.payments import LedgerStore
from casero.properties.application.properties import PropertyStore
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.money import CENTS_PER_SOL
from casero.shared.kernel.periods import Period
from casero.tax.application.declarations import TAXED, GetDeclarations

# A spreadsheet runs a cell that starts with one of these as a formula (CSV injection).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
# Excel needs the BOM to read the file as UTF-8, or the accents break.
UTF8_BOM = "﻿"

METHOD_NAMES = {
    "cash": "Efectivo",
    "yape": "Yape",
    "plin": "Plin",
    "transfer": "Transferencia",
    "bank_deposit": "Depósito en banco",
    "guarantee": "Garantía",
}
DOC_TYPE_NAMES = {"dni": "DNI", "ce": "Carné de extranjería", "passport": "Pasaporte", "ruc": "RUC"}

PAYMENT_COLUMNS = (
    "Fecha de cobro",
    "Inquilino",
    "Tipo de documento",
    "Número de documento",
    "Unidad",
    "Medio",
    "Monto",
    "Deuda de 2025 o antes",
    "Monto gravado",
    "Entra al 1683",
    "Nota",
)
DECLARATION_COLUMNS = (
    "Período",
    "Inquilino",
    "Tipo de documento",
    "Número de documento",
    "Base",
    "Tributo",
    "Pagado",
    "Pendiente",
    "Vencimiento",
    "Números de orden",
    "Falta el documento",
)

Unavailable = Literal["accountant_export_unavailable"]


def spreadsheet_cell(value: str) -> str:
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def csv_text(columns: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows([spreadsheet_cell(value) for value in row] for row in rows)
    return UTF8_BOM + buffer.getvalue()


def soles(cents: int) -> str:
    return f"{cents // CENTS_PER_SOL}.{cents % CENTS_PER_SOL:02d}"


def day(value: date) -> str:
    return value.strftime("%d/%m/%Y")


@dataclass(frozen=True)
class ExportPayments:
    """Every valid payment collected in a year, for the landlord's accountant (SPEC)."""

    entitlements: GetEntitlements
    leases: LeaseStore
    renters: RenterDocuments
    properties: PropertyStore
    ledger: LedgerStore

    async def __call__(self, year: int) -> str | Unavailable:
        if not (await self.entitlements()).allows("accountant_export"):
            return "accountant_export_unavailable"
        documents = {doc.renter_id: doc for doc in await self.renters.documents()}
        units = {
            unit.id: f"{unit.details.name} · {p.details.name}"
            for p in await self.properties.all()
            for unit in p.units
        }
        rows = []
        for lease in await self.leases.all(Period(year, 1)):
            ledger = await self.ledger.lease_ledger(lease.id)
            if ledger is None:
                continue
            renter = documents[lease.terms.renter_id]
            for received in received_payments(ledger):
                payment = received.record.payment
                if payment.received_on.year != year:
                    continue
                taxed = lease.terms.tax_treatment in TAXED
                sort_key = (payment.received_on, payment.created_at)
                row = (
                    day(payment.received_on),
                    renter.full_name,
                    DOC_TYPE_NAMES[renter.doc_type] if renter.doc_type else "",
                    renter.number or "",
                    units.get(lease.terms.unit_id, ""),
                    METHOD_NAMES.get(received.record.method, received.record.method),
                    soles(payment.amount_cents),
                    soles(received.old_debt_cents),
                    soles(payment.amount_cents - received.old_debt_cents) if taxed else "",
                    "Sí" if taxed else "No",
                    received.record.note or "",
                )
                rows.append((sort_key, row))
        return csv_text(PAYMENT_COLUMNS, [row for _, row in sorted(rows, key=lambda r: r[0])])


@dataclass(frozen=True)
class ExportDeclarations:
    """Each month's 1683 declarations of a year up to the current month, with what was paid."""

    entitlements: GetEntitlements
    declarations: GetDeclarations
    clock: Clock

    async def __call__(self, year: int) -> str | Unavailable:
        if not (await self.entitlements()).allows("accountant_export"):
            return "accountant_export_unavailable"
        current = Period.of(self.clock.today_lima())
        rows = []
        period = Period(year, 1)
        while period <= current and period.year == year:
            month = await self.declarations(period)
            if month == "tax_module_unavailable":
                return "accountant_export_unavailable"
            if month == "unknown_year":
                break
            for card in month.cards:
                rows.append(
                    (
                        str(period),
                        card.renter_name,
                        DOC_TYPE_NAMES[card.doc_type] if card.doc_type else "",
                        card.doc_number or "",
                        soles(card.declaration.base_cents),
                        soles(card.declaration.tax_cents),
                        soles(card.paid_cents),
                        soles(card.pending_cents),
                        day(month.due_on) if month.due_on else "",
                        " ".join(payment.order_number for payment in card.payments),
                        "Sí" if card.declaration.incomplete else "No",
                    )
                )
            period = period.next()
        return csv_text(DECLARATION_COLUMNS, rows)
