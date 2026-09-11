"""Train and evaluate a compact GRU Deep Knowledge Tracing model.

This script is designed for the protected FoundationalASSIST workspace at
~/uchko-model. It consumes the existing student-disjoint Parquet splits and
does not write or expose raw interaction data outside that workspace.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from torch import nn
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data import DataLoader, Dataset


ROOT_DIR = Path.home() / "uchko-model"
DATA_DIR = ROOT_DIR / "data" / "processed"
ARTIFACT_DIR = ROOT_DIR / "artifacts"
REPORT_DIR = ROOT_DIR / "reports"

PAD_TOKEN = 0
UNKNOWN_SKILL = "__UNKNOWN_SKILL__"


@dataclass(frozen=True)
class Configuration:
    random_seed: int
    embedding_dim: int
    hidden_dim: int
    dropout: float
    max_sequence_length: int
    batch_size: int
    learning_rate: float
    weight_decay: float
    max_epochs: int
    patience: int
    gradient_clip: float
    threads: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-sequence-length", type=int, default=100)
    parser.add_argument("--embedding-dim", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--gradient-clip", type=float, default=5.0)
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def set_reproducibility(seed: int, threads: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass


def load_split(name: str, smoke_test: bool = False) -> pd.DataFrame:
    columns = [
        "id",
        "user_id",
        "primary_skill",
        "end_time",
        "target",
    ]
    data = pd.read_parquet(DATA_DIR / f"{name}.parquet", columns=columns)
    data["primary_skill"] = data["primary_skill"].fillna(UNKNOWN_SKILL).astype(str)
    data["target"] = data["target"].astype("int8")
    data = data.sort_values(["user_id", "end_time", "id"]).reset_index(drop=True)

    if smoke_test:
        user_limit = {"train": 120, "validation": 40, "test": 40}[name]
        selected_users = data["user_id"].drop_duplicates().iloc[:user_limit]
        data = data[data["user_id"].isin(selected_users)].copy()

    data["user_position"] = data.groupby("user_id", sort=False).cumcount()
    return data


def build_skill_vocabulary(train: pd.DataFrame) -> tuple[dict[str, int], list[str]]:
    skill_codes = sorted(train["primary_skill"].unique().tolist())
    if UNKNOWN_SKILL in skill_codes:
        skill_codes.remove(UNKNOWN_SKILL)
    skill_codes.append(UNKNOWN_SKILL)
    return {skill: index for index, skill in enumerate(skill_codes)}, skill_codes


class SequenceDataset(Dataset):
    """Non-overlapping prediction chunks with one-event boundary overlap."""

    def __init__(
        self,
        data: pd.DataFrame,
        skill_to_index: dict[str, int],
        max_sequence_length: int,
    ) -> None:
        self.samples: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]] = []
        unknown_index = skill_to_index[UNKNOWN_SKILL]

        for _, student_data in data.groupby("user_id", sort=False):
            skills = (
                student_data["primary_skill"]
                .map(lambda value: skill_to_index.get(value, unknown_index))
                .to_numpy(dtype=np.int64)
            )
            outcomes = student_data["target"].to_numpy(dtype=np.int64)

            if len(skills) < 2:
                continue

            for start in range(0, len(skills) - 1, max_sequence_length):
                stop = min(start + max_sequence_length + 1, len(skills))
                chunk_skills = skills[start:stop]
                chunk_outcomes = outcomes[start:stop]

                if len(chunk_skills) < 2:
                    continue

                interaction_tokens = (
                    1 + 2 * chunk_skills[:-1] + chunk_outcomes[:-1]
                )
                next_skills = chunk_skills[1:]
                next_outcomes = chunk_outcomes[1:]

                self.samples.append(
                    (
                        torch.from_numpy(interaction_tokens.copy()).long(),
                        torch.from_numpy(next_skills.copy()).long(),
                        torch.from_numpy(next_outcomes.copy()).float(),
                    )
                )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        return self.samples[index]


def collate_sequences(batch):
    tokens, next_skills, labels = zip(*batch)
    lengths = torch.tensor([len(sequence) for sequence in tokens], dtype=torch.long)
    padded_tokens = pad_sequence(tokens, batch_first=True, padding_value=PAD_TOKEN)
    padded_skills = pad_sequence(next_skills, batch_first=True, padding_value=0)
    padded_labels = pad_sequence(labels, batch_first=True, padding_value=0.0)
    positions = torch.arange(padded_tokens.shape[1]).unsqueeze(0)
    mask = positions < lengths.unsqueeze(1)
    return padded_tokens, padded_skills, padded_labels, mask


class GRUDKT(nn.Module):
    def __init__(
        self,
        number_of_skills: int,
        embedding_dim: int,
        hidden_dim: int,
        dropout: float,
    ) -> None:
        super().__init__()
        interaction_vocabulary_size = 1 + 2 * number_of_skills
        self.embedding = nn.Embedding(
            interaction_vocabulary_size,
            embedding_dim,
            padding_idx=PAD_TOKEN,
        )
        self.gru = nn.GRU(
            input_size=embedding_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
        )
        self.dropout = nn.Dropout(dropout)
        self.output = nn.Linear(hidden_dim, number_of_skills)

    def forward(self, tokens: torch.Tensor, next_skills: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(tokens)
        hidden, _ = self.gru(embedded)
        all_logits = self.output(self.dropout(hidden))
        return all_logits.gather(2, next_skills.unsqueeze(-1)).squeeze(-1)


def calculate_metrics(targets: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    probabilities = np.clip(probabilities.astype(float), 1e-7, 1.0 - 1e-7)
    predictions = (probabilities >= 0.5).astype(int)
    return {
        "roc_auc": float(roc_auc_score(targets, probabilities)),
        "accuracy": float(accuracy_score(targets, predictions)),
        "f1": float(f1_score(targets, predictions)),
        "log_loss": float(log_loss(targets, probabilities)),
        "brier_score": float(brier_score_loss(targets, probabilities)),
        "rows": int(len(targets)),
    }


@torch.inference_mode()
def evaluate_model(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
) -> tuple[float, dict[str, float]]:
    model.eval()
    total_loss = 0.0
    total_count = 0
    target_parts = []
    probability_parts = []

    for tokens, next_skills, labels, mask in loader:
        logits = model(tokens, next_skills)
        selected_logits = logits[mask]
        selected_labels = labels[mask]
        loss = criterion(selected_logits, selected_labels)

        count = int(selected_labels.numel())
        total_loss += float(loss.item()) * count
        total_count += count
        target_parts.append(selected_labels.numpy())
        probability_parts.append(torch.sigmoid(selected_logits).numpy())

    targets = np.concatenate(target_parts)
    probabilities = np.concatenate(probability_parts)
    return total_loss / total_count, calculate_metrics(targets, probabilities)


def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    gradient_clip: float,
) -> float:
    model.train()
    total_loss = 0.0
    total_count = 0

    for tokens, next_skills, labels, mask in loader:
        optimizer.zero_grad(set_to_none=True)
        logits = model(tokens, next_skills)
        selected_logits = logits[mask]
        selected_labels = labels[mask]
        loss = criterion(selected_logits, selected_labels)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), gradient_clip)
        optimizer.step()

        count = int(selected_labels.numel())
        total_loss += float(loss.item()) * count
        total_count += count

    return total_loss / total_count


def evaluate_history_baseline(data: pd.DataFrame) -> dict[str, float]:
    eligible = data[data["user_position"] > 0].copy()
    user_group = data.groupby("user_id", sort=False)
    attempts_before = user_group.cumcount()
    correct_before = user_group["target"].cumsum() - data["target"]
    probabilities = ((correct_before + 1.0) / (attempts_before + 2.0)).loc[
        eligible.index
    ]
    return calculate_metrics(
        eligible["target"].to_numpy(dtype=int),
        probabilities.to_numpy(dtype=float),
    )


def evaluate_xgboost_on_matched_rows(data: pd.DataFrame) -> dict[str, float] | None:
    preprocessor_path = ARTIFACT_DIR / "preprocessor.joblib"
    model_path = ARTIFACT_DIR / "xgboost_model.json"
    schema_path = ARTIFACT_DIR / "feature_schema.json"
    if not (preprocessor_path.exists() and model_path.exists() and schema_path.exists()):
        return None

    import xgboost as xgb

    with schema_path.open("r", encoding="utf-8") as file:
        schema = json.load(file)

    full_data = pd.read_parquet(DATA_DIR / "test.parquet")
    full_data = full_data.sort_values(["user_id", "end_time", "id"]).reset_index(drop=True)
    matched = full_data[full_data.groupby("user_id", sort=False).cumcount() > 0].copy()
    for column in schema["categorical_features"]:
        matched[column] = matched[column].fillna("unknown").astype(str)

    preprocessor = joblib.load(preprocessor_path)
    transformed = preprocessor.transform(matched[schema["model_features"]])
    model = xgb.XGBClassifier()
    model.load_model(model_path)
    model.set_params(device="cpu")
    probabilities = model.predict_proba(transformed)[:, 1]
    return calculate_metrics(matched["target"].to_numpy(dtype=int), probabilities)


def print_metrics(name: str, metrics: dict[str, float]) -> None:
    print(f"\n{name}")
    for key, value in metrics.items():
        if key == "rows":
            print(f"  {key}: {value:,}")
        else:
            print(f"  {key}: {value:.6f}")


def main() -> None:
    args = parse_args()
    epochs = 1 if args.smoke_test else args.epochs
    configuration = Configuration(
        random_seed=args.seed,
        embedding_dim=args.embedding_dim,
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        max_sequence_length=args.max_sequence_length,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        max_epochs=epochs,
        patience=args.patience,
        gradient_clip=args.gradient_clip,
        threads=args.threads,
    )
    set_reproducibility(configuration.random_seed, configuration.threads)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading student-disjoint splits...")
    train = load_split("train", args.smoke_test)
    validation = load_split("validation", args.smoke_test)
    test = load_split("test", args.smoke_test)
    skill_to_index, skill_codes = build_skill_vocabulary(train)

    print(
        f"Rows: train={len(train):,}, validation={len(validation):,}, "
        f"test={len(test):,}; skills={len(skill_codes):,}"
    )

    train_dataset = SequenceDataset(
        train, skill_to_index, configuration.max_sequence_length
    )
    validation_dataset = SequenceDataset(
        validation, skill_to_index, configuration.max_sequence_length
    )
    test_dataset = SequenceDataset(
        test, skill_to_index, configuration.max_sequence_length
    )

    generator = torch.Generator().manual_seed(configuration.random_seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=configuration.batch_size,
        shuffle=True,
        generator=generator,
        num_workers=0,
        collate_fn=collate_sequences,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=configuration.batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=collate_sequences,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=configuration.batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=collate_sequences,
    )

    train_pairs = sum(len(sample[0]) for sample in train_dataset.samples)
    validation_pairs = sum(len(sample[0]) for sample in validation_dataset.samples)
    test_pairs = sum(len(sample[0]) for sample in test_dataset.samples)
    print(
        f"Next-response pairs: train={train_pairs:,}, "
        f"validation={validation_pairs:,}, test={test_pairs:,}"
    )

    model = GRUDKT(
        number_of_skills=len(skill_codes),
        embedding_dim=configuration.embedding_dim,
        hidden_dim=configuration.hidden_dim,
        dropout=configuration.dropout,
    )
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=configuration.learning_rate,
        weight_decay=configuration.weight_decay,
    )
    criterion = nn.BCEWithLogitsLoss()
    checkpoint_path = ARTIFACT_DIR / (
        "dkt_smoke_model.pt" if args.smoke_test else "dkt_model.pt"
    )

    print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")
    print(f"PyTorch threads: {torch.get_num_threads()}")
    best_validation_loss = math.inf
    best_epoch = 0
    epochs_without_improvement = 0
    history = []
    training_started = time.time()

    for epoch in range(1, configuration.max_epochs + 1):
        epoch_started = time.time()
        train_loss = train_epoch(
            model,
            train_loader,
            optimizer,
            criterion,
            configuration.gradient_clip,
        )
        validation_loss, validation_metrics = evaluate_model(
            model, validation_loader, criterion
        )
        duration = time.time() - epoch_started
        epoch_result = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "validation_metrics": validation_metrics,
            "duration_seconds": duration,
        }
        history.append(epoch_result)
        print(
            f"Epoch {epoch:02d}: train_loss={train_loss:.6f}, "
            f"val_loss={validation_loss:.6f}, "
            f"val_auc={validation_metrics['roc_auc']:.6f}, "
            f"time={duration / 60:.2f} min"
        )

        if validation_loss < best_validation_loss - 1e-5:
            best_validation_loss = validation_loss
            best_epoch = epoch
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "configuration": asdict(configuration),
                    "skill_codes": skill_codes,
                    "best_epoch": best_epoch,
                    "best_validation_loss": best_validation_loss,
                },
                checkpoint_path,
            )
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= configuration.patience:
                print("Early stopping activated.")
                break

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    validation_loss, validation_metrics = evaluate_model(
        model, validation_loader, criterion
    )
    test_loss, test_metrics = evaluate_model(model, test_loader, criterion)
    history_baseline = evaluate_history_baseline(test)
    xgboost_matched = None
    if not args.smoke_test:
        print("\nEvaluating deployed XGBoost on identical next-response rows...")
        xgboost_matched = evaluate_xgboost_on_matched_rows(test)

    print_metrics("DKT validation", validation_metrics)
    print_metrics("DKT test", test_metrics)
    print_metrics("History baseline - matched test rows", history_baseline)
    if xgboost_matched is not None:
        print_metrics("XGBoost - matched test rows", xgboost_matched)

    report = {
        "experiment": "compact_gru_dkt_smoke" if args.smoke_test else "compact_gru_dkt",
        "device": "cpu",
        "torch_version": torch.__version__,
        "configuration": asdict(configuration),
        "number_of_skills_including_unknown": len(skill_codes),
        "model_parameters": sum(p.numel() for p in model.parameters()),
        "train_students": int(train["user_id"].nunique()),
        "validation_students": int(validation["user_id"].nunique()),
        "test_students": int(test["user_id"].nunique()),
        "train_pairs": train_pairs,
        "validation_pairs": validation_pairs,
        "test_pairs": test_pairs,
        "best_epoch": best_epoch,
        "best_validation_loss": best_validation_loss,
        "validation": validation_metrics,
        "test": test_metrics,
        "history_baseline_matched_test": history_baseline,
        "xgboost_matched_test": xgboost_matched,
        "training_duration_seconds": time.time() - training_started,
        "epoch_history": history,
    }
    report_path = REPORT_DIR / (
        "dkt_smoke_metrics.json" if args.smoke_test else "dkt_metrics.json"
    )
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    schema_path = ARTIFACT_DIR / (
        "dkt_smoke_schema.json" if args.smoke_test else "dkt_schema.json"
    )
    with schema_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "skill_codes": skill_codes,
                "unknown_skill": UNKNOWN_SKILL,
                "pad_token": PAD_TOKEN,
                "interaction_encoding": "1 + 2 * skill_index + correctness",
                "target": "next interaction correctness",
                "configuration": asdict(configuration),
            },
            file,
            indent=2,
        )

    print(f"\nBest epoch: {best_epoch}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Schema: {schema_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
