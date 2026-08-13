from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product

from codeseam.corpus.fingerprint import NormalizedFingerprint, mixed_distance


@dataclass(frozen=True, slots=True)
class FingerprintSample:
    sample_id: str
    vector: tuple[float, ...] = ()
    label: str = "ambiguous"
    factors: tuple[tuple[str, str], ...] | Mapping[str, str] = ()
    semantic_program_id: str = ""
    renderer_variant_id: str = ""
    split: str = "train"
    counterfactual_family: str = ""
    pair_id: str = ""
    polarity: str = ""
    fingerprint: NormalizedFingerprint | None = None
    boundary_index: int = 0
    target_boundary: bool = False
    requested_factors: tuple[tuple[str, str], ...] | Mapping[str, str] = ()
    observed_factors: tuple[tuple[str, str], ...] | Mapping[str, str] = ()
    renderer_trace_id: str = ""

    def factor_map(self) -> dict[str, str]:
        return dict(self.factors)


@dataclass(frozen=True, slots=True)
class CoverageDesign:
    factor_domains: Mapping[str, tuple[str, ...]]
    required_pairs: tuple[tuple[str, str], ...] = ()
    required_triples: tuple[tuple[str, str, str], ...] = ()
    required_cf_families: tuple[str, ...] = ()
    labels: tuple[str, ...] = ("cut", "no_cut", "ambiguous")


@dataclass(frozen=True, slots=True)
class CollisionRecord:
    left_id: str
    right_id: str
    distance: float
    block_distances: tuple[tuple[str, float], ...]
    label_pair: tuple[str, str]
    classification: str
    reason: str


def novelty(vector: tuple[float, ...], selected: list[FingerprintSample]) -> float:
    if not selected:
        return float("inf")
    return min(_vector_distance(vector, item.vector) for item in selected)


def coverage_sample(items: list[FingerprintSample], limit: int) -> list[FingerprintSample]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if len(items) <= limit:
        return list(items)
    selected = [min(items, key=lambda item: item.sample_id)]
    remaining = [item for item in items if item is not selected[0]]
    while remaining and len(selected) < limit:
        candidate = max(
            remaining,
            key=lambda item: (
                _sample_novelty(item, selected),
                sum(other.label != item.label for other in selected),
                item.sample_id,
            ),
        )
        selected.append(candidate)
        remaining.remove(candidate)
    return selected


def contradictory_collisions(
    items: list[FingerprintSample], *, epsilon: float = 1e-9
) -> list[tuple[str, str, float]]:
    return [
        (item.left_id, item.right_id, item.distance)
        for item in collision_audit(items, radii=(epsilon,))
        if item.distance <= epsilon
    ]


def collision_audit(
    items: list[FingerprintSample], *, radii: tuple[float, ...] = (0.0, 0.02, 0.05)
) -> list[CollisionRecord]:
    records = []
    radius = max(radii)
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if left.label == right.label or "ambiguous" in {left.label, right.label}:
                continue
            same_boundary = (
                left.semantic_program_id
                and left.semantic_program_id == right.semantic_program_id
                and left.renderer_variant_id == right.renderer_variant_id
                and left.boundary_index == right.boundary_index
            )
            distance, blocks, missing = _sample_distance(left, right)
            if distance > radius:
                continue
            exact = distance == 0.0 and missing == 0.0
            if same_boundary:
                classification, reason = (
                    "data_bug",
                    "same semantic program, render and candidate boundary has opposite truth",
                )
            elif missing >= 0.5:
                classification, reason = "unresolved", "missingness dominates observable distance"
            elif exact:
                classification, reason = (
                    "potential_missing_raw_fact",
                    "opposite candidate-level truths have identical typed observations",
                )
            elif left.factor_map() != right.factor_map():
                classification, reason = (
                    "healthy",
                    "near pair differs in traceable semantic factors",
                )
            else:
                classification, reason = (
                    "potential_missing_raw_fact",
                    "candidate-level semantic truth differs without sufficient observed delta",
                )
            records.append(
                CollisionRecord(
                    left.sample_id,
                    right.sample_id,
                    distance,
                    blocks,
                    (left.label, right.label),
                    classification,
                    reason,
                )
            )
    return records


def factor_coverage(items: list[FingerprintSample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = "|".join(f"{name}={value}" for name, value in sorted(item.factor_map().items()))
        counts[key] = counts.get(key, 0) + 1
    return counts


def audit_coverage(items: list[FingerprintSample], design: CoverageDesign) -> dict[str, object]:
    factor_label: dict[str, object] = {}
    for factor, domain in design.factor_domains.items():
        cells = {}
        empty = []
        for value, label in product(domain, design.labels):
            count = sum(
                item.factor_map().get(factor) == value and item.label == label for item in items
            )
            cells[f"{value}|{label}"] = count
            if count == 0:
                empty.append([value, label])
        factor_label[factor] = {
            "cells": cells,
            "empty_cells": empty,
            "coverage_ratio": 1.0 - len(empty) / max(1, len(cells)),
        }
    pairwise = {
        "×".join(pair): _combination_coverage(items, design, pair) for pair in design.required_pairs
    }
    three_way = {
        "×".join(triple): _combination_coverage(items, design, triple)
        for triple in design.required_triples
    }
    cf = {}
    for family in design.required_cf_families:
        observed = {
            (item.label, item.polarity)
            for item in items
            if item.counterfactual_family == family and item.target_boundary
        }
        expected = {
            (label, polarity) for label in ("cut", "no_cut") for polarity in ("low", "high")
        }
        cf[family] = {
            "complete": observed >= expected,
            "missing_quadrants": sorted([list(item) for item in expected - observed]),
        }
    leakage = _leakage(items)
    return {
        "factor_label": factor_label,
        "pairwise": pairwise,
        "three_way": three_way,
        "counterfactual": cf,
        "leakage": leakage,
        "novelty": novelty_report(items),
    }


def novelty_report(items: list[FingerprintSample]) -> dict[str, object]:
    result = {}
    train = [item for item in items if item.split == "train"]
    for split in sorted({item.split for item in items}):
        group = [item for item in items if item.split == split]
        distances = []
        for item in group:
            candidates = (
                train
                if split != "train"
                else [other for other in group if other.sample_id != item.sample_id]
            )
            if candidates:
                distances.append(min(_sample_distance(item, other)[0] for other in candidates))
        result[split] = _quantiles(distances)
    return result


def _combination_coverage(items, design, factors):
    target_items = [item for item in items if item.target_boundary]
    if target_items:
        items = target_items
    expected = list(product(*(design.factor_domains[name] for name in factors)))
    observed = Counter(tuple(item.factor_map().get(name) for name in factors) for item in items)
    return {
        "expected_cells": len(expected),
        "observed_cells": sum(observed[cell] > 0 for cell in expected),
        "empty_cells": [list(cell) for cell in expected if observed[cell] == 0],
        "counts": {"|".join(cell): observed[cell] for cell in expected},
    }


def _leakage(items):
    splits = defaultdict(set)
    render_splits = defaultdict(set)
    for item in items:
        if item.semantic_program_id:
            splits[item.semantic_program_id].add(item.split)
        if item.renderer_variant_id:
            render_splits[item.renderer_variant_id].add(item.split)
    leaked = sorted(key for key, values in splits.items() if len(values) > 1)
    render_leaked = sorted(key for key, values in render_splits.items() if len(values) > 1)
    return {
        "leaked_semantic_programs": leaked,
        "count": len(leaked),
        "leaked_renderer_variants": render_leaked,
        "renderer_count": len(render_leaked),
        "pass": not leaked and not render_leaked,
    }


def _sample_novelty(item, selected):
    return min(_sample_distance(item, other)[0] for other in selected)


def _sample_distance(left, right):
    if left.fingerprint is not None and right.fingerprint is not None:
        result = mixed_distance(left.fingerprint, right.fingerprint)
        return result.distance, result.block_distances, result.missingness_distance
    return _vector_distance(left.vector, right.vector), (), 0.0


def _vector_distance(left, right):
    if len(left) != len(right):
        raise ValueError("fingerprints must have equal dimensions")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _quantiles(values):
    if not values:
        return {"count": 0}
    values = sorted(values)

    def at(q):
        return values[round((len(values) - 1) * q)]

    return {
        "count": len(values),
        "p0": values[0],
        "p25": at(0.25),
        "p50": at(0.5),
        "p90": at(0.9),
        "p95": at(0.95),
        "max": values[-1],
        "exact_duplicate_rate": sum(value == 0 for value in values) / len(values),
    }
