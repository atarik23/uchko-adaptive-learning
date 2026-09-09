import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import xgboost as xgb


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

PREPROCESSOR_PATH = ARTIFACT_DIR / "preprocessor.joblib"
XGBOOST_MODEL_PATH = ARTIFACT_DIR / "xgboost_model.json"
FEATURE_SCHEMA_PATH = ARTIFACT_DIR / "feature_schema.json"
BKT_PARAMETERS_PATH = ARTIFACT_DIR / "bkt_parameters.json"


@dataclass(frozen=True)
class SuccessPredictionInput:
    problem_id: str
    problem_set_id: str
    problem_type: str
    answer_type: str
    primary_skill: str

    problem_part: int
    skill_count: int

    user_attempts_before: int
    user_correct_before: int
    user_accuracy_before: float
    user_hints_before: int
    user_saw_answer_before: int

    previous_correct: int
    previous_used_hint: int
    hours_since_previous: float

    skill_attempts_before: int
    skill_correct_before: int
    skill_accuracy_before: float


@dataclass(frozen=True)
class BKTParameters:
    initial_mastery: float
    learn: float
    guess: float
    slip: float
    source: str


@dataclass(frozen=True)
class BKTUpdate:
    previous_mastery: float
    probability_correct: float
    posterior_mastery: float
    updated_mastery: float
    source: str


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def load_feature_schema() -> dict[str, Any]:
    return _read_json(FEATURE_SCHEMA_PATH)


@lru_cache(maxsize=1)
def load_preprocessor():
    return joblib.load(PREPROCESSOR_PATH)


@lru_cache(maxsize=1)
def load_xgboost_model() -> xgb.XGBClassifier:
    model = xgb.XGBClassifier()
    model.load_model(XGBOOST_MODEL_PATH)

    # Model je treniran na serveru koji ima GPU, ali Django aplikacija
    # mora moći vršiti predikcije i na računaru bez GPU-a.
    model.set_params(device="cpu")

    return model


@lru_cache(maxsize=1)
def load_bkt_artifact() -> dict[str, Any]:
    return _read_json(BKT_PARAMETERS_PATH)


def predict_success_probability(
    prediction_input: SuccessPredictionInput,
) -> float:
    schema = load_feature_schema()
    values = asdict(prediction_input)

    expected_features = schema["model_features"]
    provided_features = list(values.keys())

    if provided_features != expected_features:
        raise ValueError(
            "Prediction input does not match the trained feature schema. "
            f"Expected {expected_features}, received {provided_features}."
        )

    frame = pd.DataFrame(
        [values],
        columns=expected_features,
    )

    for column in schema["categorical_features"]:
        frame[column] = (
            frame[column]
            .fillna("unknown")
            .astype(str)
        )

    transformed = load_preprocessor().transform(frame)

    probability = (
        load_xgboost_model()
        .predict_proba(transformed)[0, 1]
    )

    return float(probability)


def get_bkt_parameters(skill_code: str) -> BKTParameters:
    artifact = load_bkt_artifact()
    skill_data = artifact["skills"].get(str(skill_code))

    if skill_data is None:
        global_data = artifact["global"]

        return BKTParameters(
            initial_mastery=float(
                global_data["initial_mastery"]
            ),
            learn=float(global_data["learn"]),
            guess=float(global_data["guess"]),
            slip=float(global_data["slip"]),
            source="global_fallback",
        )

    return BKTParameters(
        initial_mastery=float(
            skill_data["initial_mastery"]
        ),
        learn=float(skill_data["learn"]),
        guess=float(skill_data["guess"]),
        slip=float(skill_data["slip"]),
        source=str(skill_data["source"]),
    )


def initial_mastery(skill_code: str) -> float:
    return get_bkt_parameters(
        skill_code
    ).initial_mastery


def predict_bkt_correct_probability(
    mastery: float,
    skill_code: str,
) -> float:
    parameters = get_bkt_parameters(skill_code)
    mastery = _validate_probability(mastery, "mastery")

    probability_correct = (
        mastery * (1.0 - parameters.slip)
        + (1.0 - mastery) * parameters.guess
    )

    return _clip_probability(probability_correct)


def update_bkt_mastery(
    mastery: float,
    is_correct: bool,
    skill_code: str,
) -> BKTUpdate:
    parameters = get_bkt_parameters(skill_code)
    mastery = _validate_probability(mastery, "mastery")

    probability_correct = predict_bkt_correct_probability(
        mastery=mastery,
        skill_code=skill_code,
    )

    if is_correct:
        posterior_mastery = (
            mastery * (1.0 - parameters.slip)
        ) / probability_correct
    else:
        probability_incorrect = 1.0 - probability_correct

        posterior_mastery = (
            mastery * parameters.slip
        ) / probability_incorrect

    posterior_mastery = _clip_probability(
        posterior_mastery
    )

    updated_mastery = (
        posterior_mastery
        + (1.0 - posterior_mastery) * parameters.learn
    )

    updated_mastery = _clip_probability(updated_mastery)

    return BKTUpdate(
        previous_mastery=mastery,
        probability_correct=probability_correct,
        posterior_mastery=posterior_mastery,
        updated_mastery=updated_mastery,
        source=parameters.source,
    )


def get_bkt_version() -> str:
    artifact = load_bkt_artifact()
    return str(
        artifact.get("version", "unknown")
    )


def _validate_probability(
    value: float,
    name: str,
) -> float:
    numeric_value = float(value)

    if not 0.0 <= numeric_value <= 1.0:
        raise ValueError(
            f"{name} must be between 0 and 1."
        )

    return numeric_value


def _clip_probability(value: float) -> float:
    return min(max(float(value), 1e-7), 1.0 - 1e-7)