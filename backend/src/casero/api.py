from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx2
from fastapi import Depends, FastAPI, Header, HTTPException, Request
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
from casero.accounts.application.profile import (
    GetProfile,
    Profiles,
    PropertyHoldings,
    UpdateProfile,
)
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
    LoginSteps,
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
    EngineLoginSteps,
    PostgresLoginThrottle,
    SecretSessionTokens,
    SqlCredentials,
    SqlSessionStore,
    SqlUserStore,
)
from casero.identity.infrastructure.sns import SnsSignatureVerifier
from casero.identity.infrastructure.unsubscribe import HmacUnsubscribeTokens, SqlUserEmails
from casero.leases.api import renters as renters_api
from casero.leases.application.leases import LeaseStore, ListLeases
from casero.leases.application.renters import (
    CreateRenter,
    ListRenters,
    RenterDocuments,
    RenterStore,
    UpdateRenter,
)
from casero.leases.infrastructure.active_leases import SqlActiveLeases
from casero.leases.infrastructure.leases import SqlLeaseStore
from casero.leases.infrastructure.renters import SqlRenterHolders, SqlRenterStore
from casero.ledger.api import charges as charges_api
from casero.ledger.api import collections as collections_api
from casero.ledger.api import lease_changes as lease_changes_api
from casero.ledger.api import leases as leases_api
from casero.ledger.api import payments as payments_api
from casero.ledger.application.charges import EnsureRentCharges, RentChargeStore
from casero.ledger.application.collections import CollectionsStore, GetCollections
from casero.ledger.application.lease_changes import (
    ChangeRent,
    ChargedPeriods,
    EndLease,
    SetEndDate,
)
from casero.ledger.application.leases import CreateLease, OpeningBalanceStore
from casero.ledger.application.manual_charges import (
    AdjustLease,
    ChargeStore,
    CorrectRent,
    RecordPriorDebt,
    VoidCharge,
)
from casero.ledger.application.payments import (
    CashThresholds,
    GetStatement,
    LedgerStore,
    RecordPayment,
    VoidPayment,
)
from casero.ledger.infrastructure.ledger import SqlLedger
from casero.ledger.infrastructure.opening_balances import SqlOpeningBalances
from casero.ledger.infrastructure.rent_charges import SqlRentCharges
from casero.properties.api import properties as properties_api
from casero.properties.application.properties import (
    ActiveLeases,
    AddUnit,
    ArchiveProperty,
    ArchiveUnit,
    CreateProperty,
    ListProperties,
    PropertyStore,
    UpdateProperty,
    UpdateUnit,
)
from casero.properties.infrastructure.properties import SqlPropertyStore
from casero.reminders.api import reminders as reminders_api
from casero.reminders.api import templates as templates_api
from casero.reminders.application.reminders import (
    ListLastReminders,
    PrepareReminder,
    RecipientStore,
    ReminderLog,
    TenantLinkUrls,
)
from casero.reminders.application.templates import ListTemplates, SaveTemplate, TemplateStore
from casero.reminders.infrastructure.reminders import SqlRecipientStore, SqlReminderLog
from casero.reminders.infrastructure.templates import SqlTemplateStore
from casero.shared.infrastructure import client_errors as client_errors_api
from casero.shared.infrastructure.audit import SqlAuditLog
from casero.shared.infrastructure.caching import NoStore
from casero.shared.infrastructure.database import Transaction, create_engine, database_answers
from casero.shared.infrastructure.error_tracking import init_error_tracking
from casero.shared.infrastructure.logs import ErrorShield, configure_logging
from casero.shared.infrastructure.mail import SmtpMailer
from casero.shared.infrastructure.rate_limits import PostgresRateLimiter
from casero.shared.infrastructure.settings import ApiSettings
from casero.shared.kernel.audit import AuditLog
from casero.shared.kernel.clock import Clock, SystemClock
from casero.tax.api import calculator as calculator_api
from casero.tax.api import declarations as declarations_api
from casero.tax.api import exports as exports_api
from casero.tax.api import payments as tax_payments_api
from casero.tax.application.calculator import (
    CalculateTax,
    CalculatorRateLimiter,
    TaxRuleBook,
)
from casero.tax.application.declarations import GetDeclarations
from casero.tax.application.exports import ExportDeclarations, ExportPayments
from casero.tax.application.payments import RecordTaxPayment, VoidTaxPayment
from casero.tax.application.sunat_payments import TaxPaymentStore
from casero.tax.application.upcoming import GetUpcomingDue
from casero.tax.infrastructure.payments import SqlTaxPayments
from casero.tax.infrastructure.rule_book import SqlTaxRuleBook
from casero.tenant_portal.api import links as tenant_links_api
from casero.tenant_portal.api import portal as tenant_portal_api
from casero.tenant_portal.application.links import (
    GetLink,
    IssueLink,
    LinkInUse,
    Links,
    LinkSigner,
    LinkStore,
    RevokeLink,
)
from casero.tenant_portal.application.portal import (
    GetTenantStatement,
    OpenPortal,
    PortalReader,
    TenantGate,
)
from casero.tenant_portal.infrastructure.links import HmacLinkSigner, SqlLinks
from casero.tenant_portal.infrastructure.portal import SqlPortalReader, SqlTenantGate

WAITLIST_JOINS_PER_HOUR = 5
COMPLAINTS_PER_HOUR = 5
CALCULATIONS_PER_HOUR = 30
CLIENT_ERRORS_PER_HOUR = 30
CLIENT_ERROR_KINDS_PER_HOUR = 1
CLIENT_ERRORS_FORWARDED_PER_HOUR = 6
# Account emails go out inside the request's transaction (ADR-0009): a slow SMTP server must
# not hold a pooled connection for long.
ACCOUNT_EMAIL_TIMEOUT_SECONDS = 10
TENANT_PORTAL_PER_HOUR = 60
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
    configure_logging()
    config = settings or ApiSettings.from_environment()
    init_error_tracking(config.sentry_dsn, config.sentry_environment)
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
    app.add_middleware(ErrorShield)
    app.add_middleware(NoStore)

    async def provide_join_waitlist(
        connection: Transaction,
    ) -> JoinWaitlist:
        repository: WaitlistRepository = SqlWaitlistRepository(connection)
        limiter: WaitlistRateLimiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "waitlist", WAITLIST_JOINS_PER_HOUR
        )
        return JoinWaitlist(repository, limiter, app_clock)

    app.include_router(waitlist_api.create_router(provide_join_waitlist))

    async def provide_file_complaint(
        connection: Transaction,
    ) -> FileComplaint:
        repository: ComplaintRepository = SqlComplaintRepository(connection)
        limiter: ComplaintRateLimiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "complaints", COMPLAINTS_PER_HOUR
        )
        return FileComplaint(repository, limiter, app_clock)

    app.include_router(complaints_api.create_router(provide_file_complaint))

    async def provide_record_email_event(
        connection: Transaction,
    ) -> RecordEmailEvent:
        store: SuppressionStore = SqlSuppressionStore(connection, config.email_hash_key)
        return RecordEmailEvent(store, verifier, app_clock, config.ses_events_topic_arn)

    app.include_router(email_events_api.create_router(provide_record_email_event))

    tokens: UnsubscribeTokens = HmacUnsubscribeTokens(config.unsubscribe_key)

    async def provide_unsubscribe(
        connection: Transaction,
    ) -> Unsubscribe:
        users: UserEmails = SqlUserEmails(connection)
        store: SuppressionStore = SqlSuppressionStore(connection, config.email_hash_key)
        return Unsubscribe(tokens, users, store, app_clock)

    app.include_router(unsubscribe_api.create_router(provide_unsubscribe))

    async def provide_calculate(
        connection: Transaction,
    ) -> CalculateTax:
        rule_book: TaxRuleBook = SqlTaxRuleBook(connection)
        limiter: CalculatorRateLimiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "calculator", CALCULATIONS_PER_HOUR
        )
        return CalculateTax(rule_book, limiter)

    app.include_router(calculator_api.create_router(provide_calculate))

    async def provide_client_error_limits(
        connection: Transaction,
    ) -> client_errors_api.ReportLimits:
        def limiter(scope: str, per_hour: int) -> PostgresRateLimiter:
            key = config.rate_limit_key
            return PostgresRateLimiter(connection, key, app_clock, scope, per_hour)

        return client_errors_api.ReportLimits(
            per_client=limiter("client-errors", CLIENT_ERRORS_PER_HOUR),
            per_kind=limiter("client-error-kinds", CLIENT_ERROR_KINDS_PER_HOUR),
            overall=limiter("client-errors-forwarded", CLIENT_ERRORS_FORWARDED_PER_HOUR),
        )

    app.include_router(client_errors_api.create_router(provide_client_error_limits))

    hasher: PasswordHasher = Argon2PasswordHasher()
    session_tokens: SessionTokens = SecretSessionTokens()
    login_sleeper: Sleeper = sleeper or AsyncioSleeper()

    async def provide_credentials(
        connection: Transaction,
    ) -> SqlCredentials:
        return SqlCredentials(connection)

    def login_throttle(connection: AsyncConnection) -> LoginThrottle:
        throttle: LoginThrottle = PostgresLoginThrottle(
            connection, config.rate_limit_key, app_clock, LOGIN_ATTEMPTS_PER_IP_PER_HOUR
        )
        return throttle

    def login_credentials(connection: AsyncConnection) -> Credentials:
        credentials: Credentials = SqlCredentials(connection)
        return credentials

    def login_sessions(connection: AsyncConnection) -> StartSession:
        store: SessionStore = SqlSessionStore(connection)
        return StartSession(session_tokens, store, app_clock)

    login_steps: LoginSteps = EngineLoginSteps(
        engine, login_throttle, login_credentials, login_sessions, hasher
    )

    async def provide_login() -> LogIn:
        """Without the request's transaction: the delay must not hold a connection (I1)."""
        return LogIn(login_steps, login_sleeper)

    async def provide_authenticate(
        connection: Transaction,
    ) -> AuthenticateSession:
        store: SessionStore = SqlSessionStore(connection)
        return AuthenticateSession(session_tokens, store, app_clock)

    async def provide_logout(
        connection: Transaction,
    ) -> LogOut:
        store: SessionStore = SqlSessionStore(connection)
        return LogOut(store, app_clock)

    current_session = sessions_api.session_dependency(provide_authenticate)

    account_mailer: AccountMailer = mailer or SmtpMailer(
        config.smtp, app_clock, timeout_seconds=ACCOUNT_EMAIL_TIMEOUT_SECONDS
    )
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
        connection: Transaction,
    ) -> SendVerification:
        return send_verification(connection)

    async def provide_confirm_email(
        connection: Transaction,
    ) -> ConfirmEmail:
        users: AccountUsers = SqlAccountUsers(connection)
        store: EmailTokenStore = SqlEmailTokenStore(connection)
        return ConfirmEmail(users, store, email_tokens, app_clock)

    async def provide_request_reset(
        connection: Transaction,
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
        connection: Transaction,
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
        connection: Transaction,
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
        connection: Transaction,
    ) -> OpenAccount:
        memberships: Memberships = SqlMemberships(connection)
        scope: AccountScope = SqlAccountScope(connection)
        return OpenAccount(memberships, scope)

    async def provide_access_gate(
        connection: Transaction,
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
        connection: Transaction,
    ) -> GetEntitlements:
        subscriptions: SubscriptionReader = SqlSubscriptions(connection)
        plans: PlanCatalog = SqlPlans(connection)
        return GetEntitlements(subscriptions, plans, app_clock)

    async def provide_account_summary(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> GetAccountSummary:
        names: AccountNames = SqlAccounts(connection)
        return GetAccountSummary(names, entitlements)

    async def provide_get_profile(
        connection: Transaction,
    ) -> GetProfile:
        profiles: Profiles = SqlProfiles(connection)
        holdings: PropertyHoldings = SqlPropertyStore(connection)
        return GetProfile(profiles, holdings)

    async def provide_update_profile(
        connection: Transaction,
    ) -> UpdateProfile:
        profiles: Profiles = SqlProfiles(connection)
        holdings: PropertyHoldings = SqlPropertyStore(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return UpdateProfile(profiles, holdings, audit, app_clock)

    app.include_router(
        account_api.create_router(
            current_account,
            provide_account_summary,
            provide_get_profile,
            provide_update_profile,
        )
    )

    async def provide_list_properties(
        connection: Transaction,
    ) -> ListProperties:
        store: PropertyStore = SqlPropertyStore(connection)
        return ListProperties(store)

    async def provide_create_property(
        connection: Transaction,
    ) -> CreateProperty:
        profiles: Profiles = SqlProfiles(connection)
        store: PropertyStore = SqlPropertyStore(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return CreateProperty(profiles, store, audit, app_clock)

    async def provide_update_property(
        connection: Transaction,
    ) -> UpdateProperty:
        profiles: Profiles = SqlProfiles(connection)
        store: PropertyStore = SqlPropertyStore(connection)
        leases: ActiveLeases = SqlActiveLeases(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return UpdateProperty(profiles, store, leases, audit, app_clock)

    async def provide_archive_property(
        connection: Transaction,
    ) -> ArchiveProperty:
        store: PropertyStore = SqlPropertyStore(connection)
        leases: ActiveLeases = SqlActiveLeases(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return ArchiveProperty(store, leases, audit, app_clock)

    async def provide_add_unit(
        connection: Transaction,
    ) -> AddUnit:
        store: PropertyStore = SqlPropertyStore(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return AddUnit(store, audit, app_clock)

    async def provide_update_unit(
        connection: Transaction,
    ) -> UpdateUnit:
        store: PropertyStore = SqlPropertyStore(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return UpdateUnit(store, audit, app_clock)

    async def provide_archive_unit(
        connection: Transaction,
    ) -> ArchiveUnit:
        store: PropertyStore = SqlPropertyStore(connection)
        leases: ActiveLeases = SqlActiveLeases(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return ArchiveUnit(store, leases, audit, app_clock)

    app.include_router(
        properties_api.create_router(
            current_account,
            provide_list_properties,
            provide_create_property,
            provide_update_property,
            provide_archive_property,
            provide_add_unit,
            provide_update_unit,
            provide_archive_unit,
        )
    )

    def renter_store(connection: AsyncConnection) -> RenterStore:
        store: RenterStore = SqlRenterStore(connection, config.field_cipher, config.document_hasher)
        return store

    async def provide_list_renters(
        connection: Transaction,
    ) -> ListRenters:
        return ListRenters(renter_store(connection))

    async def provide_create_renter(
        connection: Transaction,
    ) -> CreateRenter:
        profiles: Profiles = SqlProfiles(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return CreateRenter(profiles, renter_store(connection), audit, app_clock)

    async def provide_update_renter(
        connection: Transaction,
    ) -> UpdateRenter:
        profiles: Profiles = SqlProfiles(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return UpdateRenter(profiles, renter_store(connection), audit, app_clock)

    app.include_router(
        renters_api.create_router(
            current_account, provide_list_renters, provide_create_renter, provide_update_renter
        )
    )

    async def provide_list_leases(
        connection: Transaction,
    ) -> ListLeases:
        leases: LeaseStore = SqlLeaseStore(connection)
        return ListLeases(leases, app_clock)

    async def provide_create_lease(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> CreateLease:
        profiles: Profiles = SqlProfiles(connection)
        properties: PropertyStore = SqlPropertyStore(connection)
        leases: LeaseStore = SqlLeaseStore(connection)
        balances: OpeningBalanceStore = SqlOpeningBalances(connection)
        charges: RentChargeStore = SqlRentCharges(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return CreateLease(
            profiles,
            entitlements,
            properties,
            renter_store(connection),
            leases,
            balances,
            EnsureRentCharges(charges, app_clock),
            audit,
            app_clock,
        )

    app.include_router(
        leases_api.create_router(current_account, provide_list_leases, provide_create_lease)
    )

    async def provide_record_payment(
        connection: Transaction,
    ) -> RecordPayment:
        ledger: LedgerStore = SqlLedger(connection)
        thresholds: CashThresholds = SqlTaxRuleBook(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return RecordPayment(ledger, thresholds, audit, app_clock)

    async def provide_void_payment(
        connection: Transaction,
    ) -> VoidPayment:
        ledger: LedgerStore = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return VoidPayment(ledger, audit, app_clock)

    async def provide_statement(
        connection: Transaction,
    ) -> GetStatement:
        ledger: LedgerStore = SqlLedger(connection)
        return GetStatement(ledger, app_clock)

    app.include_router(
        payments_api.create_router(
            current_account, provide_record_payment, provide_void_payment, provide_statement
        )
    )

    async def provide_adjust_lease(connection: Transaction) -> AdjustLease:
        charges: ChargeStore = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return AdjustLease(charges, audit, app_clock)

    async def provide_correct_rent(connection: Transaction) -> CorrectRent:
        charges: ChargeStore = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return CorrectRent(charges, audit, app_clock)

    async def provide_prior_debt(connection: Transaction) -> RecordPriorDebt:
        leases: LeaseStore = SqlLeaseStore(connection)
        charges: ChargeStore = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return RecordPriorDebt(leases, charges, audit, app_clock)

    async def provide_change_rent(connection: Transaction) -> ChangeRent:
        leases: LeaseStore = SqlLeaseStore(connection)
        periods: ChargedPeriods = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return ChangeRent(leases, periods, audit, app_clock)

    async def provide_set_end_date(connection: Transaction) -> SetEndDate:
        leases: LeaseStore = SqlLeaseStore(connection)
        periods: ChargedPeriods = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return SetEndDate(leases, periods, audit, app_clock)

    async def provide_end_lease(connection: Transaction) -> EndLease:
        leases: LeaseStore = SqlLeaseStore(connection)
        charges: ChargeStore = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return EndLease(leases, charges, audit, app_clock)

    async def provide_void_charge(connection: Transaction) -> VoidCharge:
        charges: ChargeStore = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return VoidCharge(charges, audit, app_clock)

    app.include_router(
        charges_api.create_router(
            current_account,
            provide_adjust_lease,
            provide_correct_rent,
            provide_prior_debt,
            provide_void_charge,
        )
    )
    app.include_router(
        lease_changes_api.create_router(
            current_account, provide_change_rent, provide_set_end_date, provide_end_lease
        )
    )

    link_signer: LinkSigner = HmacLinkSigner(config.tenant_link_keys)

    def tenant_links(connection: AsyncConnection) -> Links:
        store: LinkStore = SqlLinks(connection)
        return Links(store, link_signer, config.public_url)

    async def provide_get_link(connection: Transaction) -> GetLink:
        return GetLink(tenant_links(connection))

    async def provide_issue_link(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> IssueLink:
        audit: AuditLog = SqlAuditLog(connection)
        return IssueLink(tenant_links(connection), entitlements, audit, app_clock)

    async def provide_revoke_link(connection: Transaction) -> RevokeLink:
        store: LinkStore = SqlLinks(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return RevokeLink(store, audit, app_clock)

    app.include_router(
        tenant_links_api.create_router(
            current_account, provide_get_link, provide_issue_link, provide_revoke_link
        )
    )

    async def tenant_access(
        request: Request,
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
        x_tenant_token: Annotated[str, Header()] = "",
    ) -> tenant_portal_api.TenantAccess:
        limiter = PostgresRateLimiter(
            connection, config.rate_limit_key, app_clock, "tenant-portal", TENANT_PORTAL_PER_HOUR
        )
        if not await limiter.allow(request.client.host if request.client else "unknown"):
            return "too_many_requests"
        gate: TenantGate = SqlTenantGate(connection)
        return await OpenPortal(gate, entitlements, app_clock)(x_tenant_token)

    async def provide_tenant_statement(connection: Transaction) -> GetTenantStatement:
        reader: PortalReader = SqlPortalReader(connection)
        ledger: LedgerStore = SqlLedger(connection)
        return GetTenantStatement(reader, GetStatement(ledger, app_clock))

    app.include_router(tenant_portal_api.create_router(tenant_access, provide_tenant_statement))

    async def provide_collections(
        connection: Transaction,
    ) -> GetCollections:
        books: CollectionsStore = SqlLedger(connection)
        return GetCollections(books, app_clock)

    app.include_router(collections_api.create_router(current_account, provide_collections))

    async def provide_list_templates(connection: Transaction) -> ListTemplates:
        store: TemplateStore = SqlTemplateStore(connection)
        return ListTemplates(store)

    async def provide_save_template(connection: Transaction) -> SaveTemplate:
        store: TemplateStore = SqlTemplateStore(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return SaveTemplate(store, audit, app_clock)

    app.include_router(
        templates_api.create_router(current_account, provide_list_templates, provide_save_template)
    )

    async def provide_prepare_reminder(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> PrepareReminder:
        recipients: RecipientStore = SqlRecipientStore(connection)
        ledger: LedgerStore = SqlLedger(connection)
        templates: TemplateStore = SqlTemplateStore(connection)
        log: ReminderLog = SqlReminderLog(connection)
        audit: AuditLog = SqlAuditLog(connection)
        links = tenant_links(connection)
        urls: TenantLinkUrls = LinkInUse(links, IssueLink(links, entitlements, audit, app_clock))
        return PrepareReminder(
            entitlements,
            recipients,
            GetStatement(ledger, app_clock),
            templates,
            urls,
            log,
            app_clock,
        )

    async def provide_last_reminders(connection: Transaction) -> ListLastReminders:
        log: ReminderLog = SqlReminderLog(connection)
        return ListLastReminders(log, app_clock)

    app.include_router(
        reminders_api.create_router(
            current_account, provide_prepare_reminder, provide_last_reminders
        )
    )

    def declarations_with(
        connection: AsyncConnection, entitlements: GetEntitlements, renters: RenterDocuments
    ) -> GetDeclarations:
        profiles: Profiles = SqlProfiles(connection)
        properties: PropertyStore = SqlPropertyStore(connection)
        leases: LeaseStore = SqlLeaseStore(connection)
        books: CollectionsStore = SqlLedger(connection)
        rule_book: TaxRuleBook = SqlTaxRuleBook(connection)
        tax_payments: TaxPaymentStore = SqlTaxPayments(connection)
        return GetDeclarations(
            entitlements,
            profiles,
            properties,
            leases,
            renters,
            books,
            rule_book,
            tax_payments,
            app_clock,
        )

    async def provide_declarations(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> GetDeclarations:
        """With document numbers in clear, only for the 1683 cards and the export."""
        renters: RenterDocuments = SqlRenterStore(
            connection, config.field_cipher, config.document_hasher
        )
        return declarations_with(connection, entitlements, renters)

    async def provide_declaration_totals(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> GetDeclarations:
        renters: RenterDocuments = SqlRenterHolders(connection)
        return declarations_with(connection, entitlements, renters)

    async def provide_upcoming(
        connection: Transaction,
        declarations: Annotated[GetDeclarations, Depends(provide_declaration_totals)],
    ) -> GetUpcomingDue:
        profiles: Profiles = SqlProfiles(connection)
        rule_book: TaxRuleBook = SqlTaxRuleBook(connection)
        return GetUpcomingDue(declarations, profiles, rule_book, app_clock)

    app.include_router(
        declarations_api.create_router(current_account, provide_declarations, provide_upcoming)
    )

    async def provide_export_payments(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> ExportPayments:
        leases: LeaseStore = SqlLeaseStore(connection)
        renters: RenterDocuments = SqlRenterStore(
            connection, config.field_cipher, config.document_hasher
        )
        properties: PropertyStore = SqlPropertyStore(connection)
        ledger: LedgerStore = SqlLedger(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return ExportPayments(entitlements, leases, renters, properties, ledger, audit, app_clock)

    async def provide_export_declarations(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
        declarations: Annotated[GetDeclarations, Depends(provide_declarations)],
    ) -> ExportDeclarations:
        audit: AuditLog = SqlAuditLog(connection)
        return ExportDeclarations(entitlements, declarations, audit, app_clock)

    app.include_router(
        exports_api.create_router(
            current_account, provide_export_payments, provide_export_declarations
        )
    )

    async def provide_record_tax_payment(
        connection: Transaction,
        declarations: Annotated[GetDeclarations, Depends(provide_declaration_totals)],
    ) -> RecordTaxPayment:
        profiles: Profiles = SqlProfiles(connection)
        store: TaxPaymentStore = SqlTaxPayments(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return RecordTaxPayment(profiles, declarations, store, audit, app_clock)

    async def provide_void_tax_payment(
        connection: Transaction,
        entitlements: Annotated[GetEntitlements, Depends(provide_entitlements)],
    ) -> VoidTaxPayment:
        store: TaxPaymentStore = SqlTaxPayments(connection)
        audit: AuditLog = SqlAuditLog(connection)
        return VoidTaxPayment(entitlements, store, audit, app_clock)

    app.include_router(
        tax_payments_api.create_router(
            current_account, provide_record_tax_payment, provide_void_tax_payment
        )
    )

    @app.get("/api/health", responses={503: {"description": "`database_unavailable`"}})
    async def health() -> HealthResponse:
        """Report that the API process is up and the database answers."""
        if not await database_answers(engine):
            raise HTTPException(status_code=503, detail="database_unavailable")
        return HealthResponse(status="ok")

    return app
