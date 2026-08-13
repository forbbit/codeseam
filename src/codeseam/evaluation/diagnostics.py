from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiagnosticRow:
    features: dict[str, float]
    contributions: dict[str, float]
    confidence: dict[str, float]
    label: str


def feature_diagnostics(rows: list[DiagnosticRow]) -> dict[str, object]:
    names = sorted({name for row in rows for name in row.features})
    pearson = {
        left: {right: _correlation(rows, left, right) for right in names}
        for left in names
    }
    contribution = {
        name: _mean([row.contributions.get(name, 0.0) for row in rows]) for name in names
    }
    confidence = {
        name: _mean([row.confidence.get(name, 0.0) for row in rows]) for name in names
    }
    return {
        "pearson_correlation": pearson,
        "mean_contribution": contribution,
        "mean_confidence": confidence,
        "rows": len(rows),
    }


def ablation_scores(
    rows: list[DiagnosticRow], families: dict[str, set[str]]
) -> dict[str, float]:
    """Report deterministic contribution mass removed by each feature family."""
    return {
        family: _mean(
            [sum(abs(row.contributions.get(name, 0.0)) for name in names) for row in rows]
        )
        for family, names in families.items()
    }


def _correlation(rows: list[DiagnosticRow], left: str, right: str) -> float:
    xs = [row.features.get(left, 0.0) for row in rows]
    ys = [row.features.get(right, 0.0) for row in rows]
    mx, my = _mean(xs), _mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denominator if denominator else float(left == right)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
