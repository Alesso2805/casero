import json
import sys
from pathlib import Path

from casero.api import create_app


def main() -> None:
    target = Path(sys.argv[1])
    schema = create_app().openapi()
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
