from __future__ import annotations

import json
from pathlib import Path

from script_boundary.core.scoring import DEFAULT_WEIGHTS
from script_boundary.corpus.training import TrainingExample, load_examples

LEGACY_FEATURES = (
    "variable_death",
    "variable_birth",
    "interface_compactness",
    "dependency_drop",
    "vocabulary_shift",
    "structural_completion",
)
LEGACY_WEIGHTS = {
    "variable_death": 0.22,
    "variable_birth": 0.14,
    "interface_compactness": 0.22,
    "dependency_drop": 0.18,
    "vocabulary_shift": 0.12,
    "structural_completion": 0.12,
}


def ablation_report(corpus: Path, split: str) -> dict[str, object]:
    examples = load_examples(corpus, split)
    manifest = {
        item["sample_id"]: item
        for item in (
            json.loads(line)
            for line in (corpus / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        )
        if item["split"] == split
    }
    return {
        "split": split,
        "legacy_pairwise_accuracy": _accuracy(examples, LEGACY_WEIGHTS),
        "expanded_pairwise_accuracy": _accuracy(examples, DEFAULT_WEIGHTS),
        "families": {
            family: {
                "legacy": _accuracy(
                    [item for item in examples if manifest[item.sample_id]["family"] == family],
                    LEGACY_WEIGHTS,
                ),
                "expanded": _accuracy(
                    [item for item in examples if manifest[item.sample_id]["family"] == family],
                    DEFAULT_WEIGHTS,
                ),
            }
            for family in sorted({item["family"] for item in manifest.values()})
        },
    }


def _accuracy(examples: list[TrainingExample], weights: dict[str, float]) -> float:
    by_sample: dict[str, list[TrainingExample]] = {}
    for example in examples:
        by_sample.setdefault(example.sample_id, []).append(example)
    correct = total = 0
    for items in by_sample.values():
        positives = [item for item in items if item.label == "preferred_cut"]
        negatives = [item for item in items if item.label in {"discouraged_cut", "forbidden_cut"}]
        for positive in positives:
            for negative in negatives:
                total += 1
                positive_score = _score(positive, weights)
                negative_score = _score(negative, weights)
                correct += int(positive_score > negative_score)
    return correct / total if total else 0.0


def _score(example: TrainingExample, weights: dict[str, float]) -> float:
    values = dict(example.features)
    if weights is LEGACY_WEIGHTS:
        values["structural_completion"] = example.raw_features.get(
            "raw_structural_completion", values["structural_completion"]
        )
    return sum(weights.get(name, 0.0) * value for name, value in values.items())
