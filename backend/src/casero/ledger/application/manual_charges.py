from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.leases.application.leases import (
    LeaseProblem,
    LeaseStore,
    OpeningBalances,
    lease_problem,
    opening_balance_due,
)
from casero.ledger.application.declared import DeclaredMonths, months_a_void_changes
from casero.ledger.application.payments import LeaseLedger
from casero.ledger.domain.allocation import Charge
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period

CORRECTABLE_KINDS = ("rent", "rent_correction")


@dataclass(frozen=True)
class ChargeRecord:
    charge: Charge
    lease_id: UUID
    corrects_charge_id: UUID | None


@dataclass(frozen=True)
class NewAdjustment:
    id: UUID
    lease_id: UUID
    amount_cents: int


@dataclass(frozen=True)
class NewPriorDebt:
    id: UUID
    lease_id: UUID
    pre_2026: bool
    amount_cents: int


@dataclass(frozen=True)
class NewCorrection:
    id: UUID
    lease_id: UUID
    corrects_charge_id: UUID
    amount_cents: int


class ChargeStore(Protocol):
    async def lock_lease(self, lease_id: UUID) -> bool: ...

    async def charge(self, charge_id: UUID) -> ChargeRecord | None: ...

    async def lease_ledger(self, lease_id: UUID) -> LeaseLedger | None: ...

    async def correction_of(self, charge_id: UUID) -> UUID | None: ...

    async def valid_prior_debt(self, lease_id: UUID, pre_2026: bool) -> bool: ...

    async def rents_after(self, lease_id: UUID, period: Period) -> list[UUID]:
        """Valid rents and corrections of the periods after the given one."""
        ...

    async def add_charge(self, account_id: UUID, record: ChargeRecord, created_by: UUID) -> bool:
        """False when the id already exists, in this account or another (rule 5)."""
        ...

    async def void_charge(
        self, account_id: UUID, charge_id: UUID, reason: str, voided_by: UUID, at: datetime
    ) -> None: ...


@dataclass(frozen=True)
class ChargeCreated:
    record: ChargeRecord
    replayed: bool


CorrectionRefusal = Literal["lease_not_found", "conflict", "not_a_voided_rent", "already_corrected"]


@dataclass(frozen=True)
class AdjustLease:
    """A debit (positive) or a credit (negative) entered by hand; a credit is never money
    collected, so it stays out of the tax base (SPEC, "Ajustes negativos")."""

    store: ChargeStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, new: NewAdjustment
    ) -> ChargeCreated | Literal["lease_not_found", "conflict"]:
        if not await self.store.lock_lease(new.lease_id):
            return "lease_not_found"
        existing = await self.store.charge(new.id)
        if existing is not None:
            matches = (
                existing.lease_id,
                existing.charge.kind,
                existing.charge.amount_cents,
            ) == (new.lease_id, "adjustment", new.amount_cents)
            return ChargeCreated(existing, True) if matches else "conflict"
        now = self.clock.now()
        record = ChargeRecord(
            Charge(new.id, "adjustment", new.amount_cents, self.clock.today_lima(), None, now),
            new.lease_id,
            None,
        )
        if not await self.store.add_charge(context.account_id, record, context.user_id):
            return "conflict"
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "charge.adjusted",
                "charges",
                new.id,
                ["amount_cents"],
                now,
            )
        )
        return ChargeCreated(record, False)


@dataclass(frozen=True)
class CorrectRent:
    """Replaces a voided rent of a period with its corrected amount (SPEC, "Corrección")."""

    store: ChargeStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, new: NewCorrection
    ) -> ChargeCreated | CorrectionRefusal:
        if not await self.store.lock_lease(new.lease_id):
            return "lease_not_found"
        existing = await self.store.charge(new.id)
        if existing is not None:
            matches = (
                existing.lease_id,
                existing.corrects_charge_id,
                existing.charge.amount_cents,
            ) == (new.lease_id, new.corrects_charge_id, new.amount_cents)
            return ChargeCreated(existing, True) if matches else "conflict"
        target = await self.store.charge(new.corrects_charge_id)
        if (
            target is None
            or target.lease_id != new.lease_id
            or target.charge.kind not in CORRECTABLE_KINDS
            or not target.charge.voided
        ):
            return "not_a_voided_rent"
        if await self.store.correction_of(target.charge.id) is not None:
            return "already_corrected"
        now = self.clock.now()
        record = ChargeRecord(
            Charge(
                new.id,
                "rent_correction",
                new.amount_cents,
                target.charge.due_date,
                None,
                now,
                period=target.charge.period,
            ),
            new.lease_id,
            target.charge.id,
        )
        if not await self.store.add_charge(context.account_id, record, context.user_id):
            return "conflict"
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "charge.corrected",
                "charges",
                new.id,
                ["amount_cents", "corrects_charge_id"],
                now,
            )
        )
        return ChargeCreated(record, False)


@dataclass(frozen=True)
class RecordPriorDebt:
    """A prior debt entered after the lease, usually to replace a voided wrong one.

    At most one valid prior debt per lease and era, checked under the lease lock (CS-31).
    """

    leases: LeaseStore
    store: ChargeStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, new: NewPriorDebt
    ) -> ChargeCreated | LeaseProblem | Literal["lease_not_found", "conflict", "prior_debt_exists"]:
        if not await self.store.lock_lease(new.lease_id):
            return "lease_not_found"
        existing = await self.store.charge(new.id)
        if existing is not None:
            matches = (
                existing.lease_id,
                existing.charge.kind,
                existing.charge.pre_2026,
                existing.charge.amount_cents,
            ) == (new.lease_id, "opening_balance", new.pre_2026, new.amount_cents)
            return ChargeCreated(existing, True) if matches else "conflict"
        today = self.clock.today_lima()
        lease = await self.leases.get(new.lease_id, Period.of(today))
        if lease is None:
            return "lease_not_found"
        amount = new.amount_cents
        opening = OpeningBalances(*((amount, None) if new.pre_2026 else (None, amount)))
        problem = lease_problem(lease.terms, opening, today)
        if problem is not None:
            return problem
        if await self.store.valid_prior_debt(new.lease_id, new.pre_2026):
            return "prior_debt_exists"
        now = self.clock.now()
        due = opening_balance_due(new.pre_2026, lease.terms.control_from)
        record = ChargeRecord(
            Charge(new.id, "opening_balance", amount, due, new.pre_2026, now), new.lease_id, None
        )
        if not await self.store.add_charge(context.account_id, record, context.user_id):
            return "conflict"
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "charge.prior_debt",
                "charges",
                new.id,
                ["amount_cents", "pre_2026"],
                now,
            )
        )
        return ChargeCreated(record, False)


@dataclass(frozen=True)
class VoidedCharge:
    record: ChargeRecord
    paid_to_sunat: list[Period]


@dataclass(frozen=True)
class VoidCharge:
    """Voiding is idempotent: doing it again returns the voided charge (rule 5).

    Either way it says which months already paid to SUNAT it changed: voiding a credit or the
    debt from 2025 or before moves the taxed part of later payments.
    """

    store: ChargeStore
    declared: DeclaredMonths
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, charge_id: UUID, reason: str
    ) -> VoidedCharge | Literal["charge_not_found"]:
        found = await self.store.charge(charge_id)
        if found is None:
            return "charge_not_found"
        await self.store.lock_lease(found.lease_id)
        record = await self.store.charge(charge_id)
        ledger = await self.store.lease_ledger(found.lease_id)
        if record is None or ledger is None:
            return "charge_not_found"
        payments = [r.payment for r in ledger.payments]
        changed = months_a_void_changes(ledger.charges, payments, charge_id=charge_id)
        paid = await self.declared.paid_to_sunat(record.lease_id, changed) if changed else []
        if record.charge.voided:
            return VoidedCharge(record, paid)
        now = self.clock.now()
        await self.store.void_charge(context.account_id, charge_id, reason, context.user_id, now)
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "charge.voided",
                "charges",
                charge_id,
                ["reason"],
                now,
            )
        )
        return VoidedCharge(replace(record, charge=replace(record.charge, voided=True)), paid)
