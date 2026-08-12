from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from codeseam.core.ir import BoundaryAnalysis, ExecutableRegion
from codeseam.core.module_quality import evaluate_module

DEFAULT_WEIGHTS = {
    "variable_death": 0.06572769953051644,
    "variable_birth": 0.06572769953051644,
    "interface_compactness": 0.07511737089201878,
    "dependency_drop": 0.07511737089201878,
    "medium_dependency_drop": 0.056338028169014086,
    "vocabulary_shift": 0.06572769953051644,
    "structural_completion": 0.018779342723004695,
    "input_interface_compactness": 0.06572769953051644,
    "output_interface_compactness": 0.06572769953051644,
    "local_cohesion_support": 0.08450704225352113,
    "call_set_change": 0.056338028169014086,
    "effect_set_change": 0.018779342723004695,
    "control_followup_completion": 0.10328638497652583,
    "dependency_target_dispersion": 0.07042253521126761,
    "task_completion": 0.11267605633802817,
}


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    threshold: float = 0.58
    prominence_radius: int = 5
    minimum_prominence: float = 0.055
    boundary_reward_weight: float = 0.85
    cut_penalty: float = 0.03
    module_quality_floor: float = 0.60
    module_deficit_penalty: float = 0.20
    allow_same_line: bool = False


def score_boundaries(
    boundaries: list[BoundaryAnalysis], config: ScoringConfig | None = None
) -> None:
    config = config or ScoringConfig()
    total_weight = sum(config.weights.values())
    if total_weight <= 0:
        raise ValueError("feature weights must have a positive sum")
    for boundary in boundaries:
        boundary.score = (
            sum(config.weights.get(name, 0.0) * value for name, value in boundary.features.items())
            / total_weight
        )


def select_recommendations(
    boundaries: list[BoundaryAnalysis],
    config: ScoringConfig | None = None,
    regions: dict[str, ExecutableRegion] | None = None,
) -> None:
    config = config or ScoringConfig()
    by_region: dict[str, list[BoundaryAnalysis]] = {}
    for boundary in boundaries:
        by_region.setdefault(boundary.region_id, []).append(boundary)
    for region_boundaries in by_region.values():
        candidates: list[BoundaryAnalysis] = []
        for index, boundary in enumerate(region_boundaries):
            left = region_boundaries[index - 1].score if index else -1.0
            right = (
                region_boundaries[index + 1].score if index + 1 < len(region_boundaries) else -1.0
            )
            boundary.local_peak_candidate = boundary.score >= left and boundary.score >= right
            boundary.prominence = _prominence(region_boundaries, index, config.prominence_radius)
            # Structural rejection reasons describe the boundary itself, so retain them
            # even when the boundary is not a local-peak candidate.
            if boundary.constraints:
                boundary.rejection_reasons.append("hard_constraint")
            if not config.allow_same_line and boundary.after_line == boundary.before_line:
                boundary.rejection_reasons.append("same_line_boundary")
            if boundary.local_peak_candidate:
                if boundary.score < config.threshold:
                    boundary.rejection_reasons.append("below_score_threshold")
                if boundary.prominence < config.minimum_prominence:
                    boundary.rejection_reasons.append("low_prominence")
            if boundary.local_peak_candidate and not boundary.rejection_reasons:
                candidates.append(boundary)
        chosen = _globally_select_candidates(candidates, config, regions)
        chosen_ids = {id(item) for item in chosen}
        for candidate in candidates:
            if id(candidate) not in chosen_ids:
                candidate.rejection_reasons.append("not_in_global_optimum")
        for boundary in chosen:
            boundary.recommended = True


def _prominence(boundaries: list[BoundaryAnalysis], index: int, radius: int) -> float:
    start = max(0, index - radius)
    end = min(len(boundaries), index + radius + 1)
    neighbors = [
        boundary.score
        for offset, boundary in enumerate(boundaries[start:end], start)
        if offset != index
    ]
    if not neighbors:
        return 0.0
    return max(0.0, boundaries[index].score - median(neighbors))


def _globally_select_candidates(
    candidates: list[BoundaryAnalysis],
    config: ScoringConfig,
    regions: dict[str, ExecutableRegion] | None,
) -> list[BoundaryAnalysis]:
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: item.boundary)
    if regions is None:
        return ordered
    region = regions[ordered[0].region_id]
    statement_count = len(region.statements)
    whole_module = evaluate_module(region, 0, statement_count - 1)
    whole_quality = _interval_value(whole_module, statement_count, statement_count, config)
    best = [float("-inf")] * len(ordered)
    previous: list[int | None] = [None] * len(ordered)

    def cut_reward(item: BoundaryAnalysis) -> float:
        evidence_surplus = (item.score - config.threshold) + (
            item.prominence - config.minimum_prominence
        )
        return config.boundary_reward_weight * evidence_surplus - config.cut_penalty

    def interval_reward(start: int, end: int) -> float:
        module = evaluate_module(region, start, end)
        return _interval_value(module, end - start + 1, statement_count, config)

    for index, candidate in enumerate(ordered):
        best[index] = cut_reward(candidate) + interval_reward(0, candidate.boundary - 1)
        for prior_index in range(index):
            prior = ordered[prior_index]
            objective = (
                best[prior_index]
                + cut_reward(candidate)
                + interval_reward(prior.boundary, candidate.boundary - 1)
            )
            if objective > best[index]:
                best[index] = objective
                previous[index] = prior_index

    final_objectives = [
        objective + interval_reward(candidate.boundary, statement_count - 1)
        for objective, candidate in zip(best, ordered, strict=True)
    ]
    end_index = max(range(len(ordered)), key=final_objectives.__getitem__)
    if final_objectives[end_index] <= whole_quality:
        return []
    chosen = []
    cursor: int | None = end_index
    while cursor is not None:
        chosen.append(ordered[cursor])
        cursor = previous[cursor]
    chosen.reverse()
    return chosen


def _interval_value(module, length: int, total_length: int, config: ScoringConfig) -> float:
    weighted_quality = module.score * length / total_length
    deficit = max(0.0, config.module_quality_floor - module.score)
    return weighted_quality - config.module_deficit_penalty * deficit
