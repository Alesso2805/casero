from fastapi import APIRouter
from pydantic import BaseModel


class BusinessResponse(BaseModel):
    name: str
    ruc: str
    address: str


def create_router(business: BusinessResponse) -> APIRouter:
    router = APIRouter()

    @router.get("/api/public/business")
    def get_business() -> BusinessResponse:
        """Identify the business behind Casero for the complaints book and the privacy notices."""
        return business

    return router
