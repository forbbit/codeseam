from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

import torch

from codeseam.core.hard_dp import best_segmentation
from codeseam.core.structured_energy import StructuredScorer
from codeseam.corpus.metrics import aggregate_matches, match_boundaries
from codeseam.training.structured_loss import structured_nll
from codeseam.training.trainer import StructuredExample

METRICS_SCHEMA_VERSION = "formal-structured-metrics"


def evaluate_formal(
    scorer: StructuredScorer,
    examples: Iterable[StructuredExample],
    *,
    temperature: float = 1.0,
) -> dict[str, object]:
    """Evaluate one frozen model without changing it or its training state."""

    items = list(examples)
    rows: list[dict[str, object]] = []
    scorer.eval()
    with torch.no_grad():
        for example in items:
            energy = scorer(example.region)
            predicted, _ = best_segmentation(energy)
            truth = list(example.true_cuts)
            rows.append(
                {
                    "sample_id": example.sample_id,
                    "project": example.project,
                    "region_kind": _region_kind(example.region.id),
                    "length_bucket": _length_bucket(len(example.region.statements)),
                    "predicted": predicted,
                    "truth": truth,
                    "nll": float(
                        structured_nll(energy, truth, temperature=temperature).detach()
                    ),
                    "hard_constraint_violations": sum(
                        not bool(energy.legal_boundaries[cut - 1]) for cut in predicted
                    ),
                }
            )
    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        "overall": _aggregate(rows),
        "by_project": _group(rows, "project"),
        "project_macro": _macro(_group(rows, "project")),
        "by_region_kind": _group(rows, "region_kind"),
        "by_length_bucket": _group(rows, "length_bucket"),
    }


def _aggregate(rows: list[dict[str, object]]) -> dict[str, float | int]:
    count = len(rows)
    result: dict[str, float | int] = {"samples": count}
    for tolerance in (0, 1, 2):
        matches = aggregate_matches(
            [
                match_boundaries(row["predicted"], row["truth"], tolerance=tolerance)
                for row in rows
            ]
        )
        suffix = "exact" if tolerance == 0 else f"tolerance_{tolerance}"
        result[f"precision_{suffix}"] = matches.precision
        result[f"recall_{suffix}"] = matches.recall
        result[f"f1_{suffix}"] = matches.f1
    result["structured_nll"] = _mean([float(row["nll"]) for row in rows])
    result["exact_segmentation_accuracy"] = _mean(
        [float(row["predicted"] == row["truth"]) for row in rows]
    )
    differences = [len(row["predicted"]) - len(row["truth"]) for row in rows]
    result["average_cut_count_error"] = _mean([abs(value) for value in differences])
    result["average_overcut"] = _mean([max(value, 0) for value in differences])
    result["average_undercut"] = _mean([max(-value, 0) for value in differences])
    result["hard_constraint_violations"] = sum(
        int(row["hard_constraint_violations"]) for row in rows
    )
    return result


def _group(rows: list[dict[str, object]], key: str) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return {name: _aggregate(group) for name, group in sorted(grouped.items())}


def _macro(groups: dict[str, dict[str, float | int]]) -> dict[str, float | int]:
    keys = (
        "precision_exact", "recall_exact", "f1_exact", "f1_tolerance_1",
        "f1_tolerance_2", "exact_segmentation_accuracy", "average_cut_count_error",
    )
    return {
        "projects": len(groups),
        **{key: _mean([float(group[key]) for group in groups.values()]) for key in keys},
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _region_kind(region_id: str) -> str:
    return "script" if region_id.startswith("script:") else "function"


def _length_bucket(statement_count: int) -> str:
    if statement_count < 30:
        return "short_lt_30"
    if statement_count <= 80:
        return "medium_30_80"
    return "long_gt_80"
