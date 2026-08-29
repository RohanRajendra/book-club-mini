"""Result objects for expected failures.

Use cases have failures that are part of the design — a missing book, a reply to
a reply, an oversized body. Returning them keeps the failure set visible in the
signature and keeps TDD assertions direct. Exceptions stay reserved for genuine
faults: network failure, misconfiguration, bugs.

The surface is deliberately small (02-architecture.md §Result objects): `is_ok`,
`unwrap`, `unwrap_err`, `map`. `and_then`, `or_else` and the rest of the
combinator family are not here until something needs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeAlias, TypeVar

from app.domain.errors import DomainError

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E", bound=DomainError)


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    def is_ok(self) -> bool:
        return True

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> DomainError:
        raise ValueError(f"unwrap_err() on Ok({self.value!r})")

    def map(self, fn: Callable[[T], U]) -> "Ok[U]":
        return Ok(fn(self.value))


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def unwrap(self) -> object:
        raise ValueError(f"unwrap() on Err({self.error!r})")

    def unwrap_err(self) -> E:
        return self.error

    def map(self, fn: Callable[[object], object]) -> "Err[E]":
        return self


Result: TypeAlias = Ok[T] | Err[DomainError]
