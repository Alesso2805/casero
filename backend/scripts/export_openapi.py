import json
import sys
from pathlib import Path

from casero.api import create_app
from casero.shared.infrastructure.settings import ApiSettings

UNUSED_SETTINGS = ApiSettings(
    database_url="postgresql+asyncpg://unused@localhost/unused",
    rate_limit_key=b"unused",
    email_hash_key=b"unused",
    ses_events_topic_arn="arn:aws:sns:us-east-1:000000000000:unused",
    unsubscribe_key=b"unused",
    acceptance_ip_key=b"unused",
    registration_mode="closed",
)


def main() -> None:
    target = Path(sys.argv[1])
    schema = create_app(UNUSED_SETTINGS).openapi()
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
