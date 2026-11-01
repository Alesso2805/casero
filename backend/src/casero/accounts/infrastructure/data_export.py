from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from casero.shared.infrastructure.data_sections import read_sections
from casero.shared.kernel.data_sections import DataSection

SECTIONS = (
    (
        "cuenta",
        "SELECT id, display_name AS nombre, taxpayer_kind AS tipo_de_declarante, ruc,"
        " ruc_group AS grupo_de_vencimiento, daily_digest AS resumen_diario,"
        " created_at AS creada_el FROM accounts",
    ),
    (
        "usuario",
        "SELECT u.id, u.email AS correo, u.email_verified_at AS correo_confirmado_el,"
        " u.created_at AS creado_el FROM users u JOIN account_members m ON m.user_id = u.id"
        " WHERE m.account_id = :account_id",
    ),
    (
        "aceptaciones_legales",
        "SELECT a.id, d.kind AS documento, d.version, a.accepted_at AS aceptado_el"
        " FROM legal_acceptances a JOIN legal_documents d ON d.id = a.document_id"
        " ORDER BY a.accepted_at, a.id",
    ),
    (
        "retiros_de_consentimiento",
        "SELECT w.id, d.kind AS documento, d.version, w.withdrawn_at AS retirado_el"
        " FROM legal_withdrawals w JOIN legal_documents d ON d.id = w.document_id"
        " ORDER BY w.withdrawn_at, w.id",
    ),
    (
        "suscripciones",
        "SELECT id, plan_code AS plan, starts_at AS inicio, trial_ends_at AS fin_de_prueba,"
        " ends_at AS fin, ended_at AS terminada_el, founder AS fundador FROM subscriptions"
        " ORDER BY starts_at, id",
    ),
    (
        "pagos_de_suscripcion",
        "SELECT id, amount_cents AS monto_centimos, paid_on AS pagado_el, method AS medio,"
        " boleta_number AS boleta, months AS meses FROM subscription_payments"
        " ORDER BY paid_on, id",
    ),
)


class SqlAccountData:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def sections(self, account_id: UUID) -> list[DataSection]:
        return await read_sections(self._connection, SECTIONS, account_id)
