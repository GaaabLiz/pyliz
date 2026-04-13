"""Generic collection and argument utility helpers."""

from typing import Sequence, TypeVar

T = TypeVar("T")


def contains_item(item: T, items: Sequence[T]) -> bool:
    """Return ``True`` if ``item`` exists in ``items``."""

    return item in items


def all_not_none(*args: T) -> bool:
    """Return ``True`` if all positional arguments are not ``None``."""

    return all(arg is not None for arg in args)
