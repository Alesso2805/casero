from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.ledger.domain.allocation import Charge
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock

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
class NewCorrection:
    id: UUID
    lease_id: UUID
    corrects_charge_id: UUID
    amount_cents: int


class ChargeStore(Protocol):
    async def lock_lease(self, lease_id: UUID) -> bool: ...

    async def charge(self, charge_id: UUID) -> ChargeRecord | None: ...

    async def correction_of(self, charge_id: UUID) -> UUID | None: ...

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
class VoidCharge:
    """Voiding is idempotent: doing it again returns the voided charge (rule 5).

    A prior debt is not voided here: its unique index counts voided rows too, so a wrong one
    could not be entered again.
    """

    store: ChargeStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, charge_id: UUID, reason: str
    ) -> ChargeRecord | Literal["charge_not_found", "charge_not_voidable"]:
        found = await self.store.charge(charge_id)
        if found is None:
            return "charge_not_found"
        if found.charge.kind == "opening_balance":
            return "charge_not_voidable"
        await self.store.lock_lease(found.lease_id)
        record = await self.store.charge(charge_id)
        if record is None:
            return "charge_not_found"
        if record.charge.voided:
            return record
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
        return replace(record, charge=replace(record.charge, voided=True))
