from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Optional

def _hash_key(payload: dict) -> str:
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(s).hexdigest()

def cache_get(cache_path: Path, payload: dict) -> Optional[dict]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists():
        return None
    key = _hash_key(payload)
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("key") == key:
            return obj.get("value")
    return None

def cache_put(cache_path: Path, payload: dict, value: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    key = _hash_key(payload)
    rec = {"key": key, "value": value}
    with cache_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
