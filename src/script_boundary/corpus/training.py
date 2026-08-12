from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from script_boundary.core.features import extract_boundaries
from script_boundary.core.scoring import DEFAULT_WEIGHTS
from script_boundary.languages.matlab import MatlabFrontend


@dataclass(frozen=True, slots=True)
class TrainingExample:
    features: dict[str, float]
    raw_features: dict[str, float]
    label: str
    sample_id: str


def load_examples(corpus: Path, split: str) -> list[TrainingExample]:
    manifest = corpus / "manifest.jsonl"
    examples: list[TrainingExample] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["split"] != split:
            continue
        path = corpus / record["relative_path"]
        program = MatlabFrontend().analyze_source(path.read_bytes(), str(path))
        boundaries = [item for region in program.regions for item in extract_boundaries(region)]
        lookup = {(item.region_id, item.boundary): item for item in boundaries}
        for truth in record["boundaries"]:
            key = (truth.get("region_id", "script:top-level"), truth.get("boundary"))
            if key in lookup:
                examples.append(
                    TrainingExample(
                        features=lookup[key].features,
                        raw_features=lookup[key].raw_features,
                        label=truth["label"],
                        sample_id=record["sample_id"],
                    )
                )
    return examples


def train_weights(corpus: Path, output: Path) -> dict[str, object]:
    train = load_examples(corpus, "train")
    validation = load_examples(corpus, "validation")
    if not train:
        raise ValueError("training split has no labeled examples")
    feature_names = tuple(DEFAULT_WEIGHTS)
    candidates = _candidate_weights(feature_names)
    ranked = sorted(
        candidates,
        key=lambda weights: (
            _ranking_accuracy(train, weights),
            _ranking_accuracy(validation, weights),
        ),
        reverse=True,
    )
    best_train_score = _ranking_accuracy(train, ranked[0])
    train_tied = [
        weights for weights in ranked if _ranking_accuracy(train, weights) == best_train_score
    ]
    best = max(train_tied, key=lambda weights: _ranking_accuracy(validation, weights))
    artifact: dict[str, object] = {
        "schema_version": "1.0",
        "feature_schema": "boundary-features-v6",
        "method": "deterministic_constrained_grid_search",
        "feature_order": list(feature_names),
        "weights": best,
        "metrics": {
            "train_pairwise_accuracy": _ranking_accuracy(train, best),
            "validation_pairwise_accuracy": _ranking_accuracy(validation, best),
            "train_examples": len(train),
            "validation_examples": len(validation),
        },
        "constraints": {"non_negative": True, "normalized_sum": 1.0},
        "note": "Synthetic-corpus artifact; real-project validation is still required.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def evaluate_weight_artifact(corpus: Path, artifact_path: Path, split: str) -> float:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    return _ranking_accuracy(load_examples(corpus, split), artifact["weights"])


def _candidate_weights(feature_names: tuple[str, ...]):
    # Bounded single/pair perturbations remain deterministic as the feature set grows.
    levels = (0.5, 1.5)
    yield _normalized(dict(DEFAULT_WEIGHTS))
    for index, name in enumerate(feature_names):
        for level in levels:
            raw = dict(DEFAULT_WEIGHTS)
            raw[name] *= level
            yield _normalized(raw)
        for other in feature_names[index + 1 :]:
            for first_level in levels:
                for second_level in levels:
                    raw = dict(DEFAULT_WEIGHTS)
                    raw[name] *= first_level
                    raw[other] *= second_level
                    yield _normalized(raw)


def _ranking_accuracy(examples: list[TrainingExample], weights: dict[str, float]) -> float:
    by_sample: dict[str, list[TrainingExample]] = {}
    for example in examples:
        by_sample.setdefault(example.sample_id, []).append(example)
    correct = total = 0
    for sample_examples in by_sample.values():
        positives = [item for item in sample_examples if item.label == "preferred_cut"]
        negatives = [
            item for item in sample_examples if item.label in {"discouraged_cut", "forbidden_cut"}
        ]
        for positive in positives:
            for negative in negatives:
                total += 1
                correct += int(_score(positive, weights) > _score(negative, weights))
    return correct / total if total else 0.0


def _score(example: TrainingExample, weights: dict[str, float]) -> float:
    return sum(weights.get(name, 0.0) * value for name, value in example.features.items())


def _normalized(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    return {name: value / total for name, value in weights.items()}
