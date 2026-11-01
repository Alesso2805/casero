from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.data_sections import read_sections
from casero.shared.kernel.data_sections import DataSection

SECTIONS = (
    (
        "cargos",
        "SELECT c.id, c.lease_id AS contrato_id, c.kind AS tipo, c.period AS periodo,"
        " c.amount_cents AS monto_centimos, c.due_date AS vencimiento,"
        " c.corrects_charge_id AS corrige_cargo_id, c.pre_2026 AS deuda_de_2025_o_antes,"
        " c.created_at AS creado_el, v.voided_at AS anulado_el, v.reason AS motivo_de_anulacion"
        " FROM charges c LEFT JOIN charge_voids v"
        " ON v.account_id = c.account_id AND v.charge_id = c.id ORDER BY c.created_at, c.id",
    ),
    (
        "pagos",
        "SELECT p.id, p.lease_id AS contrato_id, p.amount_cents AS monto_centimos,"
        " p.received_on AS fecha_de_cobro, p.method AS medio, p.deposit_id AS garantia_id,"
        " p.note AS nota, p.source AS origen, p.created_at AS creado_el,"
        " v.voided_at AS anulado_el, v.reason AS motivo_de_anulacion"
        " FROM payments p LEFT JOIN payment_voids v"
        " ON v.account_id = p.account_id AND v.payment_id = p.id ORDER BY p.created_at, p.id",
    ),
    (
        "garantias",
        "SELECT d.id, d.lease_id AS contrato_id, d.amount_cents AS monto_centimos,"
        " d.received_on AS recibida_el, d.note AS nota, d.created_at AS creada_el,"
        " v.voided_at AS anulada_el, v.reason AS motivo_de_anulacion"
        " FROM deposits d LEFT JOIN deposit_voids v"
        " ON v.account_id = d.account_id AND v.deposit_id = d.id ORDER BY d.created_at, d.id",
    ),
    (
        "devoluciones_de_garantia",
        "SELECT m.id, m.deposit_id AS garantia_id, m.amount_cents AS monto_centimos,"
        " m.on_date AS fecha, m.created_at AS creada_el, v.voided_at AS anulada_el,"
        " v.reason AS motivo_de_anulacion FROM deposit_movements m"
        " LEFT JOIN deposit_movement_voids v"
        " ON v.account_id = m.account_id AND v.deposit_movement_id = m.id"
        " ORDER BY m.created_at, m.id",
    ),
)


class SqlLedgerData:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def sections(self, account_id: UUID) -> list[DataSection]:
        return await read_sections(self._connection, SECTIONS, account_id)
