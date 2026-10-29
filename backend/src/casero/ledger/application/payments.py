from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.ledger.domain.allocation import (
    Charge,
    Payment,
    allocate,
    charge_status,
    debit_order,
)
from casero.ledger.domain.allocation import (
    ChargeKind as ChargeKind,
)
from casero.ledger.domain.allocation import (
    ChargeStatus as ChargeStatus,
)
from casero.ledger.domain.charges import RentChange, rent_for
from casero.ledger.domain.payments import (
    PaymentMethod,
    ReceiptProblem,
    before_control,
    needs_bank,
    receipt_problem,
)
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period

PAYMENT_FIELDS = ("amount_cents", "received_on", "method", "note")


@dataclass(frozen=True)
class NewPayment:
    id: UUID
    lease_id: UUID
    amount_cents: int
    received_on: date
    method: PaymentMethod
    note: str | None


@dataclass(frozen=True)
class PaymentRecord:
    payment: Payment
    lease_id: UUID
    method: str
    note: str | None

    def matches(self, new: NewPayment) -> bool:
        return (
            self.lease_id,
            self.payment.amount_cents,
            self.payment.received_on,
            self.method,
            self.note,
        ) == (new.lease_id, new.amount_cents, new.received_on, new.method, new.note)


@dataclass(frozen=True)
class LeaseLedger:
    lease_id: UUID
    control_from: Period
    rent_changes: tuple[RentChange, ...]
    charges: list[Charge]
    payments: list[PaymentRecord]


class LedgerStore(Protocol):
    async def lock_lease(self, lease_id: UUID) -> bool:
        """Serializes writes on one lease (SPEC: locks go on the lease row); False if missing."""
        ...

    async def lease_ledger(self, lease_id: UUID) -> LeaseLedger | None: ...

    async def payment(self, payment_id: UUID) -> PaymentRecord | None: ...

    async def add_payment(
        self, account_id: UUID, new: NewPayment, created_by: UUID, created_at: datetime
    ) -> bool:
        """False when the id already exists, in this account or another (rule 5)."""
        ...

    async def void_payment(
        self, account_id: UUID, payment_id: UUID, reason: str, voided_by: UUID, at: datetime
    ) -> None: ...


class CashThresholds(Protocol):
    """Implemented by tax (AR-03): the year's bancarization threshold, if loaded."""

    async def cash_threshold_for(self, year: int) -> int | None: ...


@dataclass(frozen=True)
class Recorded:
    record: PaymentRecord
    replayed: bool
    bank_threshold_cents: int | None
    before_control: bool


@dataclass(frozen=True)
class RecordPayment:
    store: LedgerStore
    thresholds: CashThresholds
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, new: NewPayment
    ) -> Recorded | ReceiptProblem | Literal["lease_not_found", "conflict"]:
        if not await self.store.lock_lease(new.lease_id):
            return "lease_not_found"
        ledger = await self.store.lease_ledger(new.lease_id)
        if ledger is None:
            return "lease_not_found"
        existing = await self.store.payment(new.id)
        if existing is not None:
            if not existing.matches(new):
                return "conflict"
            return await self._recorded(existing, True, ledger, new)
        problem = receipt_problem(new.received_on, self.clock.today_lima())
        if problem is not None:
            return problem
        now = self.clock.now()
        if not await self.store.add_payment(context.account_id, new, context.user_id, now):
            return "conflict"
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "payment.created",
                "payments",
                new.id,
                PAYMENT_FIELDS,
                now,
            )
        )
        record = PaymentRecord(
            Payment(new.id, new.amount_cents, new.received_on, now),
            new.lease_id,
            new.method,
            new.note,
        )
        return await self._recorded(record, False, ledger, new)

    async def _recorded(
        self, record: PaymentRecord, replayed: bool, ledger: LeaseLedger, new: NewPayment
    ) -> Recorded:
        rent = rent_for(Period.of(new.received_on), ledger.rent_changes)
        threshold = await self.thresholds.cash_threshold_for(new.received_on.year)
        return Recorded(
            record,
            replayed,
            threshold if needs_bank(new.method, rent, threshold) else None,
            before_control(new.received_on, ledger.control_from),
        )


@dataclass(frozen=True)
class VoidPayment:
    """Voiding is idempotent: doing it again returns the voided payment (rule 5)."""

    store: LedgerStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, payment_id: UUID, reason: str
    ) -> PaymentRecord | Literal["payment_not_found"]:
        found = await self.store.payment(payment_id)
        if found is None:
            return "payment_not_found"
        await self.store.lock_lease(found.lease_id)
        record = await self.store.payment(payment_id)
        if record is None:
            return "payment_not_found"
        if record.payment.voided:
            return record
        now = self.clock.now()
        await self.store.void_payment(context.account_id, payment_id, reason, context.user_id, now)
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "payment.voided",
                "payments",
                payment_id,
                ["reason"],
                now,
            )
        )
        return replace(record, payment=replace(record.payment, voided=True))


@dataclass(frozen=True)
class ChargeLine:
    charge: Charge
    outstanding_cents: int
    status: ChargeStatus | None
    partial: bool


@dataclass(frozen=True)
class Statement:
    lease_id: UUID
    charges: list[ChargeLine]
    payments: list[PaymentRecord]
    balance_cents: int
    credit_cents: int
    up_to_date: bool


@dataclass(frozen=True)
class GetStatement:
    store: LedgerStore
    clock: Clock

    async def __call__(self, lease_id: UUID) -> Statement | None:
        ledger = await self.store.lease_ledger(lease_id)
        if ledger is None:
            return None
        today = self.clock.today_lima()
        allocation = allocate(ledger.charges, [record.payment for record in ledger.payments])
        lines = []
        for charge in sorted(ledger.charges, key=debit_order):
            if charge.voided or charge.is_credit:
                lines.append(ChargeLine(charge, 0, None, False))
                continue
            outstanding = allocation.outstanding[charge.id]
            lines.append(
                ChargeLine(
                    charge,
                    outstanding,
                    charge_status(charge.due_date, outstanding, today),
                    0 < outstanding < charge.amount_cents,
                )
            )
        return Statement(
            lease_id,
            lines,
            sorted(ledger.payments, key=lambda r: (r.payment.received_on, r.payment.created_at)),
            allocation.balance_cents,
            allocation.unapplied_cents,
            not any(line.status == "overdue" for line in lines),
        )
