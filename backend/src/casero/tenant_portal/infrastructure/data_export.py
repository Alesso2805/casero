from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.data_sections import read_sections
from casero.shared.kernel.data_sections import DataSection

SECTIONS = (
    (
        "enlaces_del_inquilino",
        "SELECT id, lease_id AS contrato_id, created_at AS creado_el,"
        " revoked_at AS revocado_el, last_used_at AS ultimo_uso_el FROM tenant_links"
        " ORDER BY created_at, id",
    ),
    (
        "vouchers",
        "SELECT s.id, s.lease_id AS contrato_id, s.declared_cents AS monto_declarado_centimos,"
        " s.declared_on AS fecha_declarada, s.status AS estado,"
        " s.reject_reason AS motivo_de_rechazo, s.payment_id AS pago_id,"
        " s.reviewed_at AS revisado_el, s.created_at AS enviado_el, f.id AS archivo_id,"
        " f.mime AS tipo_de_archivo, f.size_bytes AS tamano_en_bytes"
        " FROM voucher_submissions s JOIN files f"
        " ON f.account_id = s.account_id AND f.id = s.file_id ORDER BY s.created_at, s.id",
    ),
)


class SqlTenantPortalData:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def sections(self, account_id: UUID) -> list[DataSection]:
        return await read_sections(self._connection, SECTIONS, account_id)
