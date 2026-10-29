from datetime import UTC, date, datetime

from casero.tax.domain.after_declaring import AfterDeclaring, PaidDeclaration, after_declaring

TODAY = date(2026, 11, 20)
DUE = date(2026, 11, 19)


def paid(base: int, amount: int, day: int) -> PaidDeclaration:
    return PaidDeclaration(base, amount, datetime(2026, 11, day, 15, tzinfo=UTC))


def test_without_a_payment_only_a_passed_due_date_with_tax_needs_a_text() -> None:
    assert after_declaring(80_000, 4_000, [], False, DUE, TODAY) == AfterDeclaring("overdue_unpaid")
    assert after_declaring(80_000, 4_000, [], False, TODAY, TODAY) is None
    assert after_declaring(80_000, 4_000, [], False, None, TODAY) is None
    assert after_declaring(0, 0, [], False, DUE, TODAY) is None


def test_collecting_more_after_paying_tells_both_differences() -> None:
    assert after_declaring(100_000, 5_000, [paid(80_000, 4_000, 10)], False, DUE, TODAY) == (
        AfterDeclaring("up", 20_000, 1_000)
    )


def test_the_latest_payment_is_what_was_last_declared() -> None:
    rectified = [paid(100_000, 1_000, 15), paid(80_000, 4_000, 10)]

    assert after_declaring(100_000, 5_000, rectified, False, DUE, TODAY) is None
    assert after_declaring(90_000, 4_500, rectified, False, DUE, TODAY) == AfterDeclaring(
        "down", 10_000
    )


def test_a_base_up_with_tax_already_covered_owes_nothing_more() -> None:
    assert after_declaring(80_100, 4_000, [paid(80_000, 4_000, 10)], False, DUE, TODAY) == (
        AfterDeclaring("up", 100, 0)
    )


def test_a_payment_with_another_document_comes_first() -> None:
    assert after_declaring(100_000, 5_000, [], True, DUE, TODAY) == AfterDeclaring(
        "document_changed"
    )
