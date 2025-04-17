
from enum import Enum


class AnsYesNo(Enum):
    YES = 1
    NO = 0

    @staticmethod
    def from_string(value):
        if value.lower() == 'yes':
            return AnsYesNo.YES
        elif value.lower() == 'no':
            return AnsYesNo.NO
        else:
            raise ValueError('Invalid value for AnsYesNo')

    def __str__(self):
        return self.name
