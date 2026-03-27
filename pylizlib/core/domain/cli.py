"""CLI-related domain enums."""

from enum import Enum


class AnsYesNo(Enum):
    """Binary answer enum used by CLI prompts."""

    YES = 1
    NO = 0

    @staticmethod
    def from_string(value: str) -> "AnsYesNo":
        """Parse a string into :class:`AnsYesNo`.

        :param value: Input string (case-insensitive), expected ``yes`` or ``no``.
        :raises ValueError: If value is not recognized.
        """

        normalized = value.strip().lower()
        if normalized == "yes":
            return AnsYesNo.YES
        if normalized == "no":
            return AnsYesNo.NO
        raise ValueError("Invalid value for AnsYesNo")

    def __str__(self) -> str:
        """Return the enum name."""

        return self.name
