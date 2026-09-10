import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


RANDOM_SEED = 42

ROOT_DIR = Path.home() / "uchko-model"
DATA_DIR = ROOT_DIR / "data" / "processed"
ARTIFACT_DIR = ROOT_DIR / "artifacts"
REPORT_DIR = ROOT_DIR / "reports"

TARGET_COLUMN = "target"

CATEGORICAL_FEATURES = [
    "problem_id",
    "problem_set_id",
    "problem_type",
    "answer_type",
    "primary_skill",
]

NUMERIC_FEATURES = [
    "problem_part",
    "skill_count",
    "user_attempts_before",
    "user_correct_before",
    "user_accuracy_before",
    "user_hints_before",
    "user_saw_answer_before",
    "previous_correct",
    "previous_used_hint",
    "hours_since_previous",
    "skill_attempts_before",
    "skill_correct_before",
    "skill_accuracy_before",
]

MODEL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def load_split(name):
    data = pd.read_parquet(
        DATA_DIR / f"{name}.parquet"
    )

    for column in CATEGORICAL_FEATURES:
        data[column] = (
            data[column]
            .fillna("unknown")
            .astype(str)
        )

    return data


def calculate_metrics(y_true, probabilities):
    predictions = (
        np.asarray(probabilities) >= 0.5
    ).astype(int)

    return {
        "roc_auc": float(
            roc_auc_score(y_true, probabilities)
        ),
        "accuracy": float(
            accuracy_score(y_true, predictions)
        ),
        "f1": float(
            f1_score(y_true, predictions)
        ),
        "log_loss": float(
            log_loss(y_true, probabilities)
        ),
        "brier_score": float(
            brier_score_loss(y_true, probabilities)
        ),
    }


def print_metrics(name, metrics):
    print(f"\n{name}")

    for metric_name, value in metrics.items():
        print(f"  {metric_name}: {value:.6f}")


def main():
    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Loading processed datasets...")

    train = load_split("train")
    validation = load_split("validation")
    test = load_split("test")

    x_train = train[MODEL_FEATURES]
    y_train = train[TARGET_COLUMN].astype(int)

    x_validation = validation[MODEL_FEATURES]
    y_validation = validation[TARGET_COLUMN].astype(int)

    x_test = test[MODEL_FEATURES]
    y_test = test[TARGET_COLUMN].astype(int)

    print(
        f"Train: {len(train):,}, "
        f"validation: {len(validation):,}, "
        f"test: {len(test):,}"
    )

    print("Fitting feature preprocessor...")

    numeric_transformer = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
            (
                "scaler",
                StandardScaler(with_mean=False),
            ),
        ]
    )

    categorical_transformer = OneHotEncoder(
        handle_unknown="ignore",
        min_frequency=20,
        dtype=np.float32,
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                categorical_transformer,
                CATEGORICAL_FEATURES,
            ),
            (
                "numeric",
                numeric_transformer,
                NUMERIC_FEATURES,
            ),
        ],
        sparse_threshold=1.0,
    )

    transformed_train = preprocessor.fit_transform(
        x_train
    )

    transformed_validation = preprocessor.transform(
        x_validation
    )

    transformed_test = preprocessor.transform(
        x_test
    )

    print(
        "Transformed feature count: "
        f"{transformed_train.shape[1]:,}"
    )

    joblib.dump(
        preprocessor,
        ARTIFACT_DIR / "preprocessor.joblib",
    )

    metrics_report = {}

    global_probability = float(y_train.mean())

    global_validation_probabilities = np.full(
        len(y_validation),
        global_probability,
    )

    metrics_report["global_baseline_validation"] = (
        calculate_metrics(
            y_validation,
            global_validation_probabilities,
        )
    )

    print_metrics(
        "Global baseline — validation",
        metrics_report["global_baseline_validation"],
    )

    history_validation_probabilities = (
        validation["user_accuracy_before"]
        .clip(0.001, 0.999)
        .to_numpy()
    )

    metrics_report["history_baseline_validation"] = (
        calculate_metrics(
            y_validation,
            history_validation_probabilities,
        )
    )

    print_metrics(
        "History baseline — validation",
        metrics_report["history_baseline_validation"],
    )

    print("\nTraining linear logistic baseline...")

    linear_model = SGDClassifier(
        loss="log_loss",
        alpha=1e-5,
        max_iter=40,
        tol=1e-4,
        random_state=RANDOM_SEED,
        n_jobs=-1,
        average=True,
    )

    linear_model.fit(
        transformed_train,
        y_train,
    )

    linear_validation_probabilities = (
        linear_model.predict_proba(
            transformed_validation
        )[:, 1]
    )

    metrics_report["linear_model_validation"] = (
        calculate_metrics(
            y_validation,
            linear_validation_probabilities,
        )
    )

    print_metrics(
        "Linear logistic model — validation",
        metrics_report["linear_model_validation"],
    )

    joblib.dump(
        linear_model,
        ARTIFACT_DIR / "linear_model.joblib",
    )

    print("\nTraining XGBoost model on GPU...")

    xgboost_model = xgb.XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=8,
        min_child_weight=5,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_alpha=0.1,
        reg_lambda=1.0,
        tree_method="hist",
        device="cuda",
        random_state=RANDOM_SEED,
        n_jobs=-1,
        early_stopping_rounds=30,
    )

    xgboost_model.fit(
        transformed_train,
        y_train,
        eval_set=[
            (
                transformed_validation,
                y_validation,
            )
        ],
        verbose=25,
    )

    xgboost_validation_probabilities = (
        xgboost_model.predict_proba(
            transformed_validation
        )[:, 1]
    )

    metrics_report["xgboost_validation"] = (
        calculate_metrics(
            y_validation,
            xgboost_validation_probabilities,
        )
    )

    print_metrics(
        "XGBoost — validation",
        metrics_report["xgboost_validation"],
    )

    print("\nEvaluating selected XGBoost model on test set...")

    xgboost_test_probabilities = (
        xgboost_model.predict_proba(
            transformed_test
        )[:, 1]
    )

    metrics_report["xgboost_test"] = (
        calculate_metrics(
            y_test,
            xgboost_test_probabilities,
        )
    )

    print_metrics(
        "XGBoost — test",
        metrics_report["xgboost_test"],
    )

    history_test_probabilities = (
        test["user_accuracy_before"]
        .clip(0.001, 0.999)
        .to_numpy()
    )

    metrics_report["history_baseline_test"] = (
        calculate_metrics(
            y_test,
            history_test_probabilities,
        )
    )

    print_metrics(
        "History baseline — test",
        metrics_report["history_baseline_test"],
    )

    xgboost_model.save_model(
        ARTIFACT_DIR / "xgboost_model.json"
    )

    schema = {
        "target": TARGET_COLUMN,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "model_features": MODEL_FEATURES,
        "random_seed": RANDOM_SEED,
        "train_students": int(
            train["user_id"].nunique()
        ),
        "validation_students": int(
            validation["user_id"].nunique()
        ),
        "test_students": int(
            test["user_id"].nunique()
        ),
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "test_rows": int(len(test)),
        "global_train_probability": global_probability,
    }

    with (
        ARTIFACT_DIR / "feature_schema.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            schema,
            file,
            indent=2,
        )

    with (
        REPORT_DIR / "metrics.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            metrics_report,
            file,
            indent=2,
        )

    print("\nTraining complete.")
    print(f"Artifacts: {ARTIFACT_DIR}")
    print(f"Metrics: {REPORT_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
