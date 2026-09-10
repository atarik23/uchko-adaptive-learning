import json
from pathlib import Path

import numpy as np
import pandas as pd

from numba import njit
from scipy.optimize import minimize
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)


ROOT_DIR = Path.home() / "uchko-model"
DATA_DIR = ROOT_DIR / "data" / "processed"
ARTIFACT_DIR = ROOT_DIR / "artifacts"
REPORT_DIR = ROOT_DIR / "reports"

MIN_SKILL_INTERACTIONS = 1000
MIN_SKILL_STUDENTS = 50

PARAMETER_BOUNDS = [
    (0.01, 0.99),   # initial mastery
    (0.001, 0.50),  # learning probability
    (0.001, 0.50),  # guess probability
    (0.001, 0.50),  # slip probability
]


@njit(cache=True)
def negative_log_likelihood(
    parameters,
    outcomes,
    sequence_starts,
):
    initial_mastery = parameters[0]
    learn = parameters[1]
    guess = parameters[2]
    slip = parameters[3]

    mastery = initial_mastery
    total_loss = 0.0

    for index in range(len(outcomes)):
        if sequence_starts[index]:
            mastery = initial_mastery

        probability_correct = (
            mastery * (1.0 - slip)
            + (1.0 - mastery) * guess
        )

        probability_correct = min(
            max(probability_correct, 1e-7),
            1.0 - 1e-7,
        )

        outcome = outcomes[index]

        if outcome == 1:
            total_loss -= np.log(probability_correct)

            posterior_mastery = (
                mastery * (1.0 - slip)
            ) / probability_correct
        else:
            total_loss -= np.log(
                1.0 - probability_correct
            )

            denominator = (
                mastery * slip
                + (1.0 - mastery) * (1.0 - guess)
            )

            denominator = max(denominator, 1e-7)

            posterior_mastery = (
                mastery * slip
            ) / denominator

        mastery = (
            posterior_mastery
            + (1.0 - posterior_mastery) * learn
        )

    return total_loss


@njit(cache=True)
def predict_bkt(
    parameters,
    outcomes,
    sequence_starts,
):
    initial_mastery = parameters[0]
    learn = parameters[1]
    guess = parameters[2]
    slip = parameters[3]

    mastery = initial_mastery
    probabilities = np.empty(
        len(outcomes),
        dtype=np.float64,
    )

    for index in range(len(outcomes)):
        if sequence_starts[index]:
            mastery = initial_mastery

        probability_correct = (
            mastery * (1.0 - slip)
            + (1.0 - mastery) * guess
        )

        probability_correct = min(
            max(probability_correct, 1e-7),
            1.0 - 1e-7,
        )

        probabilities[index] = probability_correct

        outcome = outcomes[index]

        if outcome == 1:
            posterior_mastery = (
                mastery * (1.0 - slip)
            ) / probability_correct
        else:
            denominator = (
                mastery * slip
                + (1.0 - mastery) * (1.0 - guess)
            )

            denominator = max(denominator, 1e-7)

            posterior_mastery = (
                mastery * slip
            ) / denominator

        mastery = (
            posterior_mastery
            + (1.0 - posterior_mastery) * learn
        )

    return probabilities


def load_split(split_name):
    columns = [
        "id",
        "user_id",
        "primary_skill",
        "end_time",
        "target",
    ]

    return pd.read_parquet(
        DATA_DIR / f"{split_name}.parquet",
        columns=columns,
    )


def create_arrays(data, include_skill_in_sequence):
    sort_columns = ["user_id", "end_time", "id"]

    if include_skill_in_sequence:
        sort_columns = [
            "primary_skill",
            "user_id",
            "end_time",
            "id",
        ]

    ordered = data.sort_values(
        sort_columns
    ).reset_index(drop=True)

    outcomes = ordered["target"].to_numpy(
        dtype=np.int8
    )

    user_values = ordered["user_id"].to_numpy()

    sequence_starts = np.empty(
        len(ordered),
        dtype=np.bool_,
    )

    sequence_starts[0] = True

    if include_skill_in_sequence:
        skill_values = ordered[
            "primary_skill"
        ].astype(str).to_numpy()

        sequence_starts[1:] = (
            (user_values[1:] != user_values[:-1])
            | (skill_values[1:] != skill_values[:-1])
        )
    else:
        sequence_starts[1:] = (
            user_values[1:] != user_values[:-1]
        )

    return outcomes, sequence_starts


def fit_parameters(
    outcomes,
    sequence_starts,
    starting_parameters,
    max_iterations=100,
):
    result = minimize(
        fun=lambda parameters: float(
            negative_log_likelihood(
                parameters,
                outcomes,
                sequence_starts,
            )
        ),
        x0=np.asarray(
            starting_parameters,
            dtype=np.float64,
        ),
        method="L-BFGS-B",
        bounds=PARAMETER_BOUNDS,
        options={
            "maxiter": max_iterations,
            "ftol": 1e-9,
        },
    )

    return result.x, result.fun, result.success


def calculate_metrics(
    outcomes,
    probabilities,
):
    predictions = (
        probabilities >= 0.5
    ).astype(int)

    return {
        "roc_auc": float(
            roc_auc_score(
                outcomes,
                probabilities,
            )
        ),
        "accuracy": float(
            accuracy_score(
                outcomes,
                predictions,
            )
        ),
        "f1": float(
            f1_score(
                outcomes,
                predictions,
            )
        ),
        "log_loss": float(
            log_loss(
                outcomes,
                probabilities,
            )
        ),
        "brier_score": float(
            brier_score_loss(
                outcomes,
                probabilities,
            )
        ),
    }


def evaluate_split(
    data,
    skill_parameters,
    global_parameters,
):
    all_outcomes = []
    all_probabilities = []

    for skill, skill_data in data.groupby(
        "primary_skill",
        sort=False,
    ):
        outcomes, starts = create_arrays(
            skill_data,
            include_skill_in_sequence=False,
        )

        parameters = np.asarray(
            skill_parameters.get(
                str(skill),
                global_parameters,
            ),
            dtype=np.float64,
        )

        probabilities = predict_bkt(
            parameters,
            outcomes,
            starts,
        )

        all_outcomes.append(outcomes)
        all_probabilities.append(probabilities)

    outcomes = np.concatenate(all_outcomes)
    probabilities = np.concatenate(
        all_probabilities
    )

    return calculate_metrics(
        outcomes,
        probabilities,
    )


def print_metrics(title, metrics):
    print(f"\n{title}")

    for name, value in metrics.items():
        print(f"  {name}: {value:.6f}")


def main():
    ARTIFACT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Loading train, validation and test data...")

    train = load_split("train")
    validation = load_split("validation")
    test = load_split("test")

    print("Preparing global BKT sequences...")

    global_outcomes, global_starts = create_arrays(
        train,
        include_skill_in_sequence=True,
    )

    initial_candidates = [
        [0.30, 0.10, 0.20, 0.10],
        [0.50, 0.05, 0.20, 0.15],
        [0.20, 0.20, 0.25, 0.10],
        [0.70, 0.05, 0.10, 0.20],
    ]

    best_parameters = None
    best_loss = np.inf

    print("Fitting global BKT parameters...")

    for candidate in initial_candidates:
        parameters, loss, success = fit_parameters(
            global_outcomes,
            global_starts,
            candidate,
            max_iterations=150,
        )

        print(
            f"  start={candidate}, "
            f"loss={loss:.2f}, "
            f"success={success}"
        )

        if loss < best_loss:
            best_loss = loss
            best_parameters = parameters

    global_parameters = best_parameters

    print("\nGlobal parameters:")
    print(
        f"  initial_mastery: "
        f"{global_parameters[0]:.6f}"
    )
    print(
        f"  learn: "
        f"{global_parameters[1]:.6f}"
    )
    print(
        f"  guess: "
        f"{global_parameters[2]:.6f}"
    )
    print(
        f"  slip: "
        f"{global_parameters[3]:.6f}"
    )

    skill_parameters = {}
    skill_details = {}

    grouped_skills = list(
        train.groupby(
            "primary_skill",
            sort=True,
        )
    )

    print(
        f"\nFitting parameters for "
        f"{len(grouped_skills)} skills..."
    )

    for index, (skill, skill_data) in enumerate(
        grouped_skills,
        start=1,
    ):
        number_of_interactions = len(skill_data)
        number_of_students = (
            skill_data["user_id"].nunique()
        )

        use_global_fallback = (
            number_of_interactions
            < MIN_SKILL_INTERACTIONS
            or number_of_students
            < MIN_SKILL_STUDENTS
        )

        if use_global_fallback:
            parameters = global_parameters.copy()
            success = True
            source = "global_fallback"
        else:
            outcomes, starts = create_arrays(
                skill_data,
                include_skill_in_sequence=False,
            )

            parameters, _, success = fit_parameters(
                outcomes,
                starts,
                global_parameters,
                max_iterations=100,
            )

            source = (
                "skill_specific"
                if success
                else "global_fallback"
            )

            if not success:
                parameters = global_parameters.copy()

        skill_key = str(skill)

        skill_parameters[skill_key] = [
            float(value)
            for value in parameters
        ]

        skill_details[skill_key] = {
            "source": source,
            "interactions": int(
                number_of_interactions
            ),
            "students": int(
                number_of_students
            ),
        }

        if (
            index == 1
            or index % 20 == 0
            or index == len(grouped_skills)
        ):
            print(
                f"  processed "
                f"{index}/{len(grouped_skills)} skills"
            )

    print("\nEvaluating BKT on validation set...")

    validation_metrics = evaluate_split(
        validation,
        skill_parameters,
        global_parameters,
    )

    print_metrics(
        "BKT — validation",
        validation_metrics,
    )

    print("\nEvaluating BKT on test set...")

    test_metrics = evaluate_split(
        test,
        skill_parameters,
        global_parameters,
    )

    print_metrics(
        "BKT — test",
        test_metrics,
    )

    parameter_output = {
        "version": "foundational-assist-bkt-v1",
        "global": {
            "initial_mastery": float(
                global_parameters[0]
            ),
            "learn": float(
                global_parameters[1]
            ),
            "guess": float(
                global_parameters[2]
            ),
            "slip": float(
                global_parameters[3]
            ),
        },
        "skills": {
            skill: {
                "initial_mastery": values[0],
                "learn": values[1],
                "guess": values[2],
                "slip": values[3],
                **skill_details[skill],
            }
            for skill, values in skill_parameters.items()
        },
    }

    with (
        ARTIFACT_DIR / "bkt_parameters.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            parameter_output,
            file,
            indent=2,
        )

    metrics_output = {
        "validation": validation_metrics,
        "test": test_metrics,
        "skill_specific_count": sum(
            detail["source"] == "skill_specific"
            for detail in skill_details.values()
        ),
        "global_fallback_count": sum(
            detail["source"] == "global_fallback"
            for detail in skill_details.values()
        ),
    }

    with (
        REPORT_DIR / "bkt_metrics.json"
    ).open("w", encoding="utf-8") as file:
        json.dump(
            metrics_output,
            file,
            indent=2,
        )

    print("\nBKT training complete.")
    print(
        f"Parameters: "
        f"{ARTIFACT_DIR / 'bkt_parameters.json'}"
    )
    print(
        f"Metrics: "
        f"{REPORT_DIR / 'bkt_metrics.json'}"
    )


if __name__ == "__main__":
    main()
