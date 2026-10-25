from alembic import op
from sqlalchemy.util import await_only


def execute_script(sql: str) -> None:
    driver_connection = op.get_bind().connection.driver_connection
    if driver_connection is None:
        raise RuntimeError("Migrations need an open driver connection")
    await_only(driver_connection.execute(sql))
