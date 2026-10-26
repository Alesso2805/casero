import json
import sys
from pathlib import Path

from casero.api import create_app
from casero.shared.infrastructure.settings import ApiSettings, BusinessSettings

UNUSED_SETTINGS = ApiSettings(
    database_url="postgresql+asyncpg://unused@localhost/unused",
    rate_limit_key=b"unused",
    business=BusinessSettings(name="unused", ruc="unused", address="unused"),
)


def main() -> None:
    target = Path(sys.argv[1])
    schema = create_app(UNUSED_SETTINGS).openapi()
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
