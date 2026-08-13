from __future__ import annotations

import hashlib
import json

import pytest

from codeseam.core.structured_energy import StructuredScorer
from codeseam.evaluation.formal_metrics import evaluate_formal
from codeseam.languages.matlab import MatlabFrontend
from codeseam.training.config import TrainingConfig
from codeseam.training.protocol import (
    dataset_identity,
    evaluate_sealed_test,
    load_formal_artifact,
    train_formal,
)
from codeseam.training.trainer import StructuredExample


def _example(sample_id: str, project: str, split: str) -> StructuredExample:
    source = b"a = rand(4,1);\nb = mean(a);\nc = fft(b);\ndisp(c);\n"
    region = MatlabFrontend().analyze_source(source, f"{sample_id}.m").regions[0]
    return StructuredExample(region, (2,), sample_id, project, split)


def _identity_corpus(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    records = []
    projects = {}
    for split in ("train", "validation", "test"):
        project = f"owner/{split}"
        projects[project] = split
        records.append(
            {
                "sample_id": split,
                "split": split,
                "relative_path": f"{split}.m",
                "source_sha256": hashlib.sha256(split.encode()).hexdigest(),
                "provenance": {"project": project},
            }
        )
        (tmp_path / f"{split}.m").write_bytes(split.encode())
    (tmp_path / "manifest.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    (tmp_path / "split_projects.json").write_text(
        json.dumps({"projects": projects}), encoding="utf-8"
    )
    return tmp_path


def test_formal_metrics_include_tolerances_macro_and_error_directions() -> None:
    report = evaluate_formal(
        StructuredScorer(),
        [_example("one", "owner/a", "validation"), _example("two", "owner/b", "validation")],
    )
    assert report["schema_version"] == "formal-structured-metrics"
    assert report["overall"]["samples"] == 2
    assert "f1_exact" in report["overall"]
    assert "f1_tolerance_1" in report["overall"]
    assert "f1_tolerance_2" in report["overall"]
    assert report["project_macro"]["projects"] == 2
    assert report["overall"]["hard_constraint_violations"] == 0


def test_dataset_identity_rejects_project_split_mismatch(tmp_path) -> None:
    corpus = _identity_corpus(tmp_path)
    payload = json.loads((corpus / "split_projects.json").read_text())
    payload["projects"]["owner/train"] = "test"
    (corpus / "split_projects.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="project split mismatch"):
        dataset_identity(corpus)


def test_dataset_identity_rejects_modified_source(tmp_path) -> None:
    corpus = _identity_corpus(tmp_path)
    (corpus / "train.m").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source hash mismatch"):
        dataset_identity(corpus)


def test_cuda_request_fails_instead_of_silently_using_cpu(monkeypatch) -> None:
    monkeypatch.setattr("torch.cuda.is_available", lambda: False)
    from codeseam.training.protocol import _resolve_device

    with pytest.raises(RuntimeError, match="CUDA is not available"):
        _resolve_device("cuda")


def test_old_feature_artifact_is_rejected(tmp_path) -> None:
    artifact = tmp_path / "old-model.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "codeseam-formal-structured-model",
                "feature_version": "older-feature-space",
                "state_dict": {},
            }
        )
    )
    with pytest.raises(ValueError, match="feature version"):
        load_formal_artifact(artifact, StructuredScorer())


def test_formal_training_never_loads_test_and_sealed_report_is_one_shot(tmp_path, monkeypatch):
    corpus = _identity_corpus(tmp_path / "corpus")
    loaded = []

    def fake_loader(_corpus, split):
        loaded.append(split)
        return [_example(split, f"owner/{split}", split)]

    monkeypatch.setattr("codeseam.training.protocol.load_structured_examples", fake_loader)
    artifact = tmp_path / "model.json"
    progress = []
    payload = train_formal(
        corpus,
        artifact,
        config=TrainingConfig(
            epochs=2, minimum_epochs=1, early_stopping_patience=1,
            batch_size=1, random_seed=7, schedule_epochs=2,
            final_learning_rate_ratio=0.1, final_boundary_auxiliary_weight=0.1,
        ),
        progress=progress.append,
    )
    assert loaded == ["train", "validation"]
    assert payload["test_status"] == "sealed_not_loaded"
    assert payload["dataset"]["dataset_sha256"]
    assert len(progress) == payload["selection"]["epochs_completed"]
    assert progress[0]["epoch"] == 1
    assert "validation_f1_exact" in progress[0]
    assert "validation_predicted_cuts" in progress[0]
    assert payload["history"][0]["validation_truth_cuts"] == 1
    assert "train_normalized_structured_nll" in payload["history"][0]
    assert "validation_normalized_structured_nll" in payload["history"][0]
    assert payload["history"][0]["learning_rate"] > payload["history"][-1]["learning_rate"]
    assert payload["history"][0]["boundary_auxiliary_weight"] > (
        payload["history"][-1]["boundary_auxiliary_weight"]
    )
    assert payload["selection"]["optimizer_updates"] == len(payload["history"])
    assert payload["selection"]["metric"] == (
        "validation_f1_exact_then_tolerance_1_then_normalized_nll"
    )
    assert set(payload["selection"]["best_value"]) == {
        "f1_exact", "f1_tolerance_1", "normalized_structured_nll"
    }

    report = tmp_path / "test-report.json"
    evaluate_sealed_test(corpus, artifact, report)
    assert loaded[-1] == "test"
    assert artifact.with_suffix(".json.test-opened.json").is_file()
    with pytest.raises(FileExistsError, match="already been opened"):
        evaluate_sealed_test(corpus, artifact, tmp_path / "different-report.json")
