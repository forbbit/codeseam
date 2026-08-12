from __future__ import annotations

from pathlib import Path

from codeseam.core.analyzer import analyze_program
from codeseam.core.features import FeatureConfig
from codeseam.core.ir import AnalysisResult
from codeseam.core.scoring import ScoringConfig
from codeseam.languages.matlab import MatlabFrontend
from codeseam.languages.matlab.project import MatlabProjectIndex, apply_project_context


def analyze_file(
    path: Path,
    *,
    window: int = 4,
    threshold: float = 0.58,
    minimum_prominence: float = 0.055,
    prominence_radius: int = 5,
    boundary_reward_weight: float = 0.85,
    cut_penalty: float = 0.03,
    module_quality_floor: float = 0.60,
    module_deficit_penalty: float = 0.20,
    scoring_config: ScoringConfig | None = None,
    project_index: MatlabProjectIndex | None = None,
) -> AnalysisResult:
    if path.suffix.lower() != ".m":
        raise ValueError("current version supports MATLAB .m files only")
    source = path.read_bytes()
    program = MatlabFrontend().analyze_source(source, str(path))
    if project_index is not None:
        apply_project_context(program, project_index)
    return analyze_program(
        program,
        FeatureConfig(window=window),
        scoring_config
        or ScoringConfig(
            threshold=threshold,
            minimum_prominence=minimum_prominence,
            prominence_radius=prominence_radius,
            boundary_reward_weight=boundary_reward_weight,
            cut_penalty=cut_penalty,
            module_quality_floor=module_quality_floor,
            module_deficit_penalty=module_deficit_penalty,
        ),
    )
