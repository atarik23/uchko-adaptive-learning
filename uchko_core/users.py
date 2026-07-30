from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class User:
    username: str
    student_id: str
    created_at: float
    last_active_at: float
    prefs: Dict[str, Any]


def _now() -> float:
    return time.time()


def _read_json_safe(path: Path) -> dict:
    """
    Load JSON file safely.
    - If file doesn't exist -> {}
    - If file exists but empty/corrupt -> {}
    """
    if not path.exists():
        return {}
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return {}
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_users(path: Path) -> Dict[str, User]:
    """
    Returns map: username -> User
    """
    raw = _read_json_safe(path)
    users: Dict[str, User] = {}

    for username, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        try:
            users[username] = User(
                username=str(payload.get("username", username)),
                student_id=str(payload.get("student_id", "")),
                created_at=float(payload.get("created_at", _now())),
                last_active_at=float(payload.get("last_active_at", _now())),
                prefs=dict(payload.get("prefs", {})) if isinstance(payload.get("prefs", {}), dict) else {},
            )
        except Exception:
            # Skip malformed entries rather than crashing the whole app
            continue

    return users


def get_or_create_user(path: Path, username: str) -> User:
    """
    Creates a new user if username doesn't exist; otherwise returns existing.
    Updates last_active_at on access.
    """
    username = username.strip()
    if not username:
        raise ValueError("username cannot be empty")

    raw = _read_json_safe(path)

    if username in raw and isinstance(raw[username], dict):
        payload = raw[username]
        user = User(
            username=username,
            student_id=str(payload.get("student_id", "")) or f"U_{uuid.uuid4().hex[:8]}",
            created_at=float(payload.get("created_at", _now())),
            last_active_at=_now(),
            prefs=dict(payload.get("prefs", {})) if isinstance(payload.get("prefs", {}), dict) else {},
        )
    else:
        user = User(
            username=username,
            student_id=f"U_{uuid.uuid4().hex[:8]}",
            created_at=_now(),
            last_active_at=_now(),
            prefs={},
        )

    # persist
    raw[username] = asdict(user)
    _write_json(path, raw)
    return user


def update_user_prefs(path: Path, username: str, **prefs_updates: Any) -> None:
    """
    Patch user prefs and persist them.
    """
    username = username.strip()
    if not username:
        return

    raw = _read_json_safe(path)
    payload = raw.get(username)
    if not isinstance(payload, dict):
        # user doesn't exist yet -> create
        user = get_or_create_user(path, username)
        payload = asdict(user)

    prefs = payload.get("prefs")
    if not isinstance(prefs, dict):
        prefs = {}

    prefs.update(prefs_updates)
    payload["prefs"] = prefs
    payload["last_active_at"] = _now()

    raw[username] = payload
    _write_json(path, raw)
