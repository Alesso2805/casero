from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from casero.shared.infrastructure.crypto import (
    DocumentHasher,
    EnvelopeError,
    FieldCipher,
    b64encode,
    field_context,
    parse_keys,
)
from casero.shared.infrastructure.settings import MIN_SECRET_KEY_BYTES, secret_key

OLD_KEY, NEW_KEY = bytes(32), bytes(range(32))
CIPHER = FieldCipher({"k1": OLD_KEY}, "k1")
ANA = field_context("renters", "doc_enc", UUID(int=1), UUID(int=10))
LUIS = field_context("renters", "doc_enc", UUID(int=2), UUID(int=10))
ANOTHER_RENTER = field_context("renters", "doc_enc", UUID(int=1), UUID(int=11))


@given(st.text(max_size=40))
def test_a_value_opens_in_its_own_context(plaintext: str) -> None:
    assert CIPHER.decrypt(CIPHER.encrypt(plaintext, ANA), ANA) == plaintext


def test_the_envelope_carries_version_key_nonce_and_ciphertext() -> None:
    envelope = CIPHER.encrypt("12345678", ANA)
    version, key_id, nonce, sealed = envelope.split(":")

    assert (version, key_id) == ("v1", "k1")
    assert "12345678" not in envelope
    assert CIPHER.encrypt("12345678", ANA) != envelope
    assert nonce
    assert sealed


@pytest.mark.parametrize(
    "context",
    [
        LUIS,
        ANOTHER_RENTER,
        field_context("accounts", "deletion_contact_enc", UUID(int=1), UUID(int=1)),
    ],
)
def test_a_value_does_not_open_in_another_row_or_column(context: str) -> None:
    with pytest.raises(EnvelopeError):
        CIPHER.decrypt(CIPHER.encrypt("12345678", ANA), context)


def test_a_tampered_or_unknown_envelope_is_rejected() -> None:
    version, key_id, nonce, sealed = CIPHER.encrypt("12345678", ANA).split(":")
    tampered = ":".join((version, key_id, nonce, b64encode(b"x" * 24)))

    for envelope in (tampered, f"v2:{key_id}:{nonce}:{sealed}", f"v1:k9:{nonce}:{sealed}", "x"):
        with pytest.raises(EnvelopeError):
            CIPHER.decrypt(envelope, ANA)


def test_after_rotation_old_values_still_open_and_new_ones_use_the_new_key() -> None:
    old = CIPHER.encrypt("12345678", ANA)
    rotated = FieldCipher({"k1": OLD_KEY, "k2": NEW_KEY}, "k2")

    assert rotated.decrypt(old, ANA) == "12345678"
    assert rotated.encrypt("12345678", ANA).split(":")[1] == "k2"


@pytest.mark.parametrize(
    ("keys", "active"),
    [({"k1": bytes(16)}, "k1"), ({"k1": OLD_KEY}, "k2"), ({"k:1": OLD_KEY}, "k:1")],
)
def test_bad_key_sets_are_refused_at_startup(keys: dict[str, bytes], active: str) -> None:
    with pytest.raises(ValueError, match="key"):
        FieldCipher(keys, active)


def test_keys_are_read_from_the_environment_format() -> None:
    value = f"k1:{b64encode(OLD_KEY)}, k2:{b64encode(NEW_KEY)}"

    assert parse_keys(value) == {"k1": OLD_KEY, "k2": NEW_KEY}


def test_the_document_hmac_depends_on_the_type_and_the_number() -> None:
    hasher = DocumentHasher(NEW_KEY)

    assert hasher.digest("dni", "12345678") == hasher.digest("dni", "12345678")
    assert hasher.digest("dni", "12345678") != hasher.digest("ce", "12345678")
    assert hasher.digest("dni", "12345678") != DocumentHasher(OLD_KEY).digest("dni", "12345678")


def test_a_short_hmac_key_is_refused() -> None:
    with pytest.raises(ValueError, match="at least"):
        DocumentHasher(bytes(16))


@pytest.mark.parametrize(
    ("value", "valid"), [("x" * MIN_SECRET_KEY_BYTES, True), ("email_hash_dev", False)]
)
def test_hmac_keys_from_the_environment_need_32_bytes(value: str, valid: bool) -> None:
    env = {"CASERO_EMAIL_HASH_KEY": value}

    if valid:
        assert secret_key(env, "CASERO_EMAIL_HASH_KEY") == value.encode()
    else:
        with pytest.raises(ValueError, match="at least 32 bytes"):
            secret_key(env, "CASERO_EMAIL_HASH_KEY")
