from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from .features import RiskFeatures, features_to_vector, FEATURE_ORDER
from .scoring import heuristic_risk_score


@dataclass(frozen=True)
class RiskModelArtifacts:
    """
    Paths to model artifacts on disk.
    """
    model_path: Path
    feature_spec_path: Path
    metrics_path: Path


def _default_artifacts_paths(repo_root: Path) -> RiskModelArtifacts:
    """
    Default artifact locations used by the app.
    """
    base = repo_root / "models" / "edm_risk_gbm"
    return RiskModelArtifacts(
        model_path=base / "risk_model.joblib",
        feature_spec_path=base / "feature_spec.json",
        metrics_path=base / "training_metrics.json",
    )

def load_decision_threshold(metrics_path: Path, default: float = 0.65) -> float:
    if not metrics_path.exists():
        return default
    try:
        m = json.loads(metrics_path.read_text(encoding="utf-8"))
        return float(m.get("decision_threshold", default))
    except Exception:
        return default


def load_feature_spec(feature_spec_path: Path) -> List[str]:
    """
    Loads the feature order used at training time.

    feature_spec.json format:
      {
        "feature_order": ["n_solves", "acc", ...],
        "version": 1
      }
    """
    spec = json.loads(feature_spec_path.read_text(encoding="utf-8"))
    order = spec.get("feature_order")
    if not isinstance(order, list) or not order:
        raise ValueError("feature_spec.json must contain a non-empty 'feature_order' list")
    return [str(x) for x in order]


def try_load_model(repo_root: Path) -> Tuple[Optional[object], Optional[List[str]], Optional[float]]:
    """
    Returns (model, feature_order) if artifacts exist; otherwise (None, None).

    The loaded model is expected to expose predict_proba(X).
    In training, you should save a full sklearn Pipeline (e.g., StandardScaler + LR).
    """
    artifacts = _default_artifacts_paths(repo_root)
    if not artifacts.model_path.exists() or not artifacts.feature_spec_path.exists():
        return None, None, None

    # Local import so the Streamlit app doesn't require sklearn/joblib unless model exists.
    from joblib import load

    model = load(artifacts.model_path)
    feature_order = load_feature_spec(artifacts.feature_spec_path)
    threshold = load_decision_threshold(artifacts.metrics_path, default=0.65)
    return model, feature_order, threshold



def score_risk(*, features: RiskFeatures, repo_root: Path) -> Tuple[float, str, Optional[bool]]:
    model, feature_order, threshold = try_load_model(repo_root)
    if model is None or feature_order is None:
        score = float(heuristic_risk_score(features))
        return score, "heuristic", None

    x = features_to_vector(features, order=feature_order).astype(float).reshape(1, -1)
    proba = float(model.predict_proba(x)[0, 1])
    return proba, "model", (proba >= float(threshold))



def write_default_feature_spec(feature_spec_path: Path) -> None:
    """
    Utility: writes a default feature spec matching the current extractor order.
    Use this during training to lock feature order.
    """
    feature_spec_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"feature_order": FEATURE_ORDER, "version": 1}
    feature_spec_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
