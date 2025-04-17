from typing import Generic, TypeVar, Optional

T = TypeVar('T')


class Operation(Generic[T]):
    def __init__(self, payload: Optional[T] = None, status: bool = False, error: Optional[str] = None):
        self.payload = payload
        self.status = status
        self.error = error

    # @classmethod
    # def is_ok(cls, operation: 'Operation[T]') -> bool:
    #     return operation.status

    def is_op_ok(self) -> bool:
        return self.status

    def __str__(self):
        return f"Operation(status={self.status}, payload={self.payload}, error={self.error})"

