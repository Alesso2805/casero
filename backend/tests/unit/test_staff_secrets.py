import re

import pyotp

from casero.admin.infrastructure.staff import HashedRecoveryCodes, PyotpSecondFactor

RECOVERY_CODE = re.compile(r"[0-9a-f]{5}(-[0-9a-f]{5}){3}")


def test_a_recovery_code_is_easy_to_copy_and_only_its_hash_is_kept() -> None:
    code, code_hash = HashedRecoveryCodes().new()

    assert RECOVERY_CODE.fullmatch(code)
    assert code_hash == HashedRecoveryCodes().hash(code)
    assert code.replace("-", "") not in code_hash


def test_a_recovery_code_is_recognized_however_it_was_typed() -> None:
    code, code_hash = HashedRecoveryCodes().new()
    codes = HashedRecoveryCodes()

    assert codes.hash(f"  {code.upper()} ") == code_hash
    assert codes.hash(code.replace("-", " ")) == code_hash
    assert codes.hash(code.replace("-", "")) == code_hash


def test_each_recovery_code_is_new() -> None:
    assert HashedRecoveryCodes().new() != HashedRecoveryCodes().new()


def test_an_authenticator_app_can_read_the_enrollment_link() -> None:
    second_factor = PyotpSecondFactor()
    secret = second_factor.new_secret()

    totp = pyotp.parse_uri(second_factor.enrollment_uri(secret, "ana@example.com"))

    assert isinstance(totp, pyotp.TOTP)
    assert totp.secret == secret
    assert (totp.interval, totp.digits) == (30, 6)
