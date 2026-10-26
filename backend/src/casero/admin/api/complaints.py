from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Annotated, Self

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator

from casero.admin.application.complaints import FileComplaint
from casero.admin.domain.complaints import (
    ComplaintKind,
    ComplaintSheet,
    DocumentType,
    Guardian,
    ItemKind,
    ResponseChannel,
    is_valid_document,
    normalize_document,
)

MAX_CLAIMED_AMOUNT_CENTS = 10**12

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
DocumentNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class GuardianRequest(BaseModel):
    full_name: Name
    address: Address | None = None
    phone: Phone | None = None
    email: EmailStr | None = None


class FileComplaintRequest(BaseModel):
    full_name: Name
    document_type: DocumentType
    document_number: DocumentNumber
    address: Address | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    guardian: GuardianRequest | None = None
    item_kind: ItemKind
    claimed_amount_cents: Annotated[int, Field(ge=0, le=MAX_CLAIMED_AMOUNT_CENTS)] | None = None
    item_description: LongText | None = None
    kind: ComplaintKind
    detail: LongText
    request: LongText | None = None
    response_channel: ResponseChannel

    @model_validator(mode="after")
    def check_sheet(self) -> Self:
        if not is_valid_document(self.document_type, normalize_document(self.document_number)):
            raise ValueError("document_number does not match document_type")
        if self.response_channel == "email" and self.email is None:
            raise ValueError("an email answer needs an email")
        if self.response_channel == "letter" and self.address is None:
            raise ValueError("a letter answer needs an address")
        return self

    def to_sheet(self) -> ComplaintSheet:
        guardian = self.guardian
        return ComplaintSheet(
            full_name=self.full_name,
            document_type=self.document_type,
            document_number=normalize_document(self.document_number),
            address=self.address,
            email=str(self.email) if self.email else None,
            phone=self.phone,
            guardian=Guardian(
                full_name=guardian.full_name,
                address=guardian.address,
                phone=guardian.phone,
                email=str(guardian.email) if guardian.email else None,
            )
            if guardian
            else None,
            item_kind=self.item_kind,
            claimed_amount_cents=self.claimed_amount_cents,
            item_description=self.item_description,
            kind=self.kind,
            detail=self.detail,
            request=self.request,
            response_channel=self.response_channel,
        )


class FiledComplaintResponse(BaseModel):
    number: str
    filed_at: datetime
    due_on: date


def create_router(provide_file_complaint: Callable[..., Awaitable[FileComplaint]]) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/public/complaints",
        status_code=201,
        response_model=FiledComplaintResponse,
        responses={429: {"description": "Too many requests from this client"}},
    )
    async def file_complaint(
        body: FileComplaintRequest,
        request: Request,
        file: Annotated[FileComplaint, Depends(provide_file_complaint)],
    ) -> FiledComplaintResponse | Response:
        """File a claim or a complaint in the virtual Libro de Reclamaciones."""
        client = request.client.host if request.client else "unknown"
        complaint = await file(body.to_sheet(), client)
        if complaint is None:
            return Response(status_code=429)
        return FiledComplaintResponse(
            number=complaint.number, filed_at=complaint.created_at, due_on=complaint.due_on
        )

    return router
