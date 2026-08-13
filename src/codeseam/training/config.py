from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

MODEL_SCHEMA_VERSION = "codeseam-structured-model-v2"


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    learning_rate: float = 0.01
    weight_decay: float = 0.001
    epochs: int = 30
    gradient_clip: float = 5.0
    soft_dp_temperature: float = 1.0

    def __post_init__(self) -> None:
        if self.learning_rate <= 0 or self.epochs < 1 or self.gradient_clip <= 0:
            raise ValueError("invalid training configuration")
        if self.soft_dp_temperature <= 0:
            raise ValueError("soft_dp_temperature must be positive")


def save_artifact(path: Path, scorer, config: TrainingConfig, metrics: dict) -> None:
    payload = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "feature_version": "boundary-features-v2-structured",
        "energy_version": "structured-energy-v2",
        "training": asdict(config),
        "state_dict": {name: value.detach().tolist() for name, value in scorer.state_dict().items()},
        "metrics": metrics,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_artifact(path: Path, scorer) -> dict:
    import torch

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != MODEL_SCHEMA_VERSION:
        raise ValueError("unsupported structured model schema")
    current = scorer.state_dict()
    state = {
        name: torch.tensor(value, dtype=current[name].dtype)
        for name, value in payload["state_dict"].items()
    }
    scorer.load_state_dict(state)
    return payload
