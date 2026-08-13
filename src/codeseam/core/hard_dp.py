from __future__ import annotations

from codeseam.core.structured_energy import StructuredEnergy


def best_segmentation(energy: StructuredEnergy) -> tuple[list[int], float]:
    n = energy.statement_count
    best = [float("-inf")] * (n + 1)
    previous = [-1] * (n + 1)
    best[0] = 0.0
    boundary = energy.boundary.detach().tolist()
    segments = energy.segments.detach().tolist()
    for end in range(1, n + 1):
        for start in range(end):
            value = best[start] + segments[start][end]
            if start:
                value += boundary[start - 1]
            if value > best[end]:
                best[end] = value
                previous[end] = start
    cuts = []
    cursor = n
    while previous[cursor] > 0:
        cursor = previous[cursor]
        cuts.append(cursor)
    cuts.reverse()
    return cuts, best[n]
