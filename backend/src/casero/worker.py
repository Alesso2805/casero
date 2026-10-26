import asyncio
import os

import asyncpg
import structlog

WORKER_LOCK_KEY = 7_294_011
TICK_SECONDS = 60

log = structlog.get_logger()


async def acquire_worker_lock(connection: asyncpg.Connection) -> bool:
    acquired: bool = await connection.fetchval("SELECT pg_try_advisory_lock($1)", WORKER_LOCK_KEY)
    return acquired


async def run() -> None:
    connection = await asyncpg.connect(os.environ["CASERO_WORKER_DATABASE_URL"])
    try:
        if not await acquire_worker_lock(connection):
            log.info("worker.lock_held_elsewhere")
            return
        log.info("worker.started")
        while True:
            await asyncio.sleep(TICK_SECONDS)
    finally:
        await connection.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
