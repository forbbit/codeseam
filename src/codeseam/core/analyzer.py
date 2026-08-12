from __future__ import annotations

from codeseam.core.features import FeatureConfig, extract_boundaries
from codeseam.core.ir import AnalysisResult, ProgramIR
from codeseam.core.scoring import ScoringConfig, score_boundaries, select_recommendations


def analyze_program(
    program: ProgramIR,
    feature_config: FeatureConfig | None = None,
    scoring_config: ScoringConfig | None = None,
) -> AnalysisResult:
    feature_config = feature_config or FeatureConfig()
    scoring_config = scoring_config or ScoringConfig()
    boundaries = [
        boundary
        for region in program.regions
        for boundary in extract_boundaries(region, feature_config)
    ]
    score_boundaries(boundaries, scoring_config)
    select_recommendations(
        boundaries, scoring_config, {region.id: region for region in program.regions}
    )
    return AnalysisResult(program=program, boundaries=boundaries)
