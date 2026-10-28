from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints

from casero.accounts.application.context import AccountContext
from casero.leases.application.renters import CreateRenter, ListRenters, UpdateRenter
from casero.leases.domain.renters import (
    DocType,
    Document,
    Renter,
    RenterDetails,
    normalize_phone,
    parse_document,
)
from casero.shared.infrastructure.csrf import require_csrf

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
RawText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, or the email is unverified past its deadline"},
}
WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **READ_ERRORS,
    403: {"description": "No account, unverified email past its deadline, or `csrf`"},
    409: {"description": "`duplicate_document`: another renter of the account has it"},
    422: {"description": "Invalid data, `invalid_phone` or `invalid_document`"},
}


class DocumentRequest(BaseModel):
    doc_type: DocType
    number: RawText


class RenterRequest(BaseModel):
    full_name: FullName
    phone: RawText | None = None
    document: DocumentRequest | None = None


class RenterResponse(BaseModel):
    id: UUID
    full_name: str
    phone_e164: str | None
    doc_type: DocType | None
    doc_last4: str | None


def renter_response(item: Renter) -> RenterResponse:
    return RenterResponse(
        id=item.id,
        full_name=item.details.full_name,
        phone_e164=item.details.phone_e164,
        doc_type=item.doc_type,
        doc_last4=item.doc_last4,
    )


def parsed(body: RenterRequest) -> tuple[RenterDetails, Document | None]:
    phone = None
    if body.phone is not None and (phone := normalize_phone(body.phone)) is None:
        raise HTTPException(status_code=422, detail="invalid_phone")
    document = None
    if body.document is not None:
        document = parse_document(body.document.doc_type, body.document.number)
        if document is None:
            raise HTTPException(status_code=422, detail="invalid_document")
    return RenterDetails(body.full_name, phone), document


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_list: Callable[..., Awaitable[ListRenters]],
    provide_create: Callable[..., Awaitable[CreateRenter]],
    provide_update: Callable[..., Awaitable[UpdateRenter]],
) -> APIRouter:
    router = APIRouter()
    csrf = [Depends(require_csrf)]

    @router.get("/api/app/renters", responses=READ_ERRORS)
    async def list_renters(
        _: Annotated[AccountContext, Depends(current_account)],
        list_all: Annotated[ListRenters, Depends(provide_list)],
    ) -> list[RenterResponse]:
        """The account's renters; documents show only their type and last characters."""
        return [renter_response(item) for item in await list_all()]

    @router.post("/api/app/renters", status_code=201, dependencies=csrf, responses=WRITE_ERRORS)
    async def create_renter(
        body: RenterRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        create: Annotated[CreateRenter, Depends(provide_create)],
    ) -> RenterResponse:
        """Register a renter; a Peruvian mobile without +51 is taken as such."""
        details, document = parsed(body)
        result = await create(context, details, document)
        if result == "duplicate_document":
            raise HTTPException(status_code=409, detail=result)
        return renter_response(result)

    @router.put(
        "/api/app/renters/{renter_id}",
        dependencies=csrf,
        responses={**WRITE_ERRORS, 404: {"description": "No such renter in this account"}},
    )
    async def update_renter(
        renter_id: UUID,
        body: RenterRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        update: Annotated[UpdateRenter, Depends(provide_update)],
    ) -> RenterResponse:
        """Replace the name and phone; a `document`, if sent, replaces the stored one."""
        details, document = parsed(body)
        result = await update(context, renter_id, details, document)
        if result == "not_found":
            raise HTTPException(status_code=404, detail=result)
        if result == "duplicate_document":
            raise HTTPException(status_code=409, detail=result)
        return renter_response(result)

    return router
