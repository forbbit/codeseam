from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import subprocess
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import torch

from codeseam.core.feature_model import FEATURE_MODEL_VERSION
from codeseam.core.hard_dp import best_segmentation
from codeseam.core.structured_energy import ENERGY_SCHEMA_VERSION, StructuredScorer
from codeseam.corpus.metrics import aggregate_matches, match_boundaries
from codeseam.evaluation.formal_metrics import evaluate_formal
from codeseam.training.config import TrainingConfig
from codeseam.training.corpus import load_structured_examples
from codeseam.training.structured_loss import balanced_boundary_loss, structured_nll

FORMAL_ARTIFACT_VERSION = "codeseam-formal-structured-model"
PROTOCOL_VERSION = "formal-training-protocol"


def dataset_identity(corpus: Path) -> dict[str, object]:
    """Hash all supervised truth and verify the declared project-isolated split."""

    manifest = corpus / "manifest.jsonl"
    split_file = corpus / "split_projects.json"
    if not manifest.is_file() or not split_file.is_file():
        raise ValueError("formal corpus requires manifest.jsonl and split_projects.json")
    records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    declared = json.loads(split_file.read_text(encoding="utf-8"))["projects"]
    observed: dict[str, str] = {}
    split_samples: dict[str, list[str]] = {name: [] for name in ("train", "validation", "test")}
    for record in records:
        project = record["provenance"]["project"]
        split = record["split"]
        source = corpus / record["relative_path"]
        if not source.is_file():
            raise ValueError(f"missing supervised source: {record['relative_path']}")
        actual_source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        declared_source_hash = record.get("source_sha256") or record["provenance"].get(
            "source_sha256"
        )
        if actual_source_hash != declared_source_hash:
            raise ValueError(f"source hash mismatch: {record['sample_id']}")
        if declared.get(project) != split:
            raise ValueError(f"project split mismatch: {project}")
        if project in observed and observed[project] != split:
            raise ValueError(f"project leakage across splits: {project}")
        observed[project] = split
        split_samples[split].append(record["sample_id"])
    digest = hashlib.sha256()
    digest.update(manifest.read_bytes())
    digest.update(b"\0")
    digest.update(split_file.read_bytes())
    for record in sorted(records, key=lambda item: item["sample_id"]):
        digest.update(b"\0")
        digest.update((corpus / record["relative_path"]).read_bytes())
    return {
        "dataset_sha256": digest.hexdigest(),
        "record_count": len(records),
        "projects": len(observed),
        "split_samples": {key: sorted(value) for key, value in split_samples.items()},
        "split_projects": {
            split: sorted(project for project, value in observed.items() if value == split)
            for split in split_samples
        },
    }


def train_formal(
    corpus: Path,
    artifact: Path,
    *,
    config: TrainingConfig | None = None,
    scorer: StructuredScorer | None = None,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Train on train, select on validation, and never load the test examples."""

    config = config or TrainingConfig()
    identity = dataset_identity(corpus)
    _set_determinism(config.random_seed)
    device = _resolve_device(config.device)
    train_examples = load_structured_examples(corpus, "train")
    validation_examples = load_structured_examples(corpus, "validation")
    if not train_examples or not validation_examples:
        raise ValueError("formal training requires non-empty train and validation splits")
    if {item.project for item in train_examples} & {item.project for item in validation_examples}:
        raise ValueError("project leakage between train and validation")

    model = (scorer or StructuredScorer()).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    best_state = copy.deepcopy(model.state_dict())
    best_validation = float("inf")
    best_f1_exact = -1.0
    best_f1_tolerance_1 = -1.0
    best_epoch = 0
    stale_epochs = 0
    history: list[dict[str, float | int]] = []
    optimizer_updates = 0
    for epoch in range(1, config.epochs + 1):
        progress_fraction = min(1.0, (epoch - 1) / max(1, config.schedule_epochs - 1))
        schedule = 0.5 * (1.0 + math.cos(math.pi * progress_fraction))
        learning_rate = config.learning_rate * (
            config.final_learning_rate_ratio
            + (1.0 - config.final_learning_rate_ratio) * schedule
        )
        auxiliary_weight = (
            config.final_boundary_auxiliary_weight
            + (
                config.boundary_auxiliary_weight
                - config.final_boundary_auxiliary_weight
            )
            * schedule
        )
        for group in optimizer.param_groups:
            group["lr"] = learning_rate
        model.train()
        order = list(range(len(train_examples)))
        random.Random(config.random_seed + epoch).shuffle(order)
        train_raw_total = 0.0
        train_normalized_total = 0.0
        train_auxiliary_total = 0.0
        for batch_start in range(0, len(order), config.batch_size):
            batch_indices = order[batch_start : batch_start + config.batch_size]
            optimizer.zero_grad()
            batch_loss = None
            for index in batch_indices:
                item = train_examples[index]
                energy = model(item.region)
                item_loss = structured_nll(
                    energy, list(item.true_cuts),
                    temperature=config.soft_dp_temperature,
                )
                if not torch.isfinite(item_loss):
                    raise FloatingPointError("non-finite structured loss")
                normalized = item_loss / _loss_scale(energy)
                auxiliary = balanced_boundary_loss(energy, list(item.true_cuts))
                optimized_loss = (
                    normalized
                    + auxiliary_weight * auxiliary
                )
                train_raw_total += float(item_loss.detach())
                train_normalized_total += float(normalized.detach())
                train_auxiliary_total += float(auxiliary.detach())
                batch_loss = (
                    optimized_loss if batch_loss is None else batch_loss + optimized_loss
                )
            assert batch_loss is not None
            (batch_loss / len(batch_indices)).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.gradient_clip)
            optimizer.step()
            optimizer_updates += 1
        validation = _epoch_validation(
            model, validation_examples, config.soft_dp_temperature
        )
        validation_nll = float(validation["normalized_structured_nll"])
        row: dict[str, float | int] = {
            "epoch": epoch,
            "optimizer_updates": optimizer_updates,
            "learning_rate": learning_rate,
            "boundary_auxiliary_weight": auxiliary_weight,
            "train_structured_nll": train_raw_total / len(train_examples),
            "train_normalized_structured_nll": (
                train_normalized_total / len(train_examples)
            ),
            "train_boundary_auxiliary_loss": train_auxiliary_total / len(train_examples),
            "validation_structured_nll": float(validation["structured_nll"]),
            "validation_normalized_structured_nll": validation_nll,
            "validation_f1_exact": float(validation["f1_exact"]),
            "validation_f1_tolerance_1": float(validation["f1_tolerance_1"]),
            "validation_predicted_cuts": int(validation["predicted_cuts"]),
            "validation_truth_cuts": int(validation["truth_cuts"]),
        }
        history.append(row)
        f1_exact = float(validation["f1_exact"])
        f1_tolerance_1 = float(validation["f1_tolerance_1"])
        improved = (
            f1_exact > best_f1_exact
            or (
                f1_exact == best_f1_exact
                and (
                    f1_tolerance_1 > best_f1_tolerance_1
                    or (
                        f1_tolerance_1 == best_f1_tolerance_1
                        and validation_nll
                        < best_validation - config.minimum_validation_improvement
                    )
                )
            )
        )
        if improved:
            best_validation = validation_nll
            best_f1_exact = f1_exact
            best_f1_tolerance_1 = f1_tolerance_1
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
            improved = True
        else:
            stale_epochs += 1
        if progress is not None:
            progress(
                {
                    **row,
                    "epochs": config.epochs,
                    "improved": improved,
                    "best_epoch": best_epoch,
                    "best_validation_structured_nll": best_validation,
                    "best_validation_f1_exact": best_f1_exact,
                    "best_validation_f1_tolerance_1": best_f1_tolerance_1,
                    "stale_epochs": stale_epochs,
                    "early_stopping_patience": config.early_stopping_patience,
                }
            )
        if (
            epoch >= config.minimum_epochs
            and not improved
            and stale_epochs >= config.early_stopping_patience
        ):
            break
    model.load_state_dict(best_state)
    validation_metrics = evaluate_formal(
        model, validation_examples, temperature=config.soft_dp_temperature
    )
    payload = {
        "schema_version": FORMAL_ARTIFACT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "feature_version": FEATURE_MODEL_VERSION,
        "energy_version": ENERGY_SCHEMA_VERSION,
        "training": asdict(config),
        "dataset": identity,
        "selection": {
            "metric": "validation_f1_exact_then_tolerance_1_then_normalized_nll",
            "best_epoch": best_epoch,
            "best_value": {
                "f1_exact": best_f1_exact,
                "f1_tolerance_1": best_f1_tolerance_1,
                "normalized_structured_nll": best_validation,
            },
            "epochs_completed": len(history),
            "stopped_early": len(history) < config.epochs,
            "optimizer_updates": optimizer_updates,
        },
        "validation_metrics": validation_metrics,
        "history": history,
        "source_commit": _source_commit(corpus),
        "state_dict": {name: value.detach().tolist() for name, value in model.state_dict().items()},
        "test_status": "sealed_not_loaded",
    }
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def evaluate_sealed_test(corpus: Path, artifact: Path, report: Path) -> dict[str, object]:
    """Open the test split only for a frozen, provenance-matching artifact."""

    receipt = artifact.with_suffix(artifact.suffix + ".test-opened.json")
    if receipt.exists():
        raise FileExistsError("sealed test has already been opened for this artifact")
    if report.exists():
        raise FileExistsError("sealed test report already exists; refusing to overwrite it")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    if payload.get("schema_version") != FORMAL_ARTIFACT_VERSION:
        raise ValueError("not a formal structured artifact")
    if payload.get("feature_version") != FEATURE_MODEL_VERSION:
        raise ValueError("formal artifact feature version does not match current code")
    current = dataset_identity(corpus)
    if current["dataset_sha256"] != payload["dataset"]["dataset_sha256"]:
        raise ValueError("dataset changed after model selection")
    model = StructuredScorer()
    _load_state(model, payload["state_dict"])
    test_examples = load_structured_examples(corpus, "test")
    result = {
        "schema_version": "sealed-test-report",
        "model_artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "dataset_sha256": current["dataset_sha256"],
        "test_metrics": evaluate_formal(model, test_examples),
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "sealed-test-receipt",
                "model_artifact_sha256": result["model_artifact_sha256"],
                "report": str(report.resolve()),
                "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def load_formal_artifact(path: Path, scorer: StructuredScorer) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != FORMAL_ARTIFACT_VERSION:
        raise ValueError("unsupported formal model schema")
    if payload.get("feature_version") != FEATURE_MODEL_VERSION:
        raise ValueError("formal artifact feature version does not match current code")
    _load_state(scorer, payload["state_dict"])
    return payload


def _epoch_validation(model, examples, temperature: float) -> dict[str, float | int]:
    model.eval()
    losses = []
    normalized_losses = []
    exact_matches = []
    tolerance_matches = []
    predicted_cuts = 0
    truth_cuts = 0
    with torch.no_grad():
        for item in examples:
            energy = model(item.region)
            truth = list(item.true_cuts)
            predicted, _ = best_segmentation(energy)
            loss = structured_nll(energy, truth, temperature=temperature)
            losses.append(float(loss))
            normalized_losses.append(float(loss / _loss_scale(energy)))
            exact_matches.append(match_boundaries(predicted, truth))
            tolerance_matches.append(match_boundaries(predicted, truth, tolerance=1))
            predicted_cuts += len(predicted)
            truth_cuts += len(truth)
    exact = aggregate_matches(exact_matches)
    tolerance = aggregate_matches(tolerance_matches)
    return {
        "structured_nll": sum(losses) / len(losses),
        "normalized_structured_nll": sum(normalized_losses) / len(normalized_losses),
        "f1_exact": exact.f1,
        "f1_tolerance_1": tolerance.f1,
        "predicted_cuts": predicted_cuts,
        "truth_cuts": truth_cuts,
    }


def _loss_scale(energy) -> int:
    """Normalize structured NLL by the number of legal decisions in a region."""
    return max(1, int(energy.legal_boundaries.sum().item()))


def _set_determinism(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)


def _resolve_device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA training requested but CUDA is not available")
    return torch.device(requested)


def _load_state(model: StructuredScorer, values: dict[str, object]) -> None:
    current = model.state_dict()
    model.load_state_dict(
        {name: torch.tensor(value, dtype=current[name].dtype) for name, value in values.items()}
    )


def _source_commit(corpus: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=corpus, check=True, capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
