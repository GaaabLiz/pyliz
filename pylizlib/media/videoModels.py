from dataclasses import dataclass
from enum import Enum

import numpy as np


class SceneType(Enum):
    STATIC = "static"
    ACTION = "action"
    TRANSITION = "transition"


@dataclass
class Frame:
    image: np.ndarray
    timestamp: float
    scene_type: SceneType
    difference_score: float = 0.0