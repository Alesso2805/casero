import io
import json
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.accounts.application.context import AccountContext
from casero.accounts.application.entitlements import GetEntitlements
from casero.shared.kernel.audit import AuditEntry, AuditLog
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.data_sections import Cell, DataSection
from casero.shared.kernel.spreadsheet import csv_text


class DataSections(Protocol):
    """Implemented by each module with data of its own (AR-03); reads under RLS."""

    async def sections(self, account_id: UUID) -> list[DataSection]: ...


def csv_cell(value: Cell) -> str:
    return "" if value is None else str(value)


def data_archive(sections: Sequence[DataSection], at: datetime) -> bytes:
    """A ZIP with everything in one JSON file and one CSV per section, for a spreadsheet."""
    everything = {
        "exportado_el": at.isoformat(),
        "secciones": {
            section.name: [dict(zip(section.columns, row, strict=True)) for row in section.rows]
            for section in sections
        },
    }
    files = {"datos.json": json.dumps(everything, ensure_ascii=False, indent=2)}
    for section in sections:
        files[f"{section.name}.csv"] = csv_text(
            section.columns, ([csv_cell(value) for value in row] for row in section.rows)
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            # A ZipInfo, because writestr with a name would read the wall clock (AR-06).
            info = zipfile.ZipInfo(name, at.timetuple()[:6])
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


@dataclass(frozen=True)
class ExportMyData:
    """The legal export: everything the account holds, tenants' full documents included.

    Hashes, tokens and device keys stay out. The owner chose the full document on 2026-11-01,
    so each export is audited, like the accountant's (ADR-0007).
    """

    entitlements: GetEntitlements
    modules: Sequence[DataSections]
    audit: AuditLog
    clock: Clock

    async def __call__(self, context: AccountContext) -> bytes | Literal["data_export_unavailable"]:
        if not (await self.entitlements()).allows("data_export"):
            return "data_export_unavailable"
        sections = [
            section
            for module in self.modules
            for section in await module.sections(context.account_id)
        ]
        now = self.clock.now()
        await self.audit.record(
            AuditEntry.of(
                context.account_id,
                context.user_id,
                "export.my_data",
                "accounts",
                context.account_id,
                ["sections"],
                now,
            )
        )
        return data_archive(sections, now)
