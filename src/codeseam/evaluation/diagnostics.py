from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiagnosticRow:
    features: dict[str, float]
    contributions: dict[str, float]
    confidence: dict[str, float]
    label: str


@dataclass(frozen=True, slots=True)
class ControlledPair:
    pair_id: str
    target_family: str
    target_features: tuple[str, ...]
    left: dict[str, float]
    right: dict[str, float]
    expected_direction: int


def feature_diagnostics(rows: list[DiagnosticRow]) -> dict[str, object]:
    names = _validate(rows)
    columns = {name: [row.features[name] for row in rows] for name in names}
    zero_variance = [name for name, values in columns.items() if len(set(values)) <= 1]
    pearson = {
        left: {right: _correlation(columns[left], columns[right]) for right in names}
        for left in names
    }
    spearman = {
        left: {
            right: _correlation(_ranks(columns[left]), _ranks(columns[right])) for right in names
        }
        for left in names
    }
    singular, rank, condition, effective = _matrix_diagnostics(columns, names)
    return {
        "pearson_correlation": pearson,
        "spearman_correlation": spearman,
        "mutual_information": {
            left: {right: _mutual_information(columns[left], columns[right]) for right in names}
            for left in names
        },
        "zero_variance_features": zero_variance,
        "singular_values": singular,
        "rank": rank,
        "effective_rank": effective,
        "condition_number": condition,
        "mean_contribution": {
            name: _mean([row.contributions.get(name, 0.0) for row in rows]) for name in names
        },
        "mean_confidence": {
            name: _mean([row.confidence.get(name, 0.0) for row in rows]) for name in names
        },
        "rows": len(rows),
    }


def controlled_pair_observability(
    pairs: list[ControlledPair], *, tolerance: float = 1e-9
) -> dict[str, object]:
    results = []
    for pair in pairs:
        keys = set(pair.left) | set(pair.right)
        target = {
            key: pair.right.get(key, 0.0) - pair.left.get(key, 0.0) for key in pair.target_features
        }
        non_target = [
            abs(pair.right.get(key, 0.0) - pair.left.get(key, 0.0))
            for key in keys - set(pair.target_features)
        ]
        signed = max(target.values(), key=abs, default=0.0) * pair.expected_direction
        target_magnitude = sum(abs(value) for value in target.values())
        non_target_sum = sum(non_target)
        results.append(
            {
                "pair_id": pair.pair_id,
                "target_family": pair.target_family,
                "target_delta": target,
                "max_non_target_delta": max(non_target, default=0.0),
                "non_target_delta_sum": non_target_sum,
                "isolation_ratio": target_magnitude / (non_target_sum + 1e-9),
                "direction_pass": signed > tolerance,
                "observability_pass": signed > tolerance
                and target_magnitude / (non_target_sum + 1e-9) >= 0.05,
            }
        )
    return {
        "pairs": results,
        "all_direction_pass": all(item["direction_pass"] for item in results),
        "all_observability_pass": bool(results)
        and all(item["observability_pass"] for item in results),
        "families": sorted({item.target_family for item in pairs}),
    }


def parameterization_diagnostics() -> dict[str, object]:
    return {
        "unrestricted_feature_weights": True,
        "unrestricted_module_weights": True,
        "bias_cut_penalty_nonidentifiable": True,
        "shared_dependency_tau": ["completion", "long_range_coupling"],
        "training_implication": "diagnostic only; do not tune until reparameterized",
    }


def ablation_scores(rows, families):
    return {
        family: _mean(
            [sum(abs(row.contributions.get(name, 0.0)) for name in names) for row in rows]
        )
        for family, names in families.items()
    }


def _validate(rows):
    if not rows:
        return []
    names = sorted(rows[0].features)
    for row in rows:
        if sorted(row.features) != names:
            raise ValueError("all diagnostic rows must have identical feature keys")
        if any(not math.isfinite(value) for value in row.features.values()):
            raise ValueError("features must be finite")
    return names


def _correlation(xs, ys):
    if not xs or len(set(xs)) <= 1 or len(set(ys)) <= 1:
        return None
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else None


def _ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j + 2) / 2
        for k in range(i, j + 1):
            ranks[order[k]] = rank
        i = j + 1
    return ranks


def _mutual_information(xs, ys, bins=5):
    if not xs:
        return 0.0

    def bucket(values, value):
        ordered = sorted(values)
        return min(
            bins - 1,
            sum(value > ordered[round((len(ordered) - 1) * q / bins)] for q in range(1, bins)),
        )

    joint = {}
    cx = {}
    cy = {}
    for x, y in zip(xs, ys, strict=True):
        a, b = bucket(xs, x), bucket(ys, y)
        joint[a, b] = joint.get((a, b), 0) + 1
        cx[a] = cx.get(a, 0) + 1
        cy[b] = cy.get(b, 0) + 1
    n = len(xs)
    return sum((c / n) * math.log((c * n) / (cx[a] * cy[b])) for (a, b), c in joint.items())


def _matrix_diagnostics(columns, names):
    if not names or not next(iter(columns.values()), []):
        return [], 0, float("inf"), 0.0
    try:
        import numpy as np

        matrix = np.array(
            [[columns[name][i] for name in names] for i in range(len(columns[names[0]]))],
            dtype=float,
        )
        std = matrix.std(axis=0)
        matrix = (matrix - matrix.mean(axis=0)) / np.where(std == 0, 1, std)
        singular = np.linalg.svd(matrix, compute_uv=False)
        tol = max(matrix.shape) * np.finfo(float).eps * (singular[0] if len(singular) else 0)
        rank = int((singular > tol).sum())
        condition = (
            float(singular[0] / singular[-1])
            if rank == min(matrix.shape) and singular[-1] > tol
            else float("inf")
        )
        p = singular / singular.sum() if singular.sum() else singular
        effective = float(math.exp(-sum(float(v) * math.log(float(v)) for v in p if v > 0)))
        return singular.tolist(), rank, condition, effective
    except ImportError:
        return [], 0, float("inf"), 0.0


def _mean(values):
    return sum(values) / len(values) if values else 0.0
