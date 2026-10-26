from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from casero.identity.application.email_suppressions import SuppressionStore
from casero.identity.application.sessions import PasswordHasher, SessionStore
from casero.identity.domain.account_emails import (
    RESET_LIFETIME,
    VERIFICATION_LIFETIME,
    TokenPurpose,
    password_reset_email,
    verification_email,
)
from casero.identity.domain.email_suppressions import normalize_email
from casero.identity.domain.sessions import is_acceptable_password
from casero.shared.kernel.clock import Clock
from casero.shared.kernel.email import Email, MailDeliveryError
from casero.shared.kernel.ids import new_id


@dataclass(frozen=True)
class AccountUser:
    user_id: UUID
    email: str
    email_verified: bool


class AccountUsers(Protocol):
    async def by_id(self, user_id: UUID) -> AccountUser | None: ...

    async def by_email(self, email: str) -> AccountUser | None: ...

    async def mark_verified(self, user_id: UUID, now: datetime) -> None: ...

    async def set_password_hash(self, user_id: UUID, password_hash: str) -> None: ...


class EmailTokens(Protocol):
    def new(self) -> tuple[str, bytes]: ...

    def hash(self, token: str) -> bytes: ...


class EmailTokenStore(Protocol):
    async def create(
        self,
        token_id: UUID,
        user_id: UUID,
        purpose: TokenPurpose,
        token_hash: bytes,
        expires_at: datetime,
    ) -> None: ...

    async def consume(
        self, token_hash: bytes, purpose: TokenPurpose, now: datetime
    ) -> UUID | None: ...


class AccountMailer(Protocol):
    async def send(self, email: Email) -> None: ...


class EmailRateLimiter(Protocol):
    async def allow(self, subject: str) -> bool: ...


SendOutcome = Literal["sent", "verified", "limited", "suppressed", "failed"]


@dataclass(frozen=True)
class AccountLinks:
    public_url: str

    def verification(self, token: str) -> str:
        return f"{self.public_url.rstrip('/')}/verificar#token={token}"

    def password_reset(self, token: str) -> str:
        return f"{self.public_url.rstrip('/')}/nueva-clave#token={token}"


@dataclass(frozen=True)
class AccountEmailSender:
    """Account emails go out during the request: only the API can read email_tokens, and the
    token in clear exists only here (ADR-0009, amendment of CS-05)."""

    tokens: EmailTokens
    store: EmailTokenStore
    suppressions: SuppressionStore
    mailer: AccountMailer
    links: AccountLinks
    clock: Clock

    async def send(self, user: AccountUser, purpose: TokenPurpose) -> SendOutcome:
        if await self.suppressions.blocks(user.email, None):
            return "suppressed"
        token, token_hash = self.tokens.new()
        now = self.clock.now()
        lifetime = VERIFICATION_LIFETIME if purpose == "verify_email" else RESET_LIFETIME
        await self.store.create(new_id(), user.user_id, purpose, token_hash, now + lifetime)
        email = (
            verification_email(user.email, self.links.verification(token))
            if purpose == "verify_email"
            else password_reset_email(user.email, self.links.password_reset(token))
        )
        try:
            await self.mailer.send(email)
        except MailDeliveryError:
            return "failed"
        return "sent"


@dataclass(frozen=True)
class SendVerification:
    users: AccountUsers
    limiter: EmailRateLimiter
    sender: AccountEmailSender

    async def __call__(self, user_id: UUID) -> SendOutcome:
        user = await self.users.by_id(user_id)
        if user is None:
            return "failed"
        if user.email_verified:
            return "verified"
        if not await self.limiter.allow(str(user_id)):
            return "limited"
        return await self.sender.send(user, "verify_email")


@dataclass(frozen=True)
class ConfirmEmail:
    users: AccountUsers
    store: EmailTokenStore
    tokens: EmailTokens
    clock: Clock

    async def __call__(self, token: str) -> bool:
        now = self.clock.now()
        user_id = await self.store.consume(self.tokens.hash(token), "verify_email", now)
        if user_id is None:
            return False
        await self.users.mark_verified(user_id, now)
        return True


@dataclass(frozen=True)
class RequestPasswordReset:
    """Always answers the same way, so it never reveals whether an email has an account."""

    users: AccountUsers
    ip_limiter: EmailRateLimiter
    email_limiter: EmailRateLimiter
    sender: AccountEmailSender

    async def __call__(self, email: str, client: str) -> Literal["accepted", "limited"]:
        if not await self.ip_limiter.allow(client):
            return "limited"
        email = normalize_email(email)
        user = await self.users.by_email(email)
        if user is not None and await self.email_limiter.allow(email):
            await self.sender.send(user, "reset_password")
        return "accepted"


@dataclass(frozen=True)
class ResetPassword:
    users: AccountUsers
    store: EmailTokenStore
    tokens: EmailTokens
    hasher: PasswordHasher
    sessions: SessionStore
    clock: Clock

    async def __call__(self, token: str, password: str) -> Literal["done", "invalid", "weak"]:
        if not is_acceptable_password(password):
            return "weak"
        now = self.clock.now()
        user_id = await self.store.consume(self.tokens.hash(token), "reset_password", now)
        if user_id is None:
            return "invalid"
        await self.users.set_password_hash(user_id, await self.hasher.hash(password))
        await self.users.mark_verified(user_id, now)
        await self.sessions.revoke_all(user_id, now)
        return "done"
