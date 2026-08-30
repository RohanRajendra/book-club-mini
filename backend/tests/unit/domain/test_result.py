import pytest

from app.domain.errors import BookNotFound
from app.domain.result import Err, Ok


def test_ok_is_ok_and_unwraps_to_value():
    result = Ok(42)
    assert result.is_ok()
    assert result.unwrap() == 42


def test_err_is_not_ok_and_unwraps_to_error():
    error = BookNotFound("no such book")
    result = Err(error)
    assert not result.is_ok()
    assert result.unwrap_err() is error


def test_unwrap_on_err_raises():
    with pytest.raises(ValueError):
        Err(BookNotFound("no such book")).unwrap()


def test_unwrap_err_on_ok_raises():
    with pytest.raises(ValueError):
        Ok(42).unwrap_err()


def test_map_transforms_ok_and_passes_err_through():
    assert Ok(2).map(lambda value: value * 3).unwrap() == 6

    error = BookNotFound("no such book")
    mapped = Err(error).map(lambda value: value * 3)
    assert mapped.unwrap_err() is error


def test_results_are_frozen():
    with pytest.raises(Exception):
        Ok(1).value = 2
