from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.data_sections import read_sections
from casero.shared.kernel.data_sections import DataSection

SECTIONS = (
    (
        "plantillas_de_mensajes",
        "SELECT kind AS tipo, body AS texto FROM message_templates ORDER BY kind",
    ),
    (
        "recordatorios_enviados",
        "SELECT id, kind AS tipo, charge_id AS cargo_id, period AS periodo,"
        " renter_id AS inquilino_id, channel AS canal, created_at AS enviado_el"
        " FROM reminder_logs ORDER BY created_at, id",
    ),
)


class SqlReminderData:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def sections(self, account_id: UUID) -> list[DataSection]:
        return await read_sections(self._connection, SECTIONS, account_id)
