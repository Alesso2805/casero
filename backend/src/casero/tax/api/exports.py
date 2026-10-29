from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from casero.accounts.application.context import AccountContext
from casero.tax.application.exports import ExportDeclarations, ExportPayments

FIRST_YEAR = 2026
LAST_YEAR = 2100

Year = Annotated[int, Query(ge=FIRST_YEAR, le=LAST_YEAR)]

RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"content": {"text/csv": {}}, "description": "A CSV file, UTF-8 with BOM"},
    401: {"description": "No valid session"},
    403: {"description": "No account, or `accountant_export_unavailable` in the plan"},
}


def csv_download(content: str, name: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_payments: Callable[..., Awaitable[ExportPayments]],
    provide_declarations: Callable[..., Awaitable[ExportDeclarations]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/exports/payments.csv", response_class=Response, responses=RESPONSES)
    async def export_payments(
        year: Year,
        context: Annotated[AccountContext, Depends(current_account)],
        export: Annotated[ExportPayments, Depends(provide_payments)],
    ) -> Response:
        """The year's payments for the accountant, with the part outside the 1683's base."""
        result = await export(context, year)
        if result == "accountant_export_unavailable":
            raise HTTPException(status_code=403, detail=result)
        return csv_download(result, f"casero-pagos-{year}.csv")

    @router.get("/api/app/exports/declarations.csv", response_class=Response, responses=RESPONSES)
    async def export_declarations(
        year: Year,
        context: Annotated[AccountContext, Depends(current_account)],
        export: Annotated[ExportDeclarations, Depends(provide_declarations)],
    ) -> Response:
        """The year's 1683 declarations for the accountant, with what was paid to SUNAT."""
        result = await export(context, year)
        if result == "accountant_export_unavailable":
            raise HTTPException(status_code=403, detail=result)
        return csv_download(result, f"casero-formularios-{year}.csv")

    return router
