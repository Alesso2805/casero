from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.data_sections import read_sections
from casero.shared.kernel.data_sections import DataSection

SECTIONS = (
    (
        "inmuebles",
        "SELECT id, name AS nombre, address_line AS direccion, district AS distrito,"
        " ownership AS titularidad, autovaluo_cents AS autovaluo_centimos,"
        " rented_share_pct AS porcentaje_alquilado, archived_at AS archivado_el"
        " FROM properties ORDER BY id",
    ),
    (
        "unidades",
        "SELECT id, property_id AS inmueble_id, name AS nombre, kind AS tipo,"
        " archived_at AS archivada_el FROM units ORDER BY id",
    ),
)


class SqlPropertyData:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def sections(self, account_id: UUID) -> list[DataSection]:
        return await read_sections(self._connection, SECTIONS, account_id)
