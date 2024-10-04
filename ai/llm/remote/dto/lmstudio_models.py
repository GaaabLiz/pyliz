import json
from typing import List, Any, Dict

class LmStudioModel:
    def __init__(self, id: str, object_type: str, owned_by: str):
        self.id = id
        self.object_type = object_type
        self.owned_by = owned_by

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LmStudioModel':
        return cls(
            id=data['id'],
            object_type=data['object'],
            owned_by=data['owned_by']
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'object': self.object_type,
            'owned_by': self.owned_by
        }

class LmStudioModelList:
    def __init__(self, data: List[LmStudioModel], object_type: str):
        self.data = data
        self.object_type = object_type

    @classmethod
    def from_json(cls, json_string: str) -> 'LmStudioModelList':
        json_data = json.loads(json_string)
        models = [LmStudioModel.from_dict(item) for item in json_data['data']]
        return cls(data=models, object_type=json_data['object'])

    def to_json(self) -> str:
        return json.dumps({
            'data': [model.to_dict() for model in self.data],
            'object': self.object_type
        })