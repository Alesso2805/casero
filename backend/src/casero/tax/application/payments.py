from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period
from casero.tax.application.declarations import GetDeclarations

TAX_PAYMENT_FIELDS = ("period", "renter_id", "amount_cents", "paid_on", "order_number")


@dataclass(frozen=True)
class NewTaxPayment:
    id: UUID
    period: Period
    renter_id: UUID
    amount_cents: int
    paid_on: date
    order_number: str


@dataclass(frozen=True)
class TaxPaymentRecord:
    id: UUID
    period: Period
    renter_id: UUID
    renter_doc_hmac: bytes
    amount_cents: int
    paid_on: date
    order_number: str
    base_cents: int
    created_at: datetime
    voided: bool

    def matches(self, new: NewTaxPayment) -> bool:
        return (
            self.period,
            self.renter_id,
            self.amount_cents,
            self.paid_on,
            self.order_number,
        ) == (new.period, new.renter_id, new.amount_cents, new.paid_on, new.order_number)


class TaxPaymentStore(Protocol):
    async def add(
        self,
        account_id: UUID,
        new: NewTaxPayment,
        renter_doc_hmac: bytes,
        base_cents: int,
        created_by: UUID,
        created_at: datetime,
    ) -> bool:
        """False when the id already exists, in this account or another (rule 5)."""
        ...

    async def get(self, payment_id: UUID) -> TaxPaymentRecord | None: ...

    async def of_period(self, period: Period) -> list[TaxPaymentRecord]: ...

    async def void(
        self, account_id: UUID, payment_id: UUID, reason: str, voided_by: UUID, at: datetime
    ) -> bool:
        """False when it was already voided."""
        ...


@dataclass(frozen=True)
class RecordedTaxPayment:
    record: TaxPaymentRecord
    replayed: bool


TaxPaymentRefusal = Literal[
    "tax_module_unavailable",
    "unknown_year",
    "declaration_not_found",
    "declaration_incomplete",
    "paid_before_period",
    "paid_in_future",
    "conflict",
]


@dataclass(frozen=True)
class RecordTaxPayment:
    """A payment of one declaration's 1683, with the base Casero showed for it (SPEC)."""

    declarations: GetDeclarations
    store: TaxPaymentStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, new: NewTaxPayment
    ) -> RecordedTaxPayment | TaxPaymentRefusal:
        month = await self.declarations(new.period)
        if isinstance(month, str):
            return month
        existing = await self.store.get(new.id)
        if existing is not None:
            return RecordedTaxPayment(existing, True) if existing.matches(new) else "conflict"
        card = next(
            (c for c in month.cards if c.declaration.declarant.renter_id == new.renter_id), None
        )
        if card is None:
            return "declaration_not_found"
        doc_hmac = card.declaration.declarant.doc_hmac
        if doc_hmac is None:
            return "declaration_incomplete"
        if new.paid_on < new.period.first_day():
            return "paid_before_period"
        if new.paid_on > self.clock.today_lima():
            return "paid_in_future"
        now = self.clock.now()
        base = card.declaration.base_cents
        if not await self.store.add(context.account_id, new, doc_hmac, base, context.user_id, now):
            return "conflict"
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "tax_payment.created",
                "tax_payments",
                new.id,
                TAX_PAYMENT_FIELDS,
                now,
            )
        )
        record = TaxPaymentRecord(
            new.id,
            new.period,
            new.renter_id,
            doc_hmac,
            new.amount_cents,
            new.paid_on,
            new.order_number,
            base,
            now,
            False,
        )
        return RecordedTaxPayment(record, False)


@dataclass(frozen=True)
class VoidTaxPayment:
    """Voiding is idempotent: doing it again returns the voided payment (rule 5)."""

    entitlements: GetEntitlements
    store: TaxPaymentStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, payment_id: UUID, reason: str
    ) -> TaxPaymentRecord | Literal["tax_module_unavailable", "tax_payment_not_found"]:
        if not (await self.entitlements()).allows("tax_module"):
            return "tax_module_unavailable"
        record = await self.store.get(payment_id)
        if record is None:
            return "tax_payment_not_found"
        now = self.clock.now()
        if await self.store.void(context.account_id, payment_id, reason, context.user_id, now):
            await self.audit.record(
                AuditEntry.of(
                    context.account_id,
                    context.user_id,
                    "tax_payment.voided",
                    "tax_payments",
                    payment_id,
                    ["reason"],
                    now,
                )
            )
        return replace(record, voided=True)
