"""Evaluate a saved Uchko DKT checkpoint without retraining it."""

from __future__ import annotations

import json
from dataclasses import asdict

import torch
from torch import nn
from torch.utils.data import DataLoader

import train_dkt as dkt


def main() -> None:
    checkpoint_path = dkt.ARTIFACT_DIR / "dkt_model.pt"
    report_path = dkt.REPORT_DIR / "dkt_metrics.json"
    schema_path = dkt.ARTIFACT_DIR / "dkt_schema.json"

    checkpoint = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=False,
    )
    configuration = dkt.Configuration(**checkpoint["configuration"])
    skill_codes = checkpoint["skill_codes"]
    skill_to_index = {skill: index for index, skill in enumerate(skill_codes)}

    dkt.set_reproducibility(configuration.random_seed, configuration.threads)
    print("Loading validation and test splits...")
    validation = dkt.load_split("validation")
    test = dkt.load_split("test")

    validation_dataset = dkt.SequenceDataset(
        validation, skill_to_index, configuration.max_sequence_length
    )
    test_dataset = dkt.SequenceDataset(
        test, skill_to_index, configuration.max_sequence_length
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=configuration.batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=dkt.collate_sequences,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=configuration.batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=dkt.collate_sequences,
    )

    model = dkt.GRUDKT(
        number_of_skills=len(skill_codes),
        embedding_dim=configuration.embedding_dim,
        hidden_dim=configuration.hidden_dim,
        dropout=configuration.dropout,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    criterion = nn.BCEWithLogitsLoss()

    print("Evaluating saved DKT checkpoint...")
    validation_loss, validation_metrics = dkt.evaluate_model(
        model, validation_loader, criterion
    )
    test_loss, test_metrics = dkt.evaluate_model(model, test_loader, criterion)
    history_baseline = dkt.evaluate_history_baseline(test)

    print("Evaluating deployed XGBoost on identical next-response rows...")
    xgboost_matched = dkt.evaluate_xgboost_on_matched_rows(test)

    dkt.print_metrics("DKT validation", validation_metrics)
    dkt.print_metrics("DKT test", test_metrics)
    dkt.print_metrics("History baseline - matched test rows", history_baseline)
    if xgboost_matched is not None:
        dkt.print_metrics("XGBoost - matched test rows", xgboost_matched)

    report = {
        "experiment": "compact_gru_dkt",
        "device": "cpu",
        "torch_version": torch.__version__,
        "configuration": asdict(configuration),
        "number_of_skills_including_unknown": len(skill_codes),
        "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "validation_students": int(validation["user_id"].nunique()),
        "test_students": int(test["user_id"].nunique()),
        "validation_pairs": sum(len(sample[0]) for sample in validation_dataset.samples),
        "test_pairs": sum(len(sample[0]) for sample in test_dataset.samples),
        "best_epoch": int(checkpoint["best_epoch"]),
        "best_validation_loss": float(checkpoint["best_validation_loss"]),
        "validation_evaluation_loss": float(validation_loss),
        "test_evaluation_loss": float(test_loss),
        "validation": validation_metrics,
        "test": test_metrics,
        "history_baseline_matched_test": history_baseline,
        "xgboost_matched_test": xgboost_matched,
        "note": "Final metrics reconstructed from the saved best checkpoint after post-training comparison initially failed because XGBoost was unavailable.",
    }
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    with schema_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "skill_codes": skill_codes,
                "unknown_skill": dkt.UNKNOWN_SKILL,
                "pad_token": dkt.PAD_TOKEN,
                "interaction_encoding": "1 + 2 * skill_index + correctness",
                "target": "next interaction correctness",
                "configuration": asdict(configuration),
            },
            file,
            indent=2,
        )

    print(f"\nBest epoch: {checkpoint['best_epoch']}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Schema: {schema_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
