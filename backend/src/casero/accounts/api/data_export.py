from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from casero.accounts.application.context import AccountContext
from casero.accounts.application.data_export import ExportMyData

RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/zip": {}}, "description": "A ZIP with JSON and CSV files"},
    401: {"description": "No valid session"},
    403: {"description": "No account, unverified email, or `data_export_unavailable`"},
}


def create_router(
    account_for_rights: Callable[..., Awaitable[AccountContext]],
    provide_export: Callable[..., Awaitable[ExportMyData]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/exports/my-data.zip", response_class=Response, responses=RESPONSES)
    async def export_my_data(
        context: Annotated[AccountContext, Depends(account_for_rights)],
        export: Annotated[ExportMyData, Depends(provide_export)],
    ) -> Response:
        """Everything the account holds, also available while the account is blocked."""
        result = await export(context)
        if result == "data_export_unavailable":
            raise HTTPException(status_code=403, detail=result)
        return Response(
            content=result,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="casero-mis-datos.zip"',
                "Cache-Control": "no-store",
            },
        )

    return router
