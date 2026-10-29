import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest

from casero.shared.infrastructure.crypto import HmacKeyring
from casero.tenant_portal.application.links import TenantLink
from casero.tenant_portal.domain.links import link_url, token_hash
from casero.tenant_portal.infrastructure.links import HmacLinkSigner

KEYRING = HmacKeyring({"old": bytes(range(32)), "new": bytes(range(32, 64))}, "new")
SIGNER = HmacLinkSigner(KEYRING)
CREATED = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


def link(nonce: bytes, key_id: str = "new") -> TenantLink:
    return TenantLink(UUID(int=1), UUID(int=2), nonce, key_id, CREATED, None)


def test_the_token_is_rebuilt_from_what_is_stored_and_changes_with_the_nonce() -> None:
    token = SIGNER.token(link(b"a" * 16))

    assert SIGNER.token(link(b"a" * 16)) == token
    assert SIGNER.token(link(b"b" * 16)) != token
    assert SIGNER.token(link(b"a" * 16, key_id="old")) != token
    assert "=" not in token


def test_new_links_use_the_active_key_and_a_fresh_nonce() -> None:
    (nonce, key_id), (other_nonce, _) = SIGNER.new_secret(), SIGNER.new_secret()

    assert (len(nonce), key_id) == (16, "new")
    assert nonce != other_nonce


def test_only_the_hash_of_the_token_is_kept_and_the_token_rides_in_the_fragment() -> None:
    assert token_hash("abc") == hashlib.sha256(b"abc").digest()
    assert link_url("https://casero.example/", "abc") == "https://casero.example/i#t=abc"


def test_a_short_link_key_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HmacKeyring({"k1": b"short"}, "k1")
