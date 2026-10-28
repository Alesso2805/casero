import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from casero.shared.infrastructure.crypto import DocumentHasher, FieldCipher, b64decode, parse_keys
from casero.shared.infrastructure.mail import SmtpSecurity, SmtpSettings

SMTP_SECURITY_MODES = ("none", "starttls", "tls")
RegistrationMode = Literal["closed", "invite", "open"]
REGISTRATION_MODES = ("closed", "invite", "open")
MIN_SECRET_KEY_BYTES = 32


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
    smtp: SmtpSettings
    public_url: str
    field_cipher: FieldCipher
    document_hasher: DocumentHasher
    sentry_dsn: str | None = None
    sentry_environment: str = "production"

    @classmethod
    def from_environment(cls) -> ApiSettings:
        return cls(
            database_url=os.environ["CASERO_APP_DATABASE_URL"],
            rate_limit_key=secret_key(os.environ, "CASERO_RATE_LIMIT_KEY"),
            email_hash_key=secret_key(os.environ, "CASERO_EMAIL_HASH_KEY"),
            ses_events_topic_arn=os.environ["CASERO_SES_EVENTS_TOPIC_ARN"],
            unsubscribe_key=secret_key(os.environ, "CASERO_UNSUBSCRIBE_KEY"),
            acceptance_ip_key=secret_key(os.environ, "CASERO_ACCEPTANCE_IP_KEY"),
            registration_mode=registration_mode(os.environ.get("REGISTRATION_MODE", "closed")),
            smtp=smtp_from_environment(os.environ),
            public_url=os.environ["CASERO_PUBLIC_URL"],
            field_cipher=FieldCipher(
                parse_keys(os.environ["CASERO_ENCRYPTION_KEYS"]),
                os.environ["CASERO_ENCRYPTION_ACTIVE_KEY"],
            ),
            document_hasher=DocumentHasher(b64decode(os.environ["CASERO_DOC_HMAC_KEY"])),
            sentry_dsn=os.environ.get("SENTRY_DSN") or None,
            sentry_environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        )


def secret_key(env: Mapping[str, str], name: str) -> bytes:
    """Rejects a weak HMAC key at startup: CASERO_EMAIL_HASH_KEY can never be changed later."""
    key = env[name].encode()
    if len(key) < MIN_SECRET_KEY_BYTES:
        raise ValueError(f"{name} must have at least {MIN_SECRET_KEY_BYTES} bytes")
    return key


def registration_mode(value: str) -> RegistrationMode:
    if value not in REGISTRATION_MODES:
        raise ValueError(f"REGISTRATION_MODE must be one of {', '.join(REGISTRATION_MODES)}")
    return cast(RegistrationMode, value)


def smtp_from_environment(env: Mapping[str, str]) -> SmtpSettings:
    return SmtpSettings(
        host=env["CASERO_SMTP_HOST"],
        port=int(env["CASERO_SMTP_PORT"]),
        security=smtp_security(env["CASERO_SMTP_SECURITY"]),
        username=env.get("CASERO_SMTP_USERNAME") or None,
        password=env.get("CASERO_SMTP_PASSWORD") or None,
        sender=env["CASERO_MAIL_FROM"],
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
    email_hash_key: bytes
    sentry_dsn: str | None = None
    sentry_environment: str = "production"
    alerts_inbox: str | None = None
    heartbeat_url: str | None = None

    @property
    def engine_url(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    @classmethod
    def from_environment(cls) -> WorkerSettings:
        env = os.environ
        return cls(
            database_url=env["CASERO_WORKER_DATABASE_URL"],
            smtp=smtp_from_environment(env),
            business=BusinessSettings.from_environment(env),
            complaints_inbox=env["CASERO_COMPLAINTS_INBOX"],
            email_hash_key=secret_key(env, "CASERO_EMAIL_HASH_KEY"),
            sentry_dsn=env.get("SENTRY_DSN") or None,
            sentry_environment=env.get("SENTRY_ENVIRONMENT", "production"),
            alerts_inbox=env.get("CASERO_ALERTS_INBOX") or None,
            heartbeat_url=env.get("CASERO_WORKER_HEARTBEAT_URL") or None,
        )
