from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import os

@dataclass
class LLMConfig:
    provider: str  # "none" | "openai" | "groq"
    model: str
    api_key: Optional[str]
    enabled: bool

def load_llm_config() -> LLMConfig:
    provider = os.getenv("UCHKO_LLM_PROVIDER", "none").strip().lower()
    model = os.getenv("UCHKO_LLM_MODEL", "").strip()
    enabled = os.getenv("UCHKO_LLM_ENABLED", "0").strip() == "1"

    api_key = None
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not model:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    elif provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not model:
            model = os.getenv("GROQ_MODEL", "llama3-8b-8192")

    return LLMConfig(provider=provider, model=model, api_key=api_key, enabled=enabled)