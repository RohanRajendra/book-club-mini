"""The signed cookie that says who is asking.

Hand-rolled rather than pulled from a library, for the same reason the DI
container is: it is thirty lines of standard construction — HMAC-SHA256 over a
payload, compared in constant time — and a dependency here would be a
dependency in the deployment bundle too.

What this is *not*: encryption. The member name travels in the clear, base64ed.
The signature only proves the app issued it. That is the whole requirement — a
browser must not be able to name itself a member the app never agreed to.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

#: Long, because signing out is explicit and re-entering a passphrase every week
#: is the kind of friction that gets a shared secret written on a sticky note.
MAX_AGE_SECONDS = 90 * 24 * 60 * 60

COOKIE_NAME = "bookclub_member"


def issue(member: str, secret: str, *, now: float | None = None) -> str:
    """A token naming `member`, signed with `secret`."""
    payload = _encode(
        json.dumps(
            {"member": member, "issued": int(now if now is not None else time.time())},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    return f"{payload}.{_sign(payload, secret)}"


def read(
    token: str | None,
    secret: str,
    *,
    max_age: int = MAX_AGE_SECONDS,
    now: float | None = None,
) -> str | None:
    """The member the token names, or `None` if it does not hold up.

    One return for every kind of failure — malformed, wrong signature, expired.
    A caller that could tell them apart would be tempted to say which, and
    "that signature is wrong" is a sentence only an attacker benefits from.
    """
    if not token or "." not in token:
        return None

    payload, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        return None

    try:
        claims = json.loads(_decode(payload))
        member = claims["member"]
        issued = int(claims["issued"])
    except (ValueError, KeyError, TypeError):
        return None

    if not isinstance(member, str) or not member:
        return None

    age = (now if now is not None else time.time()) - issued
    # A token issued in the future is a clock that disagrees, not a valid
    # session, and treating it as fresh would make it outlive its own expiry.
    if age < 0 or age > max_age:
        return None
    return member


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return _encode(digest)


def _encode(raw: bytes) -> str:
    """URL-safe base64 without padding, so the value is cookie-clean."""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
