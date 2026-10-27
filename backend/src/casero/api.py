from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx2
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from casero.accounts.api import account as account_api
from casero.accounts.api import registration as registration_api
from casero.accounts.api import waitlist as waitlist_api
from casero.accounts.application.account import AccountNames, GetAccountSummary
from casero.accounts.application.context import (
    AccountContext,
    AccountScope,
    Memberships,
    OpenAccount,
)
from casero.accounts.application.entitlements import (
    GetEntitlements,
    PlanCatalog,
    SubscriptionReader,
)
from casero.accounts.application.profile import GetProfile, Profiles, UpdateProfile
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
from casero.accounts.infrastructure.account import (
    SqlAccounts,
    SqlAccountScope,
    SqlMemberships,
    SqlPlans,
    SqlProfiles,
    SqlSubscriptions,
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
from casero.identity.api import account_emails as account_emails_api
from casero.identity.api import email_events as email_events_api
from casero.identity.api import sessions as sessions_api
from casero.identity.api import unsubscribe as unsubscribe_api
from casero.identity.application.account_emails import (
    AccessGate,
    AccountEmailSender,
    AccountLinks,
    AccountMailer,
    AccountUsers,
    ConfirmEmail,
    EmailRateLimiter,
    EmailTokens,
    EmailTokenStore,
    RequestPasswordReset,
    ResetPassword,
    SendVerification,
)
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
from casero.identity.domain.account_emails import (
    RESET_EMAILS_PER_HOUR,
    VERIFICATION_EMAILS_PER_HOUR,
)
from casero.identity.domain.sessions import Session
from casero.identity.infrastructure.account_emails import (
    SecretEmailTokens,
    SqlAccountUsers,
    SqlEmailTokenStore,
)
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
from casero.shared.infrastructure.audit import SqlAuditLog
from casero.shared.infrastructure.database import anonymous_transaction, create_engine
from casero.shared.infrastructure.mail import SmtpMailer
from casero.shared.infrastructure.rate_limits import PostgresRateLimiter
from casero.shared.infrastructure.settings import ApiSettings
from casero.shared.kernel.audit import AuditLog
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
PASSWORD_RESETS_PER_IP_PER_HOUR = 10
SNS_HTTP_TIMEOUT_SECONDS = 10


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(
    settings: ApiSettings | None = None,
    clock: Clock | None = None,
    sns_verifier: SnsMessageVerifier | None = None,
    sleeper: Sleeper | None = None,
    mailer: AccountMailer | None = None,
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

    current_session = sessions_api.session_dependency(provide_authenticate)

    account_mailer: AccountMailer = mailer or SmtpMailer(config.smtp, app_clock)
    email_tokens: EmailTokens = SecretEmailTokens()
    links = AccountLinks(config.public_url)

    def email_sender(connection: AsyncConnection) -> AccountEmailSender:
        store: EmailTokenStore = SqlEmailTokenStore(connection)
        suppressions: SuppressionStore = SqlSuppressionStore(connection, config.email_hash_key)
        return AccountEmailSender(
            email_tokens, store, suppressions, account_mailer, links, app_clock
        )

    def send_verification(connection: AsyncConnection) -> SendVerification:
        users: AccountUsers = SqlAccountUsers(connection)
        limiter: EmailRateLimiter = PostgresRateLimiter(
            connection,
            config.rate_limit_key,
            app_clock,
            "verification-email",
            VERIFICATION_EMAILS_PER_HOUR,
        )
        return SendVerification(users, limiter, email_sender(connection))

    async def provide_send_verification(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> SendVerification:
        return send_verification(connection)

    async def provide_confirm_email(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> ConfirmEmail:
        users: AccountUsers = SqlAccountUsers(connection)
        store: EmailTokenStore = SqlEmailTokenStore(connection)
        return ConfirmEmail(users, store, email_tokens, app_clock)

    async def provide_request_reset(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> RequestPasswordReset:
        users: AccountUsers = SqlAccountUsers(connection)
        ip_limiter: EmailRateLimiter = PostgresRateLimiter(
            connection,
            config.rate_limit_key,
            app_clock,
            "password-reset-ip",
            PASSWORD_RESETS_PER_IP_PER_HOUR,
        )
        email_limiter: EmailRateLimiter = PostgresRateLimiter(
            connection,
            config.rate_limit_key,
            app_clock,
            "password-reset-email",
            RESET_EMAILS_PER_HOUR,
        )
        return RequestPasswordReset(users, ip_limiter, email_limiter, email_sender(connection))

    async def provide_reset_password(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> ResetPassword:
        users: AccountUsers = SqlAccountUsers(connection)
        store: EmailTokenStore = SqlEmailTokenStore(connection)
        sessions: SessionStore = SqlSessionStore(connection)
        return ResetPassword(users, store, email_tokens, hasher, sessions, app_clock)

    app.include_router(
        account_emails_api.create_router(
            current_session,
            provide_send_verification,
            provide_confirm_email,
            provide_request_reset,
            provide_reset_password,
        )
    )

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
            send_verification(connection),
            app_clock,
        )

    app.include_router(registration_api.create_router(provide_register))
    app.include_router(
        sessions_api.create_router(
            provide_login, provide_logout, provide_credentials, current_session, app_clock
        )
    )

    async def provide_open_account(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> OpenAccount:
        memberships: Memberships = SqlMemberships(connection)
        scope: AccountScope = SqlAccountScope(connection)
        return OpenAccount(memberships, scope)

    async def provide_access_gate(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> AccessGate:
        users: AccountUsers = SqlAccountUsers(connection)
        return AccessGate(users, app_clock)

    async def current_account(
        session: Annotated[Session, Depends(current_session)],
        gate: Annotated[AccessGate, Depends(provide_access_gate)],
        open_account: Annotated[OpenAccount, Depends(provide_open_account)],
    ) -> AccountContext:
        if await gate.blocked(session.user_id):
            raise HTTPException(status_code=403, detail="email_unverified")
        context = await open_account(session.user_id)
        if context is None:
            raise HTTPException(status_code=403, detail="no_account")
        return context

    async def provide_entitlements(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> GetEntitlements:
        subscriptions: SubscriptionReader = SqlSubscriptions(connection)
        plans: PlanCatalog = SqlPlans(connection)
        return GetEntitlements(subscriptions, plans, app_clock)

    async def provide_account_summary(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> GetAccountSummary:
        names: AccountNames = SqlAccounts(connection)
        return GetAccountSummary(names, entitlements)

    async def provide_get_profile(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> GetProfile:
        profiles: Profiles = SqlProfiles(connection)
        return GetProfile(profiles)

    async def provide_update_profile(
        connection: Annotated[AsyncConnection, Depends(anonymous_transaction)],
    ) -> UpdateProfile:
        profiles: Profiles = SqlProfiles(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return UpdateProfile(profiles, audit, app_clock)

    app.include_router(
        account_api.create_router(
            current_account,
            provide_account_summary,
            provide_get_profile,
            provide_update_profile,
        )
    )

    @app.get("/api/health")
    def health() -> HealthResponse:
        """Report that the API process is up."""
        return HealthResponse(status="ok")

    return app
