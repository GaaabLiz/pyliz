from typing import TypeVar, List

T = TypeVar('T')


def contains_item(item: T, items: List[T]) -> bool:
    return item in items


def all_not_none(*args: T) -> bool:
    return all(arg is not None for arg in args)
