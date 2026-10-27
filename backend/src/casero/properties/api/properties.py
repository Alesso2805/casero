from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, model_validator

from casero.accounts.application.context import AccountContext
from casero.properties.application.properties import (
    AddUnit,
    CreateProperty,
    ListProperties,
    UpdateProperty,
    UpdateUnit,
)
from casero.properties.domain.properties import (
    Ownership,
    Property,
    PropertyDetails,
    Unit,
    UnitDetails,
    UnitKind,
)
from casero.shared.infrastructure.csrf import require_csrf

MAX_AUTOVALUO_CENTS = 10**13
MAX_UNITS_PER_REQUEST = 50

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, or the email is unverified past its deadline"},
}
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **READ_ERRORS,
    403: {"description": "No account, unverified email past its deadline, or `csrf`"},
    404: {"description": "No such property or unit in this account"},
}


class UnitRequest(BaseModel):
    name: ShortText
    kind: UnitKind

    def details(self) -> UnitDetails:
        return UnitDetails(self.name, self.kind)


class PropertyRequest(BaseModel):
    name: Name
    address_line: Address | None = None
    district: ShortText | None = None
    ownership: Ownership
    conjugal_option_confirmed: bool = Field(
        default=False,
        description="The landlord confirmed the account's RUC is the spouse's who chose the option",
    )
    autovaluo_cents: Annotated[int, Field(gt=0, le=MAX_AUTOVALUO_CENTS)] | None = None
    rented_share_pct: Annotated[int, Field(ge=1, le=100)] = 100

    @model_validator(mode="after")
    def conjugal_option_is_confirmed(self) -> Self:
        if self.ownership == "conjugal_option" and not self.conjugal_option_confirmed:
            raise ValueError("conjugal_option needs conjugal_option_confirmed")
        return self

    def details(self) -> PropertyDetails:
        return PropertyDetails(
            name=self.name,
            address_line=self.address_line,
            district=self.district,
            ownership=self.ownership,
            autovaluo_cents=self.autovaluo_cents,
            rented_share_pct=self.rented_share_pct,
        )


class NewPropertyRequest(PropertyRequest):
    units: list[UnitRequest] = Field(min_length=1, max_length=MAX_UNITS_PER_REQUEST)


class UnitResponse(BaseModel):
    id: UUID
    property_id: UUID
    name: str
    kind: UnitKind
    archived: bool


class PropertyResponse(BaseModel):
    id: UUID
    name: str
    address_line: str | None
    district: str | None
    ownership: Ownership
    autovaluo_cents: int | None
    rented_share_pct: int
    archived: bool
    units: list[UnitResponse]


def unit_response(unit: Unit) -> UnitResponse:
    return UnitResponse(
        id=unit.id,
        property_id=unit.property_id,
        name=unit.details.name,
        kind=unit.details.kind,
        archived=unit.archived,
    )


def property_response(item: Property) -> PropertyResponse:
    details = item.details
    return PropertyResponse(
        id=item.id,
        name=details.name,
        address_line=details.address_line,
        district=details.district,
        ownership=details.ownership,
        autovaluo_cents=details.autovaluo_cents,
        rented_share_pct=details.rented_share_pct,
        archived=item.archived,
        units=[unit_response(unit) for unit in item.units],
    )


def refuse(result: str) -> HTTPException:
    status = {"not_found": 404, "ownership_mismatch": 422}.get(result, 409)
    return HTTPException(status_code=status, detail=result)


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_list: Callable[..., Awaitable[ListProperties]],
    provide_create: Callable[..., Awaitable[CreateProperty]],
    provide_update: Callable[..., Awaitable[UpdateProperty]],
    provide_add_unit: Callable[..., Awaitable[AddUnit]],
    provide_update_unit: Callable[..., Awaitable[UpdateUnit]],
) -> APIRouter:
    router = APIRouter()
    csrf = [Depends(require_csrf)]

    @router.get("/api/app/properties", responses=READ_ERRORS)
    async def list_properties(
        _: Annotated[AccountContext, Depends(current_account)],
        list_all: Annotated[ListProperties, Depends(provide_list)],
    ) -> list[PropertyResponse]:
        """Every property of the account with its units, archived ones included."""
        return [property_response(item) for item in await list_all()]

    @router.post(
        "/api/app/properties",
        status_code=201,
        dependencies=csrf,
        responses={
            **WRITE_ERRORS,
            422: {"description": "Invalid data, or `ownership_mismatch` with the declarant"},
        },
    )
    async def create_property(
        body: NewPropertyRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        create: Annotated[CreateProperty, Depends(provide_create)],
    ) -> PropertyResponse:
        """Register a property with its first units.

        `estate` ownership is allowed only, and always, in an estate account.
        """
        result = await create(context, body.details(), [unit.details() for unit in body.units])
        if isinstance(result, str):
            raise refuse(result)
        return property_response(result)

    @router.put(
        "/api/app/properties/{property_id}",
        dependencies=csrf,
        responses={
            **WRITE_ERRORS,
            409: {"description": "`archived`: archived properties can't be edited"},
            422: {"description": "Invalid data, or `ownership_mismatch` with the declarant"},
        },
    )
    async def update_property(
        property_id: UUID,
        body: PropertyRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        update: Annotated[UpdateProperty, Depends(provide_update)],
    ) -> PropertyResponse:
        """Replace the property's details; its units are edited one by one."""
        result = await update(context, property_id, body.details())
        if isinstance(result, str):
            raise refuse(result)
        return property_response(result)

    @router.post(
        "/api/app/properties/{property_id}/units",
        status_code=201,
        dependencies=csrf,
        responses={
            **WRITE_ERRORS,
            409: {"description": "`archived`: the property is archived"},
        },
    )
    async def add_unit(
        property_id: UUID,
        body: UnitRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        add: Annotated[AddUnit, Depends(provide_add_unit)],
    ) -> UnitResponse:
        """Add a unit to a property."""
        result = await add(context, property_id, body.details())
        if isinstance(result, str):
            raise refuse(result)
        return unit_response(result)

    @router.put(
        "/api/app/units/{unit_id}",
        dependencies=csrf,
        responses={
            **WRITE_ERRORS,
            409: {"description": "`archived`: archived units can't be edited"},
        },
    )
    async def update_unit(
        unit_id: UUID,
        body: UnitRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        update: Annotated[UpdateUnit, Depends(provide_update_unit)],
    ) -> UnitResponse:
        """Rename a unit or change its kind."""
        result = await update(context, unit_id, body.details())
        if isinstance(result, str):
            raise refuse(result)
        return unit_response(result)

    return router
