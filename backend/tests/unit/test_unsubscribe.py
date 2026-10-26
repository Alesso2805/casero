from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid7

import pytest

from casero.identity.application.unsubscribe import Unsubscribe
from casero.identity.domain.email_suppressions import ScheduledEmailKind, Suppression
from casero.identity.infrastructure.unsubscribe import HmacUnsubscribeTokens, unsubscribe_links
from casero.shared.infrastructure.mail import SmtpMailer, SmtpSettings
from casero.shared.kernel.email import Email

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
USER = UUID("01a175b4-8f38-727d-a7dc-40a7a7b30001")
TOKENS = HmacUnsubscribeTokens(b"test-unsubscribe-key")
REPOSITORY = Path(__file__).resolve().parents[3]


def test_a_token_only_fits_its_user_and_kind() -> None:
    token = TOKENS.token(USER, "daily_digest")

    assert TOKENS.valid(USER, "daily_digest", token)
    assert not TOKENS.valid(USER, "tax_reminders", token)
    assert not TOKENS.valid(uuid7(), "daily_digest", token)
    assert not HmacUnsubscribeTokens(b"other-key").valid(USER, "daily_digest", token)


def test_links_point_to_the_page_and_the_one_click_endpoint() -> None:
    links = unsubscribe_links("https://casero.example/", TOKENS, USER, "tax_reminders")
    query = f"u={USER}&k=tax_reminders&t={TOKENS.token(USER, 'tax_reminders')}"

    assert links.page == f"https://casero.example/baja?{query}"
    assert links.one_click == f"https://casero.example/api/public/unsubscribe?{query}"


class FixedClock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> date:
        return NOW.date()


class Users:
    def __init__(self, emails: dict[UUID, str]) -> None:
        self.emails = emails

    async def email_of(self, user_id: UUID) -> str | None:
        return self.emails.get(user_id)


class Store:
    def __init__(self) -> None:
        self.added: list[Suppression] = []

    async def add(self, suppression: Suppression, now: datetime) -> None:
        self.added.append(suppression)

    async def blocks(self, email: str, kind: ScheduledEmailKind | None) -> bool:
        return False


@pytest.mark.anyio
async def test_a_valid_link_suppresses_only_that_kind() -> None:
    store = Store()
    unsubscribe = Unsubscribe(TOKENS, Users({USER: "ana@example.com"}), store, FixedClock())

    assert await unsubscribe(USER, "daily_digest", TOKENS.token(USER, "daily_digest"))
    assert store.added == [Suppression("ana@example.com", "daily_digest", "unsubscribe")]


@pytest.mark.anyio
async def test_a_forged_link_changes_nothing_and_an_unknown_user_is_not_revealed() -> None:
    store = Store()
    unsubscribe = Unsubscribe(TOKENS, Users({}), store, FixedClock())

    assert not await unsubscribe(USER, "daily_digest", "forged")
    assert await unsubscribe(USER, "daily_digest", TOKENS.token(USER, "daily_digest"))
    assert store.added == []


def test_scheduled_emails_carry_one_click_unsubscribe_headers() -> None:
    settings = SmtpSettings("localhost", 25, "none", None, None, "Casero <no-reply@example.com>")
    mailer = SmtpMailer(settings, FixedClock())
    url = "https://casero.example/api/public/unsubscribe?u=1&k=daily_digest&t=x"

    scheduled = mailer.build(Email("ana@example.com", "Resumen", "Hola", unsubscribe_url=url))
    transactional = mailer.build(Email("ana@example.com", "Copia", "Hola"))

    assert scheduled["List-Unsubscribe"] == f"<{url}>"
    assert scheduled["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert transactional["List-Unsubscribe"] is None


@pytest.mark.parametrize("compose", ["docker-compose.yml", "infra/deploy/docker-compose.yml"])
def test_the_api_keeps_no_access_log(compose: str) -> None:
    api_command = next(
        line
        for line in (REPOSITORY / compose).read_text(encoding="utf-8").splitlines()
        if "casero.api:create_app" in line
    )

    assert "--no-access-log" in api_command
