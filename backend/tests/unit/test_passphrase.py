"""Hashing and checking the one shared passphrase."""

from __future__ import annotations

import pytest

from app.interface.passphrase import ALGORITHM, hash_passphrase, verify_passphrase

RIGHT = "correct horse battery staple"

#: The real cost factor is deliberately slow. These tests are about the shape
#: of the check, not about how long it takes, and 1000 rounds proves the same
#: things in a hundredth of the time.
FAST = {"iterations": 1000}


def stored(passphrase: str = RIGHT, **kwargs) -> str:
    return hash_passphrase(passphrase, **{**FAST, **kwargs})


def test_the_right_passphrase_verifies():
    assert verify_passphrase(RIGHT, stored()) is True


def test_the_wrong_passphrase_does_not():
    assert verify_passphrase("wrong", stored()) is False


def test_an_empty_passphrase_does_not():
    assert verify_passphrase("", stored()) is False


def test_a_passphrase_differing_by_one_character_does_not():
    assert verify_passphrase(RIGHT + " ", stored()) is False


def test_the_same_passphrase_hashes_differently_every_time():
    """A random salt per hash, so a stored value cannot be recognised as the
    same secret someone has seen elsewhere."""
    assert stored() != stored()


def test_both_of_those_still_verify():
    for _ in range(2):
        assert verify_passphrase(RIGHT, stored())


def test_the_stored_form_names_its_algorithm_and_cost():
    algorithm, iterations, salt, digest = stored().split("$")
    assert algorithm == ALGORITHM
    assert int(iterations) == FAST["iterations"]
    assert salt and digest


def test_the_cost_factor_travels_with_the_hash():
    """Raising the iteration count strengthens new hashes without invalidating
    the one already deployed."""
    assert verify_passphrase(RIGHT, stored(iterations=1))
    assert verify_passphrase(RIGHT, stored(iterations=2000))


def test_the_passphrase_is_not_recoverable_from_the_hash():
    assert RIGHT not in stored()


@pytest.mark.parametrize(
    "malformed",
    ["", "not-a-hash", "pbkdf2_sha256$1000", "a$b$c$d", "pbkdf2_sha256$x$c2FsdA$aGFzaA"],
)
def test_a_malformed_hash_verifies_nothing(malformed):
    """A misconfigured deployment. The safe reading of "I cannot tell" is
    "no" — the alternative is an app that lets everyone in when its
    configuration is wrong."""
    assert verify_passphrase(RIGHT, malformed) is False


def test_an_unknown_algorithm_is_refused():
    assert verify_passphrase(RIGHT, stored().replace(ALGORITHM, "md5")) is False


def test_a_hash_that_is_not_a_string_is_refused():
    assert verify_passphrase(RIGHT, None) is False
