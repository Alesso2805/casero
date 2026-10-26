import hashlib
import hmac
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.application.registration import NewAccount
from casero.accounts.domain.registration import TRIAL_PLAN, LegalVersion
from casero.shared.infrastructure.database import set_account_context
from casero.shared.kernel.ids import new_id

VALID_INVITE = text(
    "SELECT id FROM registration_invites WHERE token_hash = :token_hash"
    " AND lower(email) = lower(:email) AND used_at IS NULL AND expires_at > :now"
)
CONSUME_INVITE = text(
    "UPDATE registration_invites SET used_at = :now WHERE id = :id AND used_at IS NULL"
)
CURRENT_DOCUMENTS = text(
    "SELECT DISTINCT ON (kind) kind, id FROM legal_documents WHERE published_at <= :today"
    " ORDER BY kind, published_at DESC, version DESC"
)
INSERT_ACCOUNT = text(
    "INSERT INTO accounts (id, display_name, created_at) VALUES (:id, :display_name, :created_at)"
)
INSERT_MEMBER = text(
    "INSERT INTO account_members (account_id, user_id, role)"
    " VALUES (:account_id, :user_id, 'owner')"
)
INSERT_ACCEPTANCE = text(
    "INSERT INTO legal_acceptances (id, account_id, user_id, document_id, accepted_at, ip_hash)"
    " VALUES (:id, :account_id, :user_id, :document_id, :accepted_at, :ip_hash)"
)
INSERT_TRIAL = text(
    "INSERT INTO subscriptions (id, account_id, plan_code, starts_at, trial_ends_at, ends_at)"
    " VALUES (:id, :account_id, :plan_code, :starts_at, :trial_ends_at, :trial_ends_at)"
)
FORGET_WAITLIST = text("DELETE FROM waitlist_entries WHERE lower(email) = lower(:email)")


def invite_token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def acceptance_ip_hash(key: bytes, client: str) -> bytes:
    # Evidence of where an acceptance came from, without keeping the IP itself.
    return hmac.new(key, f"legal-acceptance|{client}".encode(), hashlib.sha256).digest()


class SqlInvites:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def valid_for(self, token: str, email: str, now: datetime) -> UUID | None:
        result = await self._connection.execute(
            VALID_INVITE, {"token_hash": invite_token_hash(token), "email": email, "now": now}
        )
        invite_id: UUID | None = result.scalar_one_or_none()
        return invite_id

    async def consume(self, invite_id: UUID, now: datetime) -> None:
        await self._connection.execute(CONSUME_INVITE, {"id": invite_id, "now": now})


class SqlLegalVersions:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def current(self, today: date) -> list[LegalVersion]:
        rows = await self._connection.execute(CURRENT_DOCUMENTS, {"today": today})
        return [LegalVersion(row.kind, row.id) for row in rows]


class SqlAccountRecords:
    def __init__(self, connection: AsyncConnection, ip_key: bytes) -> None:
        self._connection = connection
        self._ip_key = ip_key

    async def create(self, account: NewAccount) -> None:
        execute = self._connection.execute
        await set_account_context(self._connection, account.account_id)
        await execute(
            INSERT_ACCOUNT,
            {
                "id": account.account_id,
                "display_name": account.display_name,
                "created_at": account.now,
            },
        )
        await execute(INSERT_MEMBER, {"account_id": account.account_id, "user_id": account.user_id})
        ip_hash = acceptance_ip_hash(self._ip_key, account.client)
        await execute(
            INSERT_ACCEPTANCE,
            [
                {
                    "id": new_id(),
                    "account_id": account.account_id,
                    "user_id": account.user_id,
                    "document_id": version.document_id,
                    "accepted_at": account.now,
                    "ip_hash": ip_hash,
                }
                for version in account.accepted
            ],
        )
        await execute(
            INSERT_TRIAL,
            {
                "id": new_id(),
                "account_id": account.account_id,
                "plan_code": TRIAL_PLAN,
                "starts_at": account.trial_starts_on,
                "trial_ends_at": account.trial_ends_on,
            },
        )

    async def forget_waitlist_entry(self, email: str) -> None:
        await self._connection.execute(FORGET_WAITLIST, {"email": email})
