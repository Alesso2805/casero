import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from casero.shared.infrastructure.mail import SmtpSecurity, SmtpSettings

SMTP_SECURITY_MODES = ("none", "starttls", "tls")
RegistrationMode = Literal["closed", "invite", "open"]
REGISTRATION_MODES = ("closed", "invite", "open")


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
    email_hash_key: bytes
    ses_events_topic_arn: str
    unsubscribe_key: bytes
    acceptance_ip_key: bytes
    registration_mode: RegistrationMode

    @classmethod
    def from_environment(cls) -> ApiSettings:
        return cls(
            database_url=os.environ["CASERO_APP_DATABASE_URL"],
            rate_limit_key=os.environ["CASERO_RATE_LIMIT_KEY"].encode(),
            email_hash_key=os.environ["CASERO_EMAIL_HASH_KEY"].encode(),
            ses_events_topic_arn=os.environ["CASERO_SES_EVENTS_TOPIC_ARN"],
            unsubscribe_key=os.environ["CASERO_UNSUBSCRIBE_KEY"].encode(),
            acceptance_ip_key=os.environ["CASERO_ACCEPTANCE_IP_KEY"].encode(),
            registration_mode=registration_mode(os.environ.get("REGISTRATION_MODE", "closed")),
        )


def registration_mode(value: str) -> RegistrationMode:
    if value not in REGISTRATION_MODES:
        raise ValueError(f"REGISTRATION_MODE must be one of {', '.join(REGISTRATION_MODES)}")
    return cast(RegistrationMode, value)


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
    email_hash_key: bytes

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
            email_hash_key=env["CASERO_EMAIL_HASH_KEY"].encode(),
        )
