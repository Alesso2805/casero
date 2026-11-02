from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

PAGE = "admin.html"


def mount_bundle(app: FastAPI, bundle_dir: Path) -> None:
    """The built panel (ADR-0008). Any other path under /admin gets the page: its router decides."""
    app.mount("/admin/assets", StaticFiles(directory=bundle_dir / "assets"))

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{path:path}", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(bundle_dir / PAGE)
