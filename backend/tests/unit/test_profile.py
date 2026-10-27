from datetime import UTC, datetime
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from casero.accounts.application.context import AccountContext
from casero.accounts.application.profile import ProfileChange, ProfileView, UpdateProfile
from casero.accounts.domain.profile import Profile, RucGroup, is_valid_ruc, ruc_group
from casero.shared.kernel.audit import AuditEntry

NOW = datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
CONTEXT = AccountContext(UUID(int=1), UUID(int=2))
SUNAT_RUC = "20131312955"
EMPTY = Profile("Ana", "person", None, None, False)


@pytest.mark.parametrize("ruc", [SUNAT_RUC, "20100047218"])
def test_real_rucs_pass_the_check_digit(ruc: str) -> None:
    assert is_valid_ruc(ruc)


@pytest.mark.parametrize(
    "ruc", ["20131312954", "2013131295", "201313129550", "2013131295a", "\uff120131312955", ""]
)
def test_malformed_rucs_are_rejected(ruc: str) -> None:
    assert not is_valid_ruc(ruc)


@given(st.text(alphabet="0123456789", min_size=10, max_size=10))
def test_exactly_one_last_digit_completes_a_ruc(first_ten: str) -> None:
    assert sum(is_valid_ruc(first_ten + digit) for digit in "0123456789") == 1


@pytest.mark.parametrize(
    ("last_digit", "group"),
    [
        ("0", "0"),
        ("1", "1"),
        ("2", "2-3"),
        ("3", "2-3"),
        ("4", "4-5"),
        ("5", "4-5"),
        ("6", "6-7"),
        ("7", "6-7"),
        ("8", "8-9"),
        ("9", "8-9"),
    ],
)
def test_the_schedule_group_follows_the_last_digit(last_digit: str, group: RucGroup) -> None:
    assert ruc_group("2013131295" + last_digit, good_taxpayer=False) == group


def test_good_taxpayers_have_their_own_group() -> None:
    assert ruc_group(SUNAT_RUC, good_taxpayer=True) == "bc"


class Clock:
    def now(self) -> datetime:
        return NOW

    def today_lima(self) -> None:
        raise AssertionError("not used")


class Profiles:
    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self.saved: list[Profile] = []

    async def current(self) -> Profile:
        return self.profile

    async def lock_current(self) -> Profile:
        return self.profile

    async def save(self, account_id: UUID, profile: Profile) -> None:
        assert account_id == CONTEXT.account_id
        self.saved.append(profile)


class Holdings:
    def __init__(self, any_property: bool) -> None:
        self._any_property = any_property

    async def any_property(self) -> bool:
        return self._any_property


class Audit:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


def change(**overrides: object) -> ProfileChange:
    values: dict[str, object] = {
        "display_name": "Ana",
        "taxpayer_kind": "person",
        "ruc": None,
        "good_taxpayer": False,
        "daily_digest": False,
    }
    return ProfileChange(**{**values, **overrides})  # type: ignore[arg-type]


def update_profile(profiles: Profiles, audit: Audit, any_property: bool = False) -> UpdateProfile:
    return UpdateProfile(profiles, Holdings(any_property), audit, Clock())  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_saving_a_ruc_derives_its_group_and_audits_only_field_names() -> None:
    profiles, audit = Profiles(EMPTY), Audit()

    result = await update_profile(profiles, audit)(CONTEXT, change(ruc=SUNAT_RUC))

    saved = Profile("Ana", "person", SUNAT_RUC, "4-5", False)
    assert result == ProfileView(saved, declarant_locked=False)
    assert profiles.saved == [saved]
    [entry] = audit.entries
    assert (entry.action, entry.changed_fields, entry.at) == (
        "account.profile_updated",
        ("ruc", "ruc_group"),
        NOW,
    )
    assert (entry.account_id, entry.actor_user_id) == (CONTEXT.account_id, CONTEXT.user_id)


@pytest.mark.anyio
async def test_an_invalid_ruc_changes_nothing() -> None:
    profiles, audit = Profiles(EMPTY), Audit()

    result = await update_profile(profiles, audit)(CONTEXT, change(ruc="20131312954"))

    assert result == "invalid_ruc"
    assert (profiles.saved, audit.entries) == ([], [])


@pytest.mark.anyio
async def test_saving_the_same_profile_writes_nothing() -> None:
    profiles, audit = Profiles(EMPTY), Audit()

    result = await update_profile(profiles, audit)(CONTEXT, change())

    assert result == ProfileView(EMPTY, declarant_locked=False)
    assert (profiles.saved, audit.entries) == ([], [])


@pytest.mark.anyio
async def test_without_a_ruc_there_is_no_group_even_for_a_good_taxpayer() -> None:
    profiles = Profiles(Profile("Ana", "person", SUNAT_RUC, "bc", False))

    result = await update_profile(profiles, Audit())(CONTEXT, change(good_taxpayer=True))

    assert result == ProfileView(EMPTY, declarant_locked=False)


@pytest.mark.anyio
async def test_the_declarant_type_is_locked_once_the_account_has_properties() -> None:
    profiles, audit = Profiles(EMPTY), Audit()

    result = await update_profile(profiles, audit, any_property=True)(
        CONTEXT, change(taxpayer_kind="estate")
    )

    assert result == "declarant_locked"
    assert (profiles.saved, audit.entries) == ([], [])


@pytest.mark.anyio
async def test_the_rest_of_the_profile_stays_editable_with_properties() -> None:
    profiles = Profiles(EMPTY)

    result = await update_profile(profiles, Audit(), any_property=True)(
        CONTEXT, change(ruc=SUNAT_RUC)
    )

    assert result == ProfileView(
        Profile("Ana", "person", SUNAT_RUC, "4-5", False), declarant_locked=True
    )
