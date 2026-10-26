from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx2
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.api import registration as registration_api
from casero.accounts.api import waitlist as waitlist_api
from casero.accounts.application.registration import (
    AccountRecords,
    Invites,
    LegalVersions,
    RegisterLandlord,
    RegistrationRateLimiter,
)
from casero.accounts.application.waitlist import (
    JoinWaitlist,
    WaitlistRateLimiter,
    WaitlistRepository,
)
from casero.accounts.infrastructure.registration import (
    SqlAccountRecords,
    SqlInvites,
    SqlLegalVersions,
)
from casero.accounts.infrastructure.waitlist import SqlWaitlistRepository
from casero.admin.api import complaints as complaints_api
from casero.admin.application.complaints import (
    ComplaintRateLimiter,
    ComplaintRepository,
    FileComplaint,
)
from casero.admin.infrastructure.complaints import SqlComplaintRepository
from casero.identity.api import email_events as email_events_api
from casero.identity.api import sessions as sessions_api
from casero.identity.api import unsubscribe as unsubscribe_api
from casero.identity.application.email_suppressions import (
    RecordEmailEvent,
    SnsMessageVerifier,
    SuppressionStore,
)
from casero.identity.application.sessions import (
    AuthenticateSession,
    Credentials,
    LogIn,
    LoginThrottle,
    LogOut,
    PasswordHasher,
    SessionStore,
    SessionTokens,
    Sleeper,
    StartSession,
)
from casero.identity.application.unsubscribe import Unsubscribe, UnsubscribeTokens, UserEmails
from casero.identity.application.users import CreateUser, UserStore
from casero.identity.infrastructure.email_suppressions import SqlSuppressionStore
from casero.identity.infrastructure.passwords import Argon2PasswordHasher
from casero.identity.infrastructure.sessions import (
    AsyncioSleeper,
    PostgresLoginThrottle,
    SecretSessionTokens,
    SqlCredentials,
    SqlSessionStore,
    SqlUserStore,
)
from casero.identity.infrastructure.sns import SnsSignatureVerifier
from casero.identity.infrastructure.unsubscribe import HmacUnsubscribeTokens, SqlUserEmails
from casero.shared.infrastructure.database import anonymous_transaction, create_engine
from casero.shared.infrastructure.rate_limits import PostgresRateLimiter
from casero.shared.infrastructure.settings import ApiSettings
from casero.shared.kernel.clock import Clock, SystemClock
from casero.tax.api import calculator as calculator_api
from casero.tax.application.calculator import (
    CalculateTax,
    CalculatorRateLimiter,
    TaxRuleBook,
)
from casero.tax.infrastructure.rule_book import SqlTaxRuleBook

WAITLIST_JOINS_PER_HOUR = 5
COMPLAINTS_PER_HOUR = 5
CALCULATIONS_PER_HOUR = 30
LOGIN_ATTEMPTS_PER_IP_PER_HOUR = 30
REGISTRATIONS_PER_IP_PER_HOUR = 10
SNS_HTTP_TIMEOUT_SECONDS = 10


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(
    settings: ApiSettings | None = None,
    clock: Clock | None = None,
    sns_verifier: SnsMessageVerifier | None = None,
    sleeper: Sleeper | None = None,
) -> FastAPI:
    config = settings or ApiSettings.from_environment()
    app_clock: Clock = clock or SystemClock()
    engine = create_engine(config.database_url)
    http = httpx2.AsyncClient(timeout=SNS_HTTP_TIMEOUT_SECONDS)
    verifier: SnsMessageVerifier = sns_verifier or SnsSignatureVerifier(http)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await http.aclose()
        await engine.dispose()

    app = FastAPI(
        title="Casero API",
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.engine = engine

    async def provide_join_waitlist(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> JoinWaitlist:
        repository: WaitlistRepository = SqlWaitlistRepository(connection)
        limiter: WaitlistRateLimiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "waitlist", WAITLIST_JOINS_PER_HOUR
        )
        return JoinWaitlist(repository, limiter, app_clock)

    app.include_router(waitlist_api.create_router(provide_join_waitlist))

    async def provide_file_complaint(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> FileComplaint:
        repository: ComplaintRepository = SqlComplaintRepository(connection)
        limiter: ComplaintRateLimiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "complaints", COMPLAINTS_PER_HOUR
        )
        return FileComplaint(repository, limiter, app_clock)

    app.include_router(complaints_api.create_router(provide_file_complaint))

    async def provide_record_email_event(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> RecordEmailEvent:
        store: SuppressionStore = SqlSuppressionStore(connection, config.email_hash_key)
        return RecordEmailEvent(store, verifier, app_clock, config.ses_events_topic_arn)

    app.include_router(email_events_api.create_router(provide_record_email_event))

    tokens: UnsubscribeTokens = HmacUnsubscribeTokens(config.unsubscribe_key)

    async def provide_unsubscribe(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> Unsubscribe:
        users: UserEmails = SqlUserEmails(connection)
        store: SuppressionStore = SqlSuppressionStore(connection, config.email_hash_key)
        return Unsubscribe(tokens, users, store, app_clock)

    app.include_router(unsubscribe_api.create_router(provide_unsubscribe))

    async def provide_calculate(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> CalculateTax:
        rule_book: TaxRuleBook = SqlTaxRuleBook(connection)
        limiter: CalculatorRateLimiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "calculator", CALCULATIONS_PER_HOUR
        )
        return CalculateTax(rule_book, limiter)

    app.include_router(calculator_api.create_router(provide_calculate))

    hasher: PasswordHasher = Argon2PasswordHasher()
    session_tokens: SessionTokens = SecretSessionTokens()
    login_sleeper: Sleeper = sleeper or AsyncioSleeper()

    async def provide_credentials(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> SqlCredentials:
        return SqlCredentials(connection)

    async def provide_login(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> LogIn:
        credentials: Credentials = SqlCredentials(connection)
        store: SessionStore = SqlSessionStore(connection)
        throttle: LoginThrottle = PostgresLoginThrottle(
            connection, config.rate_limit_key, app_clock, LOGIN_ATTEMPTS_PER_IP_PER_HOUR
        )
        start = StartSession(session_tokens, store, app_clock)
        return LogIn(credentials, hasher, start, throttle, login_sleeper)

    async def provide_authenticate(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> AuthenticateSession:
        store: SessionStore = SqlSessionStore(connection)
        return AuthenticateSession(session_tokens, store, app_clock)

    async def provide_logout(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> LogOut:
        store: SessionStore = SqlSessionStore(connection)
        return LogOut(store, app_clock)

    async def provide_register(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> RegisterLandlord:
        limiter: RegistrationRateLimiter = PostgresRateLimiter(
            connection,
            config.rate_limit_key,
            app_clock,
            "registration",
            REGISTRATIONS_PER_IP_PER_HOUR,
        )
        invites: Invites = SqlInvites(connection)
        legal: LegalVersions = SqlLegalVersions(connection)
        users: UserStore = SqlUserStore(connection)
        records: AccountRecords = SqlAccountRecords(connection, config.acceptance_ip_key)
        store: SessionStore = SqlSessionStore(connection)
        return RegisterLandlord(
            config.registration_mode,
            limiter,
            invites,
            legal,
            CreateUser(users, hasher, app_clock),
            records,
            StartSession(session_tokens, store, app_clock),
            app_clock,
        )

    app.include_router(registration_api.create_router(provide_register))

    current_session = sessions_api.session_dependency(provide_authenticate)
    app.include_router(
        sessions_api.create_router(
            provide_login, provide_logout, provide_credentials, current_session
        )
    )

    @app.get("/api/health")
    def health() -> HealthResponse:
        """Report that the API process is up."""
        return HealthResponse(status="ok")

    return app
