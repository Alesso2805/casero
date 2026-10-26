import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from casero.shared.infrastructure.mail import SmtpSecurity, SmtpSettings

SMTP_SECURITY_MODES = ("none", "starttls", "tls")


@dataclass(frozen=True)
class BusinessSettings:
    name: str
    ruc: str
    address: str

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> BusinessSettings:
        return cls(
            name=env["CASERO_BUSINESS_NAME"],
            ruc=env["CASERO_BUSINESS_RUC"],
            address=env["CASERO_BUSINESS_ADDRESS"],
        )


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


def smtp_security(value: str) -> SmtpSecurity:
    if value not in SMTP_SECURITY_MODES:
        raise ValueError(f"CASERO_SMTP_SECURITY must be one of {', '.join(SMTP_SECURITY_MODES)}")
    return cast(SmtpSecurity, value)


@dataclass(frozen=True)
class WorkerSettings:
    database_url: str
    smtp: SmtpSettings
    business: BusinessSettings
    complaints_inbox: str

    @property
    def engine_url(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @classmethod
    def from_environment(cls) -> WorkerSettings:
        env = os.environ
        return cls(
            database_url=env["CASERO_WORKER_DATABASE_URL"],
            smtp=SmtpSettings(
                host=env["CASERO_SMTP_HOST"],
                port=int(env["CASERO_SMTP_PORT"]),
                security=smtp_security(env["CASERO_SMTP_SECURITY"]),
                username=env.get("CASERO_SMTP_USERNAME") or None,
                password=env.get("CASERO_SMTP_PASSWORD") or None,
                sender=env["CASERO_MAIL_FROM"],
            ),
            business=BusinessSettings.from_environment(env),
            complaints_inbox=env["CASERO_COMPLAINTS_INBOX"],
        )
