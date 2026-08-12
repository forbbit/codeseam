from __future__ import annotations

import itertools
import json
from pathlib import Path

from script_boundary.core.analyzer import analyze_program
from script_boundary.core.scoring import ScoringConfig
from script_boundary.corpus.metrics import aggregate_matches, match_boundaries_with_ignored
from script_boundary.corpus.schema import BoundaryLabel
from script_boundary.languages.matlab import MatlabFrontend


def tune_selection(
    corpus: Path, artifact: Path, *, tolerance: int = 2, weights_artifact: Path | None = None
) -> dict:
    rows = [json.loads(line) for line in (corpus / "manifest.jsonl").read_text().splitlines()]
    development = [row for row in rows if row["split"] != "test"]
    validation = [row for row in development if row["split"] == "validation"]
    if not validation:
        raise ValueError("selection tuning requires a non-empty validation split")
    frontend = MatlabFrontend()
    weights = _load_weights(weights_artifact) if weights_artifact else None
    programs = [
        (
            row,
            frontend.analyze_source(
                (corpus / row["relative_path"]).read_bytes(), row["relative_path"]
            ),
        )
        for row in development
    ]
    candidates = []
    for threshold, prominence, radius, reward_weight, cut_penalty in itertools.product(
        (0.50, 0.54, 0.58, 0.62),
        (0.015, 0.035, 0.055),
        (3, 5),
        (0.35, 0.60, 0.85),
        (0.005, 0.015, 0.030, 0.050),
    ):
        config = ScoringConfig(
            weights=weights or ScoringConfig().weights,
            threshold=threshold,
            minimum_prominence=prominence,
            prominence_radius=radius,
            boundary_reward_weight=reward_weight,
            cut_penalty=cut_penalty,
        )
        matches = []
        family_matches: dict[str, list] = {}
        forbidden_total = forbidden_selected = 0
        for row, program in programs:
            result = analyze_program(program, scoring_config=config)
            by_position = {(item.region_id, item.boundary): item for item in result.boundaries}
            predicted: dict[str, list[int]] = {}
            truth: dict[str, list[int]] = {}
            ignored: dict[str, list[int]] = {}
            for boundary in result.boundaries:
                if boundary.recommended:
                    predicted.setdefault(boundary.region_id, []).append(boundary.boundary)
            for item in row["boundaries"]:
                key = (item.get("region_id", "script:top-level"), item.get("boundary"))
                boundary = by_position.get(key)
                if boundary is None:
                    continue
                if item["label"] == BoundaryLabel.PREFERRED.value:
                    truth.setdefault(boundary.region_id, []).append(boundary.boundary)
                elif item["label"] in {
                    BoundaryLabel.ACCEPTABLE.value,
                    BoundaryLabel.NEUTRAL.value,
                }:
                    ignored.setdefault(boundary.region_id, []).append(boundary.boundary)
                elif item["label"] == BoundaryLabel.FORBIDDEN.value:
                    forbidden_total += 1
                    forbidden_selected += int(boundary.recommended)
            for region_id in set(predicted) | set(truth) | set(ignored):
                match = match_boundaries_with_ignored(
                    predicted.get(region_id, []),
                    truth.get(region_id, []),
                    ignored.get(region_id, []),
                    tolerance=tolerance,
                )
                matches.append(match)
                family_matches.setdefault(row["family"], []).append(match)
        metric = aggregate_matches(matches)
        family_metrics = {
            family: aggregate_matches(items) for family, items in family_matches.items()
        }
        family_f05 = {
            family: _f_beta(item.precision, item.recall, 0.5)
            for family, item in family_metrics.items()
        }
        macro_family_f05 = sum(family_f05.values()) / len(family_f05)
        forbidden_rate = forbidden_selected / forbidden_total if forbidden_total else 0.0
        objective = _f_beta(metric.precision, metric.recall, 0.5) - forbidden_rate
        candidates.append(
            (
                objective,
                macro_family_f05,
                metric.f1,
                metric.precision,
                config,
                metric,
                forbidden_rate,
                family_metrics,
            )
        )
    _, macro_family_f05, _, _, best, metric, forbidden_rate, family_metrics = max(
        candidates, key=lambda item: item[:4]
    )
    result = {
        "schema_version": "selection-policy-v6",
        "feature_schema": "boundary-features-v6",
        "tuned_on_splits": ["train", "validation"],
        "test_split_used": False,
        "tolerance_statements": tolerance,
        "weights_artifact": str(weights_artifact) if weights_artifact else None,
        "weights": best.weights,
        "config": {
            "threshold": best.threshold,
            "minimum_prominence": best.minimum_prominence,
            "prominence_radius": best.prominence_radius,
            "boundary_reward_weight": best.boundary_reward_weight,
            "cut_penalty": best.cut_penalty,
            "module_quality_floor": 0.60,
            "module_deficit_penalty": 0.20,
        },
        "development": {
            **metric.to_dict(),
            "forbidden_recommendation_rate": forbidden_rate,
            "f0_5": _f_beta(metric.precision, metric.recall, 0.5),
            "family_macro_f0_5": macro_family_f05,
            "family_f1": {family: item.f1 for family, item in sorted(family_metrics.items())},
        },
        "search_candidates": len(candidates),
    }
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def load_selection_config(path: Path) -> ScoringConfig:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    supported = {("selection-policy-v6", "boundary-features-v6")}
    identity = (artifact.get("schema_version"), artifact.get("feature_schema"))
    if identity not in supported:
        raise ValueError("unsupported selection policy schema")
    values = artifact["config"]
    return ScoringConfig(
        weights={name: float(value) for name, value in artifact["weights"].items()},
        threshold=float(values["threshold"]),
        minimum_prominence=float(values["minimum_prominence"]),
        prominence_radius=int(values["prominence_radius"]),
        boundary_reward_weight=float(values["boundary_reward_weight"]),
        cut_penalty=float(values["cut_penalty"]),
        module_quality_floor=float(values.get("module_quality_floor", 0.60)),
        module_deficit_penalty=float(values.get("module_deficit_penalty", 0.20)),
    )


def _load_weights(path: Path) -> dict[str, float]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("feature_schema") != "boundary-features-v6":
        raise ValueError("weight artifact uses an incompatible feature schema")
    return {name: float(value) for name, value in artifact["weights"].items()}


def _f_beta(precision: float, recall: float, beta: float) -> float:
    beta_squared = beta * beta
    denominator = beta_squared * precision + recall
    return (1 + beta_squared) * precision * recall / denominator if denominator else 0.0
