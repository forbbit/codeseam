from __future__ import annotations

from dataclasses import dataclass

from codeseam.core.feature_model import FEATURE_MODEL_VERSION
from codeseam.core.features import FeatureConfig, extract_boundaries
from codeseam.core.hard_dp import best_segmentation
from codeseam.core.ir import AnalysisResult, ProgramIR
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.core.structured_energy import StructuredScorer


@dataclass(frozen=True, slots=True)
class StructuredAnalysis:
    result: AnalysisResult
    energies: dict[str, float]
    cuts: dict[str, list[int]]


def analyze_program_structured(
    program: ProgramIR,
    scorer: StructuredScorer,
    feature_config: FeatureConfig | None = None,
) -> StructuredAnalysis:
    """Run deterministic Hard-DP with the exact energy used by formal training."""
    config = feature_config or FeatureConfig()
    boundaries = []
    energies = {}
    cuts = {}
    for region in program.regions:
        facts = extract_raw_facts(region, window=config.window, medium_window=config.medium_window)
        region_boundaries = extract_boundaries(region, config)
        structured = scorer(region, facts)
        chosen, score = best_segmentation(structured)
        chosen_set = set(chosen)
        for boundary, decomposition, energy in zip(
            region_boundaries,
            structured.decomposition.values.detach().tolist(),
            structured.boundary.detach().tolist(),
            strict=True,
        ):
            boundary.normalization_version = FEATURE_MODEL_VERSION
            boundary.features = dict(
                zip(structured.decomposition.names, decomposition, strict=True)
            )
            boundary.score = energy
            boundary.recommended = boundary.boundary in chosen_set
            if not boundary.recommended and not boundary.constraints:
                boundary.rejection_reasons.append("not_in_structured_optimum")
        boundaries.extend(region_boundaries)
        energies[region.id] = score
        cuts[region.id] = chosen
    return StructuredAnalysis(AnalysisResult(program, boundaries), energies, cuts)
