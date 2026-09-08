from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class MoveType(IntEnum):
    PAD = 0
    SYNC = 1
    LOG = 2
    MODEL = 3


@dataclass(frozen=True)
class AlignmentMove:
    move_type: MoveType
    log_activity: str | None = None
    transition_id: int | None = None

    @classmethod
    def sync(cls, activity: str, transition_id: int) -> "AlignmentMove":
        return cls(MoveType.SYNC, activity, transition_id)

    @classmethod
    def log(cls, activity: str) -> "AlignmentMove":
        return cls(MoveType.LOG, activity, None)

    @classmethod
    def model(cls, transition_id: int) -> "AlignmentMove":
        return cls(MoveType.MODEL, None, transition_id)
