from __future__ import annotations

from typing import Iterable


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    """
    Returns a list of unique strings from the input iterable, preserving their original order.

    Args:
        values: An iterable of strings.

    Returns:
        A list of unique strings, with whitespace trimmed, in the order they first appeared.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered
