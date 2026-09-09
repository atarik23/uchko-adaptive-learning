from pathlib import Path

import numpy as np
import pandas as pd


RANDOM_SEED = 42

ROOT_DIR = Path.home() / "uchko-model"
RAW_DIR = ROOT_DIR / "data" / "foundational-assist" / "Data"
OUTPUT_DIR = ROOT_DIR / "data" / "processed"


def load_interactions():
    columns = [
        "id",
        "problem_id",
        "hint_count",
        "saw_answer",
        "discrete_score",
        "end_time",
        "user_id",
    ]

    interactions = pd.read_csv(
        RAW_DIR / "Interactions.csv",
        usecols=columns,
    )

    interactions = interactions.dropna(
        subset=["discrete_score", "end_time"]
    ).copy()

    interactions = interactions[
        interactions["discrete_score"].isin([0, 1])
    ].copy()

    interactions["end_time"] = pd.to_datetime(
        interactions["end_time"],
        format="mixed",
        errors="coerce",
        utc=True,
    )

    interactions = interactions.dropna(
        subset=["end_time"]
    ).copy()

    interactions = interactions.drop_duplicates(
        subset=["id"],
        keep="first",
    )

    interactions["target"] = interactions[
        "discrete_score"
    ].astype("int8")

    interactions["hint_count"] = (
        pd.to_numeric(
            interactions["hint_count"],
            errors="coerce",
        )
        .fillna(0)
        .clip(lower=0)
        .astype("int16")
    )

    interactions["saw_answer_numeric"] = (
        interactions["saw_answer"]
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes"])
        .astype("int8")
    )

    return interactions


def load_problem_metadata():
    problems = pd.read_csv(
        RAW_DIR / "Problems.csv"
    )

    duplicate_problem_ids = problems.loc[
        problems.duplicated(
            "problem_id",
            keep=False,
        ),
        "problem_id",
    ].unique()

    problems = problems[
        ~problems["problem_id"].isin(
            duplicate_problem_ids
        )
    ].copy()

    problems = problems[
        [
            "problem_id",
            "Problem Set Id",
            "Problem Part",
            "Problem Type",
            "Answer Types",
        ]
    ].copy()

    problems = problems.rename(
        columns={
            "Problem Set Id": "problem_set_id",
            "Problem Part": "problem_part",
            "Problem Type": "problem_type",
            "Answer Types": "answer_type",
        }
    )

    problems["problem_part"] = (
        pd.to_numeric(
            problems["problem_part"],
            errors="coerce",
        )
        .fillna(-1)
        .astype("int16")
    )

    for column in [
        "problem_set_id",
        "problem_type",
        "answer_type",
    ]:
        problems[column] = (
            problems[column]
            .fillna("unknown")
            .astype(str)
        )

    return problems


def load_skill_metadata():
    skills = pd.read_csv(
        RAW_DIR / "Skills.csv"
    )

    skills["node_code"] = (
        skills["node_code"]
        .fillna("unknown")
        .astype(str)
    )

    skills = skills.sort_values(
        ["problem_id", "node_code", "skill_id"]
    )

    skill_metadata = (
        skills
        .groupby("problem_id", as_index=False)
        .agg(
            primary_skill=("node_code", "first"),
            skill_count=("skill_id", "nunique"),
        )
    )

    skill_metadata["skill_count"] = (
        skill_metadata["skill_count"]
        .astype("int8")
    )

    return skill_metadata


def add_sequential_features(data):
    data = data.sort_values(
        ["user_id", "end_time", "id"]
    ).reset_index(drop=True)

    user_group = data.groupby(
        "user_id",
        sort=False,
    )

    data["user_attempts_before"] = (
        user_group.cumcount().astype("int16")
    )

    data["user_correct_before"] = (
        user_group["target"].cumsum()
        - data["target"]
    ).astype("int16")

    data["user_accuracy_before"] = (
        data["user_correct_before"] + 1.0
    ) / (
        data["user_attempts_before"] + 2.0
    )

    data["user_hints_before"] = (
        user_group["hint_count"].cumsum()
        - data["hint_count"]
    ).astype("int32")

    data["user_saw_answer_before"] = (
        user_group["saw_answer_numeric"].cumsum()
        - data["saw_answer_numeric"]
    ).astype("int16")

    data["previous_correct"] = (
        user_group["target"]
        .shift(1)
        .fillna(-1)
        .astype("int8")
    )

    data["previous_used_hint"] = (
        user_group["hint_count"]
        .shift(1)
        .fillna(0)
        .gt(0)
        .astype("int8")
    )

    previous_time = user_group["end_time"].shift(1)

    data["hours_since_previous"] = (
        (data["end_time"] - previous_time)
        .dt.total_seconds()
        .div(3600)
        .clip(lower=0, upper=720)
        .fillna(-1)
        .astype("float32")
    )

    skill_group = data.groupby(
        ["user_id", "primary_skill"],
        sort=False,
    )

    data["skill_attempts_before"] = (
        skill_group.cumcount().astype("int16")
    )

    data["skill_correct_before"] = (
        skill_group["target"].cumsum()
        - data["target"]
    ).astype("int16")

    data["skill_accuracy_before"] = (
        data["skill_correct_before"] + 1.0
    ) / (
        data["skill_attempts_before"] + 2.0
    )

    data["user_accuracy_before"] = data[
        "user_accuracy_before"
    ].astype("float32")

    data["skill_accuracy_before"] = data[
        "skill_accuracy_before"
    ].astype("float32")

    return data


def assign_user_splits(data):
    unique_users = data["user_id"].drop_duplicates().to_numpy()

    rng = np.random.default_rng(RANDOM_SEED)
    rng.shuffle(unique_users)

    number_of_users = len(unique_users)
    train_end = int(number_of_users * 0.70)
    validation_end = int(number_of_users * 0.85)

    train_users = set(unique_users[:train_end])
    validation_users = set(
        unique_users[train_end:validation_end]
    )

    data["split"] = "test"
    data.loc[
        data["user_id"].isin(train_users),
        "split",
    ] = "train"
    data.loc[
        data["user_id"].isin(validation_users),
        "split",
    ] = "validation"

    return data


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Loading interactions...")
    interactions = load_interactions()

    print("Loading problem metadata...")
    problems = load_problem_metadata()

    print("Loading skill metadata...")
    skills = load_skill_metadata()

    print("Joining tables...")
    data = (
        interactions
        .merge(
            problems,
            on="problem_id",
            how="inner",
            validate="many_to_one",
        )
        .merge(
            skills,
            on="problem_id",
            how="inner",
            validate="many_to_one",
        )
    )

    del interactions
    del problems
    del skills

    print("Creating leakage-safe sequential features...")
    data = add_sequential_features(data)

    print("Assigning student-level splits...")
    data = assign_user_splits(data)

    output_columns = [
        "id",
        "user_id",
        "problem_id",
        "end_time",
        "target",
        "problem_set_id",
        "problem_part",
        "problem_type",
        "answer_type",
        "primary_skill",
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
        "split",
    ]

    data = data[output_columns]

    for split_name in [
        "train",
        "validation",
        "test",
    ]:
        split_data = data[
            data["split"] == split_name
        ].drop(columns=["split"])

        output_path = OUTPUT_DIR / f"{split_name}.parquet"

        split_data.to_parquet(
            output_path,
            index=False,
        )

        print(
            f"{split_name}: "
            f"{len(split_data):,} rows, "
            f"{split_data['user_id'].nunique():,} students, "
            f"target mean={split_data['target'].mean():.4f}"
        )

    print(f"Saved processed files to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
