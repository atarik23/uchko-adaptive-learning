from __future__ import annotations

import math
import random
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import Question, Template

try:
    from uchko_core.llm.enhance import enhance_question_with_llm
except Exception:
    enhance_question_with_llm = None  # LLM is optional


# ---------- helper functions used in answer_expr ----------

def is_square(k: int) -> bool:
    if k < 0:
        return False
    r = int(math.isqrt(k))
    return r * r == k


def sqrt(k: int) -> str:
    # symbolic-ish fallback (demo-friendly)
    return f"sqrt({k})"


def isqrt(k: int) -> int:
    return int(math.isqrt(k))


def quadrant(x: int, y: int) -> str:
    if x == 0 or y == 0:
        return "Axis"
    if x > 0 and y > 0:
        return "I"
    if x < 0 and y > 0:
        return "II"
    if x < 0 and y < 0:
        return "III"
    return "IV"


def _fmt_signed(n: int) -> str:
    return f"+{n}" if n >= 0 else f"{n}"


def factor_pair(b: int, c: int) -> str:
    """
    Return '(x+2)(x+3)' if factorable over integers.
    Else 'Not factorable over integers'.
    """
    for p in range(-50, 51):
        for q in range(-50, 51):
            if p + q == b and p * q == c:
                return f"(x{_fmt_signed(p)})(x{_fmt_signed(q)})"
    return "Not factorable over integers"


def one_root_from_factor(b: int, c: int) -> int:
    """
    If factorable: (x+p)(x+q)=0 => roots -p, -q. Return one root.
    """
    for p in range(-50, 51):
        for q in range(-50, 51):
            if p + q == b and p * q == c:
                return -p
    return 0


def smaller_root_quadratic(a: int, b: int, c: int) -> str:
    disc = b * b - 4 * a * c
    if disc < 0:
        return "no real roots"
    rdisc = math.isqrt(disc)
    if rdisc * rdisc == disc:
        r1 = Fraction(-b - rdisc, 2 * a)
        r2 = Fraction(-b + rdisc, 2 * a)
        return str(min(r1, r2))
    return f"(-{b} - sqrt({disc}))/{2 * a}"


def _fraction_to_str(x: Any) -> str:
    if isinstance(x, Fraction):
        if x.denominator == 1:
            return str(x.numerator)
        return f"{x.numerator}/{x.denominator}"
    return str(x)


# ---------- core generator ----------

def _sample_params(params_spec: Dict[str, List[int]], rng: random.Random) -> Dict[str, int]:
    sampled: Dict[str, int] = {}
    for k, bounds in params_spec.items():
        lo, hi = int(bounds[0]), int(bounds[1])
        if lo > hi:
            lo, hi = hi, lo
        sampled[k] = rng.randint(lo, hi)
    return sampled


def _safe_eval_answer(expr: str, env: Dict[str, Any]) -> Any:
    """
    Evaluates a restricted expression language.
    We control templates.json, so this is safe enough for demo, but still restrict builtins.
    """
    allowed_globals = {
        "Fraction": Fraction,
        "is_square": is_square,
        "isqrt": isqrt,
        "sqrt": sqrt,
        "quadrant": quadrant,
        "factor_pair": factor_pair,
        "one_root_from_factor": one_root_from_factor,
        "smaller_root_quadratic": smaller_root_quadratic,
        "__builtins__": {},
    }
    return eval(expr, allowed_globals, env)  # controlled templates only


def _make_mcq_choices(correct: str, rng: random.Random, spec: Dict[str, Any], env: Dict[str, Any]) -> List[str]:
    """
    Simple distractor generation. For demo, we generate plausible numeric distractors.
    """
    n_choices = int(spec.get("choices", 4))
    distractor_tags: List[str] = list(spec.get("distractors", []))

    choices = {str(correct)}

    def try_add(val: str):
        val = str(val)
        if val not in choices:
            choices.add(val)

    # numeric perturbations
    if "/" in str(correct):
        try:
            num, den = str(correct).split("/")
            num_i, den_i = int(num), int(den)
            try_add(f"{num_i+1}/{den_i}")
            try_add(f"{num_i}/{max(1, den_i+1)}")
            try_add(f"{max(0, num_i-1)}/{den_i}")
        except Exception:
            pass
    else:
        try:
            x = int(str(correct))
            try_add(str(x + 1))
            try_add(str(x - 1))
            try_add(str(x + 2))
            try_add(str(x * 2 if x != 0 else 1))
        except Exception:
            pass

    # tag-based distractors
    for tag in distractor_tags:
        if tag == "add_denominators":
            if all(k in env for k in ("a", "b", "c", "d")):
                try_add(_fraction_to_str(Fraction(env["a"] + env["c"], env["b"] + env["d"])))
        elif tag == "add_numerators_only":
            if all(k in env for k in ("a", "b", "c", "d")):
                try_add(_fraction_to_str(Fraction(env["a"] + env["c"], env["b"])))
        elif tag == "wrong_common_denominator":
            if all(k in env for k in ("a", "b", "c", "d")):
                try_add(_fraction_to_str(Fraction(env["a"] * env["d"] + env["c"] * env["b"], env["b"] * env["b"])))
        elif tag in ("swap_axes", "sign_error", "origin_confusion"):
            for q in ["I", "II", "III", "IV", "Axis"]:
                try_add(q)
        elif tag in ("wrong_pair", "swap_terms"):
            s = str(correct)
            try_add(s.replace("+", "TEMP").replace("-", "+").replace("TEMP", "-"))
            try_add("(x+1)(x+1)")
        elif tag == "random_integer":
            try_add(str(rng.randint(-10, 10)))

    while len(choices) < n_choices:
        try_add(str(rng.randint(-20, 20)))

    out = list(choices)
    rng.shuffle(out)
    return out[:n_choices]


def _repo_root_from_here() -> Path:
    """
    uchko_core/content/generator.py -> repo_root = parents[2]
    repo_root/
      uchko_core/
        content/
          generator.py
    """
    return Path(__file__).resolve().parents[2]


def _apply_llm_enhancement(q: Question, *, repo_root: Path, skill_name: str) -> Question:
    enhanced = None
    try:
        enhanced = enhance_question_with_llm(
            repo_root=repo_root,
            skill_name=skill_name,
            difficulty=int(q.difficulty),
            base_prompt=str(q.prompt),
            correct_answer=str(q.correct_answer),
        )
    except Exception:
        enhanced = None

    # Default: not used
    try:
        q.generated_params = q.generated_params or {}
        q.generated_params["_llm_used"] = bool(enhanced)
    except Exception:
        pass
    return q

    # Apply prompt
    rp = enhanced.get("rewritten_prompt")
    if isinstance(rp, str) and rp.strip():
        q.prompt = rp.strip()

    # Apply choices if present
    choices = enhanced.get("choices")
    if isinstance(choices, list) and len(choices) == 4:
        q.type = "mcq"
        q.choices = [str(c) for c in choices]

    # Store hint/explanation in meta (optional)
    if hasattr(q, "meta"):
        try:
            q.meta = q.meta or {}
            if isinstance(enhanced.get("hint"), str):
                q.meta["llm_hint"] = enhanced["hint"]
            if isinstance(enhanced.get("explanation"), str):
                q.meta["llm_explanation"] = enhanced["explanation"]
        except Exception:
            pass

    return q


def generate_question(
    templates: List[Template],
    skill_id: str,
    difficulty: int,
    seed: Optional[int] = None,
    *,
    enable_llm: bool = True,
    skill_name: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Question:
    """
    Generate a single question for a given skill and difficulty.

    - Deterministic template engine computes the correct answer.
    - Optional LLM enhancement rewrites wording and proposes distractors,
      but never changes the correct answer.

    Params:
      enable_llm: set False to disable LLM enhancement even if env enables it
      skill_name: optional display name (if you have it in the UI)
      repo_root: optional path override (useful in tests)
    """
    rng = random.Random(seed if seed is not None else random.randrange(1_000_000_000))

    candidates = [t for t in templates if t.skill_id == skill_id and int(t.difficulty) == int(difficulty)]
    if not candidates:
        candidates = [t for t in templates if t.skill_id == skill_id]
    if not candidates:
        raise ValueError(f"No templates found for skill_id={skill_id}")

    t = rng.choice(candidates)
    params = _sample_params(t.params, rng)

    # avoid invalid slope (x1==x2) for slope templates
    if "x1" in params and "x2" in params and params["x1"] == params["x2"]:
        params["x2"] = params["x1"] + 1

    prompt = t.prompt_template.format(**params)

    env: Dict[str, Any] = dict(params)
    ans_raw = _safe_eval_answer(t.answer_expr, env)
    correct_answer = _fraction_to_str(ans_raw)

    choices: Optional[List[str]] = None
    if t.type == "mcq":
        spec = t.mcq or {"choices": 4, "distractors": []}
        choices = _make_mcq_choices(correct_answer, rng, spec, env)

    qid = f"Q_{t.template_id}_{uuid.uuid4().hex[:8]}"
    q = Question(
        question_id=qid,
        skill_id=t.skill_id,
        difficulty=int(t.difficulty),
        type=t.type,
        prompt=prompt,
        correct_answer=correct_answer,
        choices=choices,
        template_id=t.template_id,
        generated_params=params,
    )

    # Optional LLM enhancement
    if enable_llm:
        rr = repo_root or _repo_root_from_here()
        sk_name = skill_name or skill_id
        q = _apply_llm_enhancement(q, repo_root=rr, skill_name=sk_name)

    return q