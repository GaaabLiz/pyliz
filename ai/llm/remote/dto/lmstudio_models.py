from typing import List
from typing import Any
from dataclasses import dataclass
import json


@dataclass
class LmModel:
    id: str
    object: str
    owned_by: str

    @staticmethod
    def from_dict(obj: Any) -> 'LmModel':
        _id = str(obj.get("id"))
        _object = str(obj.get("object"))
        _owned_by = str(obj.get("owned_by"))
        return LmModel(_id, _object, _owned_by)


@dataclass
class LmStudioModelResult:
    data: List[LmModel]
    object: str

    @staticmethod
    def from_dict(obj: Any) -> 'LmStudioModelResult':
        _data = [LmModel.from_dict(y) for y in obj.get("data")]
        _object = str(obj.get("object"))
        return LmStudioModelResult(_data, _object)