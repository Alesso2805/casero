from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from casero.accounts.application.entitlements import GetEntitlements
from casero.accounts.application.profile import Profiles
from casero.leases.application.leases import LeaseStore
from casero.leases.application.renters import RenterDocument, RenterDocuments
from casero.ledger.application.collected import collected_payments, rents_charged
from casero.ledger.application.collections import CollectionsStore
from casero.properties.application.properties import PropertyStore
from casero.shared.kernel.periods import Period
from casero.tax.application.calculator import TaxRuleBook
from casero.tax.domain.declarations import Declarant, Declaration, TaxablePayment, declarations
from casero.tax.domain.minimum_rent import RentedProperty, below_minimum_rent

DueStatus = Literal["known", "no_ruc", "unknown_schedule"]
TAXED = ("standard", "company_tenant")


@dataclass(frozen=True)
class DeclarationCard:
    declaration: Declaration
    renter_name: str
    doc_type: str | None
    doc_number: str | None
    company_tenant: bool


@dataclass(frozen=True)
class Untaxed:
    """A lease outside the MVP's cases: Casero shows what was collected but no form (SPEC)."""

    lease_id: UUID
    renter_name: str
    collected_cents: int


@dataclass(frozen=True)
class MinimumRent:
    property_id: UUID
    property_name: str


@dataclass(frozen=True)
class MonthDeclarations:
    period: Period
    ruc: str | None
    due_on: date | None
    due_status: DueStatus
    cards: list[DeclarationCard]
    total_tax_cents: int
    untaxed: list[Untaxed]
    minimum_rent: list[MinimumRent]


@dataclass(frozen=True)
class GetDeclarations:
    """The 1683 of each tenant for the month they paid in, with what SUNAT's form asks for."""

    entitlements: GetEntitlements
    profiles: Profiles
    properties: PropertyStore
    leases: LeaseStore
    renters: RenterDocuments
    books: CollectionsStore
    rule_book: TaxRuleBook

    async def __call__(
        self, period: Period
    ) -> MonthDeclarations | Literal["tax_module_unavailable", "unknown_year"]:
        if not (await self.entitlements()).allows("tax_module"):
            return "tax_module_unavailable"
        rules = await self.rule_book.rules_for(period.year)
        if rules is None:
            return "unknown_year"
        documents = {doc.renter_id: doc for doc in await self.renters.documents()}
        lease_terms = {lease.id: lease.terms for lease in await self.leases.all(period)}
        books = await self.books.lease_books()
        taxable: list[TaxablePayment] = []
        untaxed: defaultdict[UUID, int] = defaultdict(int)
        companies: set[UUID] = set()
        for payment in collected_payments(books, period):
            terms = lease_terms[payment.lease_id]
            if terms.tax_treatment not in TAXED:
                untaxed[payment.lease_id] += payment.amount_cents
                continue
            renter = documents[terms.renter_id]
            if terms.tax_treatment == "company_tenant":
                companies.add(renter.renter_id)
            taxable.append(
                TaxablePayment(
                    Declarant(renter.doc_hmac, renter.renter_id),
                    payment.lease_id,
                    payment.received_on,
                    payment.taxable_cents,
                    payment.old_debt_cents,
                )
            )
        cards = [
            card(declaration, documents[declaration.declarant.renter_id], companies)
            for declaration in declarations(taxable, period, rules)
        ]
        properties = await self.properties.all()
        property_of_unit = {unit.id: p.id for p in properties for unit in p.units}
        rent_by_property: defaultdict[UUID, defaultdict[Period, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for lease_id, months in rents_charged(books, Period(period.year, 1), period).items():
            terms = lease_terms[lease_id]
            if terms.tax_treatment in TAXED:
                for month, cents in months.items():
                    rent_by_property[property_of_unit[terms.unit_id]][month] += cents
        profile = await self.profiles.current()
        due_on = (
            await self.rule_book.due_date(period, profile.ruc_group) if profile.ruc_group else None
        )
        return MonthDeclarations(
            period=period,
            ruc=profile.ruc,
            due_on=due_on,
            due_status=due_status(profile.ruc, due_on),
            cards=cards,
            total_tax_cents=sum(c.declaration.tax_cents for c in cards),
            untaxed=[
                Untaxed(lease_id, documents[lease_terms[lease_id].renter_id].full_name, cents)
                for lease_id, cents in untaxed.items()
            ],
            minimum_rent=[
                MinimumRent(p.id, p.details.name)
                for p in properties
                if p.details.autovaluo_cents is not None
                and below_minimum_rent(
                    RentedProperty(
                        p.details.autovaluo_cents,
                        p.details.rented_share_pct,
                        rent_by_property[p.id],
                    ),
                    rules,
                )
            ],
        )


def card(declaration: Declaration, renter: RenterDocument, companies: set[UUID]) -> DeclarationCard:
    return DeclarationCard(
        declaration,
        renter.full_name,
        renter.doc_type,
        renter.number,
        renter.renter_id in companies,
    )


def due_status(ruc: str | None, due_on: date | None) -> DueStatus:
    """Without a RUC there is no schedule group; with one, the year may not be loaded yet."""
    if ruc is None:
        return "no_ruc"
    return "known" if due_on else "unknown_schedule"
