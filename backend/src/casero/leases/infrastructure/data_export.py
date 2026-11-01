from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.crypto import FieldCipher, field_context
from casero.shared.infrastructure.data_sections import read_sections
from casero.shared.kernel.data_sections import DataSection, plain_cell

RENTERS = text(
    "SELECT id, full_name, phone_e164, email, doc_type, doc_enc, account_id"
    " FROM renters ORDER BY id"
)
RENTER_COLUMNS = (
    "id",
    "nombre",
    "celular",
    "correo",
    "tipo_de_documento",
    "numero_de_documento",
)
SECTIONS = (
    (
        "contratos",
        "SELECT id, unit_id AS unidad_id, renter_id AS inquilino_id, due_day AS dia_de_pago,"
        " start_date AS inicio, control_from_period AS control_desde, end_date AS fin_previsto,"
        " ended_at AS terminado_el, tax_treatment AS tratamiento_tributario,"
        " tools_enabled AS whatsapp_y_portal, created_at AS creado_el FROM leases ORDER BY id",
    ),
    (
        "cambios_de_renta",
        "SELECT id, lease_id AS contrato_id, monthly_rent_cents AS renta_mensual_centimos,"
        " effective_period AS desde_periodo, created_at AS creado_el FROM lease_rent_changes"
        " ORDER BY created_at, id",
    ),
)


class SqlLeaseData:
    """The tenant's full document is decrypted here on purpose (ExportMyData, ADR-0007)."""

    def __init__(self, connection: AsyncConnection, cipher: FieldCipher) -> None:
        self._connection = connection
        self._cipher = cipher

    async def sections(self, account_id: UUID) -> list[DataSection]:
        rows = await self._connection.execute(RENTERS)
        renters = DataSection(
            "inquilinos",
            RENTER_COLUMNS,
            [
                (
                    plain_cell(row.id),
                    row.full_name,
                    row.phone_e164,
                    row.email,
                    row.doc_type,
                    self._cipher.decrypt(
                        row.doc_enc, field_context("renters", "doc_enc", row.account_id, row.id)
                    )
                    if row.doc_enc
                    else None,
                )
                for row in rows
            ],
        )
        return [renters, *await read_sections(self._connection, SECTIONS, account_id)]
