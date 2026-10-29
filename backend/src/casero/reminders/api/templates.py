from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints

from casero.accounts.application.context import AccountContext
from casero.reminders.application.templates import ListTemplates, SaveTemplate, Template
from casero.reminders.domain.messages import MAX_BODY_LENGTH, TemplateKind
from casero.shared.infrastructure.csrf import require_csrf

Body = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_BODY_LENGTH)
]

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No valid session"},
    403: {"description": "No account, or the email is unverified past its deadline"},
}


class TemplateRequest(BaseModel):
    body: Body


class TemplateResponse(BaseModel):
    kind: TemplateKind
    body: str
    default_body: str


def template_response(template: Template) -> TemplateResponse:
    return TemplateResponse(
        kind=template.kind, body=template.body, default_body=template.default_body
    )


def create_router(
    current_account: Callable[..., Awaitable[AccountContext]],
    provide_list: Callable[..., Awaitable[ListTemplates]],
    provide_save: Callable[..., Awaitable[SaveTemplate]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/app/message-templates", responses=READ_ERRORS)
    async def list_templates(
        _: Annotated[AccountContext, Depends(current_account)],
        list_all: Annotated[ListTemplates, Depends(provide_list)],
    ) -> list[TemplateResponse]:
        """The three collection messages, edited or SPEC's default."""
        return [template_response(template) for template in await list_all()]

    @router.put(
        "/api/app/message-templates/{kind}",
        dependencies=[Depends(require_csrf)],
        responses={
            **READ_ERRORS,
            403: {"description": "No account, unverified email past its deadline, or `csrf`"},
            422: {"description": "Invalid data, or `unknown_variable` in the body"},
        },
    )
    async def save_template(
        kind: TemplateKind,
        body: TemplateRequest,
        context: Annotated[AccountContext, Depends(current_account)],
        save: Annotated[SaveTemplate, Depends(provide_save)],
    ) -> TemplateResponse:
        """Replace one message; sending the default body restores it."""
        result = await save(context, kind, body.body)
        if result == "unknown_variable":
            raise HTTPException(status_code=422, detail=result)
        return template_response(result)

    return router
