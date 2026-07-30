from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .events import Event


DEFAULT_EVENTS_PATH = Path("data/cache/events.parquet")


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_events(events: Iterable[Event], events_path: Path = DEFAULT_EVENTS_PATH) -> None:
    """
    Append events to a Parquet file. Creates the file if it doesn't exist.
    Uses pandas for simplicity (good enough for demo scale).
    """
    ensure_parent_dir(events_path)

    rows = [e.to_dict() for e in events]
    if not rows:
        return

    df_new = pd.DataFrame(rows)

    if events_path.exists():
        df_old = pd.read_parquet(events_path)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    # keep stable ordering for sanity
    df_all = df_all.sort_values(["student_id", "timestamp"], kind="mergesort")
    df_all.to_parquet(events_path, index=False)


def append_event(event: Event, events_path: Path = DEFAULT_EVENTS_PATH) -> None:
    append_events([event], events_path=events_path)


def load_events(events_path: Path = DEFAULT_EVENTS_PATH, student_id: Optional[str] = None) -> pd.DataFrame:
    """
    Load events. If student_id is provided, filter to that student.
    Returns empty DF if file doesn't exist yet.
    """
    if not events_path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(events_path)
    if student_id is not None:
        df = df[df["student_id"] == student_id].copy()
    df = df.sort_values(["timestamp"], kind="mergesort")
    return df
