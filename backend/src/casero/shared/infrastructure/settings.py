import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiSettings:
    database_url: str
    rate_limit_key: bytes

    @classmethod
    def from_environment(cls) -> ApiSettings:
        return cls(
            database_url=os.environ["CASERO_APP_DATABASE_URL"],
            rate_limit_key=os.environ["CASERO_RATE_LIMIT_KEY"].encode(),
        )
