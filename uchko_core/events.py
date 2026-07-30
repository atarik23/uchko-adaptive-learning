from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal, Optional
import time
import uuid

EventType = Literal["start", "end", "solve", "hint", "explanation"]


@dataclass(frozen=True)
class Event:
    """
    Core event schema for Uchko.

    Session correctness:
    - session_id is mandatory for all events.
    - start/end events use sentinel values for skill/question/difficulty.
    """
    event_id: str
    student_id: str
    session_id: str
    timestamp: float  # unix seconds
    event_type: EventType

    # For non-session events, these describe the practice item.
    # For start/end, they are sentinels.
    skill_id: str
    question_id: str
    difficulty: int

    # Solve-only fields
    correct: Optional[int] = None          # 1/0 for solve, None otherwise
    response_time_ms: Optional[int] = None # for solve, None otherwise
    attempt_number: Optional[int] = None   # for solve, None otherwise

    # Reserved for future extensions
    meta: Optional[dict] = None

    def to_dict(self) -> dict:
        # Keep schema stable. We keep None fields so Parquet stays consistent.
        return asdict(self)


def _new_id(prefix: str = "E") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


# ----------------------------
# Session lifecycle events
# ----------------------------
def make_start_event(student_id: str, session_id: str) -> Event:
    return Event(
        event_id=_new_id("E"),
        student_id=student_id,
        session_id=session_id,
        timestamp=time.time(),
        event_type="start",
        skill_id="__session__",
        question_id="__session__",
        difficulty=0,
        meta=None,
    )


def make_end_event(student_id: str, session_id: str) -> Event:
    return Event(
        event_id=_new_id("E"),
        student_id=student_id,
        session_id=session_id,
        timestamp=time.time(),
        event_type="end",
        skill_id="__session__",
        question_id="__session__",
        difficulty=0,
        meta=None,
    )


# ----------------------------
# Practice interaction events
# ----------------------------
def make_solve_event(
    *,
    student_id: str,
    session_id: str,
    skill_id: str,
    question_id: str,
    difficulty: int,
    correct: int,
    response_time_ms: int,
    attempt_number: int,
    meta: Optional[dict] = None,
) -> Event:
    return Event(
        event_id=_new_id("E"),
        student_id=student_id,
        session_id=session_id,
        timestamp=time.time(),
        event_type="solve",
        skill_id=skill_id,
        question_id=question_id,
        difficulty=int(difficulty),
        correct=int(correct),
        response_time_ms=int(response_time_ms),
        attempt_number=int(attempt_number),
        meta=meta,
    )


def make_hint_event(
    *,
    student_id: str,
    session_id: str,
    skill_id: str,
    question_id: str,
    difficulty: int,
    meta: Optional[dict] = None,
) -> Event:
    return Event(
        event_id=_new_id("E"),
        student_id=student_id,
        session_id=session_id,
        timestamp=time.time(),
        event_type="hint",
        skill_id=skill_id,
        question_id=question_id,
        difficulty=int(difficulty),
        meta=meta,
    )


def make_explanation_event(
    *,
    student_id: str,
    session_id: str,
    skill_id: str,
    question_id: str,
    difficulty: int,
    meta: Optional[dict] = None,
) -> Event:
    return Event(
        event_id=_new_id("E"),
        student_id=student_id,
        session_id=session_id,
        timestamp=time.time(),
        event_type="explanation",
        skill_id=skill_id,
        question_id=question_id,
        difficulty=int(difficulty),
        meta=meta,
    )
