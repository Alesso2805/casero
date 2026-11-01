from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from casero.accounts.application.context import AccountContext
from casero.accounts.application.legal import (
    AcceptLegalDocuments,
    GetLegalStatus,
    LegalStatus,
    WithdrawConsent,
)
from casero.accounts.domain.registration import DocumentKind
from casero.shared.infrastructure.csrf import require_csrf

LEGAL_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, unverified email, or `csrf` on a write"},
}


class LegalDocumentResponse(BaseModel):
    id: UUID
    kind: DocumentKind
    version: str
    url: str


class LegalStatusResponse(BaseModel):
    pending: list[LegalDocumentResponse] = Field(
        description="Current versions the user still has to accept"
    )
    consent_withdrawn: bool = Field(
        description="The sensitive-data consent is withdrawn: only rights routes work"
    )


class AcceptanceRequest(BaseModel):
    document_ids: Annotated[list[UUID], Field(min_length=1, max_length=3)]


def status_response(status: LegalStatus) -> LegalStatusResponse:
    return LegalStatusResponse(
        pending=[
            LegalDocumentResponse(
                id=document.document_id,
                kind=document.kind,
                version=document.version,
                url=document.url,
            )
            for document in status.pending
        ],
        consent_withdrawn=status.consent_withdrawn,
    )


def create_router(
    account_for_rights: Callable[..., Awaitable[AccountContext]],
    provide_status: Callable[..., Awaitable[GetLegalStatus]],
    provide_accept: Callable[..., Awaitable[AcceptLegalDocuments]],
    provide_withdraw: Callable[..., Awaitable[WithdrawConsent]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/legal", responses=LEGAL_ERRORS)
    async def legal_status(
        context: Annotated[AccountContext, Depends(account_for_rights)],
        get_status: Annotated[GetLegalStatus, Depends(provide_status)],
    ) -> LegalStatusResponse:
        """What the user must accept, and whether the consent is withdrawn."""
        return status_response(await get_status(context))

    @router.post(
        "/api/app/legal/acceptances",
        dependencies=[Depends(require_csrf)],
        responses={
            **LEGAL_ERRORS,
            422: {"description": "Invalid data, or `document_not_current`"},
        },
    )
    async def accept_documents(
        body: AcceptanceRequest,
        request: Request,
        context: Annotated[AccountContext, Depends(account_for_rights)],
        accept: Annotated[AcceptLegalDocuments, Depends(provide_accept)],
    ) -> LegalStatusResponse:
        """Accept current versions; giving the consent again also unblocks the account."""
        client = request.client.host if request.client else "unknown"
        result = await accept(context, body.document_ids, client)
        if result == "document_not_current":
            raise HTTPException(status_code=422, detail=result)
        return status_response(result)

    @router.post(
        "/api/app/legal/consent-withdrawal",
        dependencies=[Depends(require_csrf)],
        responses=LEGAL_ERRORS,
    )
    async def withdraw_consent(
        context: Annotated[AccountContext, Depends(account_for_rights)],
        withdraw: Annotated[WithdrawConsent, Depends(provide_withdraw)],
    ) -> LegalStatusResponse:
        """Withdraw the sensitive-data consent; the account then only exports or deletes."""
        return status_response(await withdraw(context))

    return router
