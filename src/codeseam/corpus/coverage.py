from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FingerprintSample:
    sample_id: str
    vector: tuple[float, ...]
    label: str
    factors: tuple[tuple[str, str], ...] = ()


def novelty(vector: tuple[float, ...], selected: list[FingerprintSample]) -> float:
    if not selected:
        return float("inf")
    return min(_distance(vector, item.vector) for item in selected)


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
                novelty(item.vector, selected),
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
    collisions = []
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            distance = _distance(left.vector, right.vector)
            if distance <= epsilon and left.label != right.label:
                collisions.append((left.sample_id, right.sample_id, distance))
    return collisions


def factor_coverage(items: list[FingerprintSample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = "|".join(f"{name}={value}" for name, value in sorted(item.factors))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("fingerprints must have equal dimensions")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
