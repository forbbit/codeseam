from __future__ import annotations

import json
from pathlib import Path

from codeseam.core.scoring import ScoringConfig


def load_selection_config(path: Path) -> ScoringConfig:
    """Load a frozen explainable selection policy for analysis."""

    artifact = json.loads(path.read_text(encoding="utf-8"))
    identity = (artifact.get("schema_version"), artifact.get("feature_schema"))
    if identity != ("selection-policy-v6", "boundary-features-v6"):
        raise ValueError("unsupported selection policy schema")
    values = artifact["config"]
    return ScoringConfig(
        weights={name: float(value) for name, value in artifact["weights"].items()},
        threshold=float(values["threshold"]),
        minimum_prominence=float(values["minimum_prominence"]),
        prominence_radius=int(values["prominence_radius"]),
        boundary_reward_weight=float(values["boundary_reward_weight"]),
        cut_penalty=float(values["cut_penalty"]),
        module_quality_floor=float(values.get("module_quality_floor", 0.60)),
        module_deficit_penalty=float(values.get("module_deficit_penalty", 0.20)),
    )
