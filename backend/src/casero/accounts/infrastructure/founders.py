import asyncio
import os
import sys
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text

from casero.shared.infrastructure.database import create_engine
from casero.shared.kernel.clock import SystemClock
from casero.shared.kernel.ids import new_id

GRANT = text(
    "UPDATE subscriptions s SET founder = true, ends_at = :ends_at"
    " FROM account_members m JOIN users u ON u.id = m.user_id"
    " WHERE s.account_id = m.account_id AND s.ended_at IS NULL AND NOT s.founder"
    " AND lower(u.email) = lower(:email) RETURNING s.id"
)
AUDIT = text(
    "INSERT INTO staff_audit_log (id, staff_user_id, actor, action, entity, entity_id, at)"
    " VALUES (:id, NULL, 'cli', 'subscription.grant_founder', 'subscriptions', :entity_id, :at)"
)


def a_year_after(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return day.replace(year=day.year + 1, day=28)


async def grant_founder(database_url: str, email: str, today: date, now: datetime) -> UUID | None:
    """The founder's year counts from this command (SPEC, beta privada)."""
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            row = (
                await connection.execute(
                    GRANT, {"email": email.strip(), "ends_at": a_year_after(today)}
                )
            ).first()
            if row is None:
                return None
            await connection.execute(AUDIT, {"id": new_id(), "entity_id": row.id, "at": now})
            subscription_id: UUID = row.id
            return subscription_id
    finally:
        await engine.dispose()


def main() -> None:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        sys.exit("Uso: make grant-founder EMAIL=correo@ejemplo.com")
    clock = SystemClock()
    granted = asyncio.run(
        grant_founder(
            os.environ["CASERO_ADMIN_DATABASE_URL"], sys.argv[1], clock.today_lima(), clock.now()
        )
    )
    if granted is None:
        sys.exit("No hay una cuenta activa con ese correo, o ya es de fundador.")
    print(f"Listo: la cuenta tiene el año de fundador hasta el {a_year_after(clock.today_lima())}.")


if __name__ == "__main__":
    main()
