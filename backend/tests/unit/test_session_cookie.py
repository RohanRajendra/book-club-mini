"""The signed cookie that says who is asking.

Hand-rolled signing earns a thorough test. Every one of these is a way a
browser could try to name itself a member the app never agreed to.
"""

from __future__ import annotations

import base64
import json

from app.interface.session import MAX_AGE_SECONDS, issue, read

SECRET = "a-long-random-value"
NOW = 1_700_000_000.0


def test_a_token_reads_back_as_the_member_it_names():
    assert read(issue("Ada", SECRET, now=NOW), SECRET, now=NOW) == "Ada"


def test_a_token_signed_with_another_secret_is_refused():
    """The whole point. Rotating SESSION_SECRET must invalidate every session,
    which is also how a leaked cookie is revoked."""
    assert read(issue("Ada", "other-secret", now=NOW), SECRET, now=NOW) is None


def test_a_tampered_payload_is_refused():
    """Renaming yourself in the payload is the obvious attack: the member name
    travels in the clear and is trivially editable."""
    token = issue("Ada", SECRET, now=NOW)
    payload, _, signature = token.partition(".")
    forged = base64.urlsafe_b64encode(
        json.dumps({"member": "Grace", "issued": int(NOW)}).encode()
    ).decode().rstrip("=")
    assert read(f"{forged}.{signature}", SECRET, now=NOW) is None


def test_a_tampered_signature_is_refused():
    token = issue("Ada", SECRET, now=NOW)
    flipped = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert read(flipped, SECRET, now=NOW) is None


def test_an_unsigned_payload_is_refused():
    """A signature the app never produced, including none at all."""
    payload = issue("Ada", SECRET, now=NOW).partition(".")[0]
    assert read(payload, SECRET, now=NOW) is None
    assert read(f"{payload}.", SECRET, now=NOW) is None


def test_nothing_at_all_is_refused():
    for token in (None, "", ".", "not-a-token"):
        assert read(token, SECRET, now=NOW) is None


def test_a_token_at_exactly_the_maximum_age_still_reads():
    token = issue("Ada", SECRET, now=NOW)
    assert read(token, SECRET, now=NOW + MAX_AGE_SECONDS) == "Ada"


def test_a_token_one_second_past_the_maximum_age_is_refused():
    token = issue("Ada", SECRET, now=NOW)
    assert read(token, SECRET, now=NOW + MAX_AGE_SECONDS + 1) is None


def test_a_token_issued_in_the_future_is_refused():
    """A clock that disagrees, not a valid session. Accepting it would let a
    token outlive its own expiry by however far ahead it claims to be."""
    token = issue("Ada", SECRET, now=NOW + 60)
    assert read(token, SECRET, now=NOW) is None


def test_a_payload_that_is_not_json_is_refused():
    payload = base64.urlsafe_b64encode(b"not json").decode().rstrip("=")
    from app.interface.session import _sign

    assert read(f"{payload}._", SECRET, now=NOW) is None
    assert read(f"{payload}.{_sign(payload, SECRET)}", SECRET, now=NOW) is None


def test_a_payload_missing_its_claims_is_refused():
    from app.interface.session import _sign

    for claims in ({}, {"member": "Ada"}, {"issued": int(NOW)}, {"member": "", "issued": int(NOW)}):
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        assert read(f"{payload}.{_sign(payload, SECRET)}", SECRET, now=NOW) is None


def test_a_member_that_is_not_a_string_is_refused():
    """`{"member": 0}` would otherwise sail through and compare unequal to
    every roster entry, which is a 401 by accident rather than by rule."""
    from app.interface.session import _sign

    payload = (
        base64.urlsafe_b64encode(json.dumps({"member": 0, "issued": int(NOW)}).encode())
        .decode()
        .rstrip("=")
    )
    assert read(f"{payload}.{_sign(payload, SECRET)}", SECRET, now=NOW) is None


def test_a_token_carries_no_padding_so_it_is_cookie_safe():
    assert "=" not in issue("Ada", SECRET, now=NOW)
