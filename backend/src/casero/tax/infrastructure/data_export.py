from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.data_sections import read_sections
from casero.shared.kernel.data_sections import DataSection

SECTIONS = (
    (
        "pagos_a_sunat",
        "SELECT p.id, p.period AS periodo, p.renter_id AS inquilino_id,"
        " p.amount_cents AS monto_centimos, p.paid_on AS pagado_el,"
        " p.order_number AS numero_de_orden, p.base_cents AS monto_declarado_centimos,"
        " p.created_at AS creado_el, v.voided_at AS anulado_el,"
        " v.reason AS motivo_de_anulacion FROM tax_payments p LEFT JOIN tax_payment_voids v"
        " ON v.account_id = p.account_id AND v.tax_payment_id = p.id"
        " ORDER BY p.created_at, p.id",
    ),
)


class SqlTaxData:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def sections(self, account_id: UUID) -> list[DataSection]:
        return await read_sections(self._connection, SECTIONS, account_id)
