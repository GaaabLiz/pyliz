"""Generic operation result container."""

from typing import Generic, TypeVar, Optional

T = TypeVar('T')


class Operation(Generic[T]):
    """Represent the result of an operation.

    :param payload: Optional result payload.
    :param status: ``True`` when operation completed successfully.
    :param error: Optional error message.
    """

    def __init__(self, payload: Optional[T] = None, status: bool = False, error: Optional[str] = None):
        self.payload = payload
        self.status = status
        self.error = error

    def is_op_ok(self) -> bool:
        """Return operation success state."""

        return self.status

    def __str__(self) -> str:
        """Return a readable string representation."""

        return f"Operation(status={self.status}, payload={self.payload}, error={self.error})"

