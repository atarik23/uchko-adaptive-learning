from __future__ import annotations
from typing import Protocol

class LLMProvider(Protocol):
    def generate_json(self, *, system: str, user: str) -> dict: ...
