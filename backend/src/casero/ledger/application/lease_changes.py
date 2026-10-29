from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.leases.application.leases import LeaseStore, LeaseView, RentChangeRecord, view
from casero.ledger.application.manual_charges import ChargeRecord, ChargeStore
from casero.ledger.domain.allocation import Charge
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.periods import Period

# Stored as the void's reason for the rents of periods after the end (SPEC, "Último mes").
ENDED_REASON = "Contrato terminado"


class ChargedPeriods(Protocol):
    async def lock_lease(self, lease_id: UUID) -> bool: ...

    async def last_rent_period(self, lease_id: UUID) -> Period | None:
        """The latest period with a rent or correction, voided ones included."""
        ...


@dataclass(frozen=True)
class NewRent:
    id: UUID
    lease_id: UUID
    monthly_rent_cents: int


@dataclass(frozen=True)
class RentChanged:
    change: RentChangeRecord
    replayed: bool


@dataclass(frozen=True)
class ChangeRent:
    """A new rent from the next period not yet charged; charged ones keep theirs (SPEC)."""

    leases: LeaseStore
    periods: ChargedPeriods
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, new: NewRent
    ) -> RentChanged | Literal["lease_not_found", "lease_ended", "conflict"]:
        if not await self.periods.lock_lease(new.lease_id):
            return "lease_not_found"
        existing = await self.leases.rent_change(new.id)
        if existing is not None:
            matches = (existing.lease_id, existing.monthly_rent_cents) == (
                new.lease_id,
                new.monthly_rent_cents,
            )
            return RentChanged(existing, True) if matches else "conflict"
        lease = await self.leases.get(new.lease_id, Period.of(self.clock.today_lima()))
        if lease is None:
            return "lease_not_found"
        if lease.ended_at is not None:
            return "lease_ended"
        last = await self.periods.last_rent_period(new.lease_id)
        effective = last.next() if last else lease.terms.control_from
        now = self.clock.now()
        added = await self.leases.add_rent_change(
            context.account_id,
            new.id,
            new.lease_id,
            new.monthly_rent_cents,
            effective,
            context.user_id,
            now,
        )
        if not added:
            return "conflict"
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "lease.rent_changed",
                "lease_rent_changes",
                new.id,
                ["monthly_rent_cents", "effective_period"],
                now,
            )
        )
        return RentChanged(
            RentChangeRecord(new.id, new.lease_id, new.monthly_rent_cents, effective), False
        )


@dataclass(frozen=True)
class SetEndDate:
    """Renewal: extend, move or remove the planned end of an active lease (CS-31).

    Ending earlier than today is a termination, which also settles the charges.
    """

    leases: LeaseStore
    periods: ChargedPeriods
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, lease_id: UUID, end_date: date | None
    ) -> LeaseView | Literal["lease_not_found", "lease_ended", "end_in_past", "end_before_start"]:
        if not await self.periods.lock_lease(lease_id):
            return "lease_not_found"
        today = self.clock.today_lima()
        lease = await self.leases.get(lease_id, Period.of(today))
        if lease is None:
            return "lease_not_found"
        if lease.ended_at is not None:
            return "lease_ended"
        if end_date is not None and end_date < today:
            return "end_in_past"
        if end_date is not None and end_date < lease.terms.start_date:
            return "end_before_start"
        if end_date != lease.terms.end_date:
            await self.leases.set_end_date(lease_id, end_date)
            await self.audit.record(
                AuditEntry.of(
                    context.account_id,
                    context.user_id,
                    "lease.end_date_changed",
                    "leases",
                    lease_id,
                    ["end_date"],
                    self.clock.now(),
                )
            )
        updated = await self.leases.get(lease_id, Period.of(today))
        return view(updated or lease, today)


@dataclass(frozen=True)
class EndingCredit:
    """A credit for the days of the last month the tenant did not use (SPEC, "Último mes")."""

    id: UUID
    amount_cents: int


EndRefusal = Literal[
    "lease_not_found",
    "lease_ended",
    "end_in_future",
    "end_before_start",
    "end_before_control",
    "conflict",
]


@dataclass(frozen=True)
class EndLease:
    """Ends a lease on a date up to today; periods starting after it are not charged.

    A lease registered ahead of its start ends today: all its rents are voided, and what was
    already collected stays in favor of the tenant, to give back (SPEC, "Último mes").
    """

    leases: LeaseStore
    charges: ChargeStore
    audit: AuditLog
    clock: Clock

    async def __call__(
        self, context: AccountContext, lease_id: UUID, ended_on: date, credit: EndingCredit | None
    ) -> LeaseView | EndRefusal:
        if not await self.charges.lock_lease(lease_id):
            return "lease_not_found"
        today = self.clock.today_lima()
        lease = await self.leases.get(lease_id, Period.of(today))
        if lease is None:
            return "lease_not_found"
        if lease.ended_at is not None:
            replayed = lease.ended_at == ended_on and await self._credit_recorded(lease_id, credit)
            return view(lease, today) if replayed else "lease_ended"
        if ended_on > today:
            return "end_in_future"
        not_started = today < lease.terms.start_date
        if ended_on < lease.terms.start_date and not (not_started and ended_on == today):
            return "end_before_start"
        if ended_on < lease.terms.control_from.first_day() and not not_started:
            return "end_before_control"
        if credit is not None and await self.charges.charge(credit.id) is not None:
            return "conflict"
        now = self.clock.now()
        await self.leases.end(lease_id, ended_on)
        last_charged = lease.terms.control_from.previous() if not_started else Period.of(ended_on)
        for charge_id in await self.charges.rents_after(lease_id, last_charged):
            await self.charges.void_charge(
                context.account_id, charge_id, ENDED_REASON, context.user_id, now
            )
            await self._audit(context, "charge.voided", "charges", charge_id, ["reason"])
        if credit is not None:
            record = ChargeRecord(
                Charge(credit.id, "adjustment", -credit.amount_cents, today, None, now),
                lease_id,
                None,
            )
            if not await self.charges.add_charge(context.account_id, record, context.user_id):
                return "conflict"
            await self._audit(context, "charge.adjusted", "charges", credit.id, ["amount_cents"])
        await self._audit(context, "lease.ended", "leases", lease_id, ["ended_at"])
        updated = await self.leases.get(lease_id, Period.of(today))
        return view(updated or lease, today)

    async def _credit_recorded(self, lease_id: UUID, credit: EndingCredit | None) -> bool:
        if credit is None:
            return True
        existing = await self.charges.charge(credit.id)
        return existing is not None and (
            existing.lease_id,
            existing.charge.kind,
            existing.charge.amount_cents,
        ) == (lease_id, "adjustment", -credit.amount_cents)

    async def _audit(
        self,
        context: AccountContext,
        action: str,
        entity: str,
        entity_id: UUID,
        fields: list[str],
    ) -> None:
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                action,
                entity,
                entity_id,
                fields,
                self.clock.now(),
            )
        )
