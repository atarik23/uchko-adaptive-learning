from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

from .cache import cache_get, cache_put
from .config import load_llm_config

import time as _time

COOLDOWN_UNTIL_TS = 0.0  # epoch seconds; if now < this => don't call Groq


LAST_LLM_STATUS = "not called"


def _safe_json_loads(text: str) -> Optional[dict]:
    import json
    if not isinstance(text, str):
        return None
    s = text.strip()

    # Strip markdown fences if present
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
        s = s.strip()

    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _groq_generate_json(*, api_key: str, model: str, system: str, user: str) -> Optional[dict]:
    global LAST_LLM_STATUS
    try:
        from groq import Groq
    except Exception as e:
        LAST_LLM_STATUS = f"Groq package missing: {e}"
        return None

    try:
        client = Groq(api_key=api_key)
        # Strong instruction: ONLY JSON
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{user}\n\nReturn ONLY valid JSON. No markdown."},
        ]
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        txt = resp.choices[0].message.content if resp and resp.choices else None
        if not txt:
            LAST_LLM_STATUS = "Groq returned empty text"
            return None

        parsed = _safe_json_loads(txt)
        if parsed is None:
            LAST_LLM_STATUS = "Groq response not valid JSON (parse failed)"
            return None
        return parsed

    except Exception as e:
        msg = f"{type(e).__name__}: {e}"

        # Rate limit detection (429)
        if "429" in str(e):
            global COOLDOWN_UNTIL_TS
            COOLDOWN_UNTIL_TS = _time.time() + 10 * 60  # 10 minutes
            LAST_LLM_STATUS = "Groq rate-limited (429). Cooling down for 10 minutes."
            return None

        LAST_LLM_STATUS = f"Groq call failed: {msg}"
        return None


def enhance_question_with_llm(
    *,
    repo_root: Path,
    skill_name: str,
    difficulty: int,
    base_prompt: str,
    correct_answer: str,
) -> Optional[Dict[str, Any]]:
    """
    Best-effort enhancement.
    Returns dict with any of:
      - rewritten_prompt (string)
      - choices (list[str]) optional
      - hint (string) optional
      - explanation (string) optional
    """
    global LAST_LLM_STATUS
    
    cfg = load_llm_config()
    if not cfg.enabled or cfg.provider != "groq":
        LAST_LLM_STATUS = "LLM disabled or provider not groq"
        return None
    if not cfg.api_key:
        LAST_LLM_STATUS = "Missing GROQ_API_KEY"
        return None
    
    # Cooldown gate (avoid repeated 429 spam)
    global COOLDOWN_UNTIL_TS
    now = _time.time()
    if now < COOLDOWN_UNTIL_TS:
        remaining = int(COOLDOWN_UNTIL_TS - now)
        LAST_LLM_STATUS = f"Groq cooldown active ({remaining}s remaining)"
        return None


    cache_path = repo_root / "data" / "cache" / "llm_cache.jsonl"
    payload = {
        "provider": cfg.provider,
        "model": cfg.model,
        "skill_name": skill_name,
        "difficulty": int(difficulty),
        "base_prompt": base_prompt,
        "correct_answer": str(correct_answer),
    }

    cached = cache_get(cache_path, payload)
    if cached is not None:
        LAST_LLM_STATUS = "OK (cache hit)"
        return cached

    system = (
        "You are an expert high-school math teacher.\n"
        "Output ONLY JSON.\n"
        "Rewrite the question clearly and generate multiple-choice distractors.\n"
        "CRITICAL: exactly one option must equal the provided correct answer.\n"
        "Also produce a short hint and short explanation.\n"
        "Start rewritten_prompt with the prefix: [Uchko-Groq] "
    )

    user = (
        f"Skill: {skill_name}\n"
        f"Difficulty: {difficulty} (1 easy, 3 hard)\n\n"
        f"Base question:\n{base_prompt}\n\n"
        f"Correct answer (must be included verbatim as one choice): {correct_answer}\n\n"
        "Return JSON with keys:\n"
        "- rewritten_prompt (string)\n"
        "- choices (list of 4 strings)\n"
        "- hint (string)\n"
        "- explanation (string)\n"
        "If you cannot generate 4 good choices, return rewritten_prompt only."
    )

    out = _groq_generate_json(api_key=cfg.api_key, model=cfg.model, system=system, user=user)
    if not isinstance(out, dict):
        # LAST_LLM_STATUS already set
        return None

    # --- normalize keys (groq sometimes uses different ones) ---
    rewritten = out.get("rewritten_prompt") or out.get("prompt") or out.get("question")
    hint = out.get("hint")
    explanation = out.get("explanation") or out.get("solution")

    choices = out.get("choices") or out.get("options")
    norm: Dict[str, Any] = {}

    if isinstance(rewritten, str) and rewritten.strip():
        norm["rewritten_prompt"] = rewritten.strip()

    if isinstance(hint, str) and hint.strip():
        norm["hint"] = hint.strip()

    if isinstance(explanation, str) and explanation.strip():
        norm["explanation"] = explanation.strip()

    # choices are optional; if provided, validate lightly
    if isinstance(choices, list) and len(choices) >= 4:
        choices4 = [str(c) for c in choices[:4]]
        # ensure correct answer appears
        s_correct = str(correct_answer)
        if s_correct not in choices4:
            choices4[0] = s_correct
        norm["choices"] = choices4

    if not norm:
        LAST_LLM_STATUS = "Groq returned JSON but with no usable fields"
        return None

    cache_put(cache_path, payload, norm)
    LAST_LLM_STATUS = "OK (Groq enhancement applied)"
    return norm
