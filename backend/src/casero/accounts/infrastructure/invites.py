"""Create a one-use registration invite as casero_admin: `make invite EMAIL=ana@example.com`.

Prints the link to send; the token travels in the URL fragment, so it never reaches a log.
"""

import asyncio
import os
import secrets
import sys
from datetime import datetime

from sqlalchemy import text

from casero.accounts.domain.registration import INVITE_LIFETIME
from casero.accounts.infrastructure.registration import invite_token_hash
from casero.shared.infrastructure.database import create_engine
from casero.shared.kernel.clock import SystemClock
from casero.shared.kernel.ids import new_id

TOKEN_BYTES = 32

INSERT_INVITE = text(
    "INSERT INTO registration_invites (id, email, token_hash, expires_at)"
    " VALUES (:id, :email, :token_hash, :expires_at)"
)
AUDIT = text(
    "INSERT INTO staff_audit_log (id, staff_user_id, actor, action, entity, entity_id, at)"
    " VALUES (:id, NULL, 'cli', 'invite.create', 'registration_invites', :entity_id, :at)"
)


async def create_invite(database_url: str, email: str, public_url: str, now: datetime) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    invite_id = new_id()
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                INSERT_INVITE,
                {
                    "id": invite_id,
                    "email": email.strip(),
                    "token_hash": invite_token_hash(token),
                    "expires_at": now + INVITE_LIFETIME,
                },
            )
            await connection.execute(AUDIT, {"id": new_id(), "entity_id": invite_id, "at": now})
    finally:
        await engine.dispose()
    return f"{public_url.rstrip('/')}/registro#invitacion={token}"


def main() -> None:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        sys.exit("Uso: make invite EMAIL=correo@ejemplo.com")
    link = asyncio.run(
        create_invite(
            os.environ["CASERO_ADMIN_DATABASE_URL"],
            sys.argv[1],
            os.environ["CASERO_PUBLIC_URL"],
            SystemClock().now(),
        )
    )
    print(f"Invitación de un solo uso, vence en {INVITE_LIFETIME.days} días:\n{link}")


if __name__ == "__main__":
    main()
