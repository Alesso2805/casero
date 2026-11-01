from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from casero.leases.domain.tools import LeaseTools, leases_keeping_tools, tools_changes

AT = datetime(2026, 10, 1, 15, tzinfo=UTC)


def lease(number: int, enabled: bool = True) -> LeaseTools:
    return LeaseTools(UUID(int=number), AT + timedelta(days=number), enabled)


def ids(*numbers: int) -> set[UUID]:
    return {UUID(int=number) for number in numbers}


def test_within_the_limit_everyone_keeps_the_tools_even_if_they_lost_them() -> None:
    assert leases_keeping_tools([lease(1, False), lease(2)], 2) == ids(1, 2)


def test_over_the_limit_the_oldest_keep_them_by_default() -> None:
    assert leases_keeping_tools([lease(3), lease(1), lease(2)], 1) == ids(1)


def test_the_landlords_choice_goes_before_age() -> None:
    assert leases_keeping_tools([lease(1, False), lease(2, False), lease(3)], 1) == ids(3)


def test_a_short_choice_is_filled_with_the_oldest() -> None:
    assert leases_keeping_tools([lease(1, False), lease(2, False), lease(3)], 2) == ids(1, 3)


def test_only_what_differs_changes() -> None:
    leases = [lease(1), lease(2, False), lease(3, False)]

    assert tools_changes(leases, ids(1, 2)) == ([UUID(int=2)], [])
    assert tools_changes(leases, ids(2)) == ([UUID(int=2)], [UUID(int=1)])


@given(st.lists(st.booleans(), max_size=8), st.integers(min_value=1, max_value=10))
def test_exactly_the_limit_keeps_them_and_a_second_pass_changes_nothing(
    flags: list[bool], limit: int
) -> None:
    leases = [lease(number, enabled) for number, enabled in enumerate(flags)]

    keep = leases_keeping_tools(leases, limit)
    settled = [LeaseTools(item.lease_id, item.created_at, item.lease_id in keep) for item in leases]

    assert len(keep) == min(len(leases), limit)
    assert leases_keeping_tools(settled, limit) == keep
    assert tools_changes(settled, keep) == ([], [])
