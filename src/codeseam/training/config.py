from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    learning_rate: float = 0.01
    weight_decay: float = 0.001
    epochs: int = 50
    batch_size: int = 8
    gradient_clip: float = 5.0
    soft_dp_temperature: float = 1.0
    boundary_auxiliary_weight: float = 0.5
    final_boundary_auxiliary_weight: float = 0.5
    final_learning_rate_ratio: float = 1.0
    schedule_epochs: int = 50
    random_seed: int = 1729
    early_stopping_patience: int = 10
    minimum_epochs: int = 15
    minimum_validation_improvement: float = 1e-5
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.learning_rate <= 0 or self.epochs < 1 or self.gradient_clip <= 0:
            raise ValueError("invalid training configuration")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.soft_dp_temperature <= 0:
            raise ValueError("soft_dp_temperature must be positive")
        if self.boundary_auxiliary_weight < 0:
            raise ValueError("boundary_auxiliary_weight must be non-negative")
        if not 0 <= self.final_boundary_auxiliary_weight <= self.boundary_auxiliary_weight:
            raise ValueError("final boundary auxiliary weight must not exceed its initial value")
        if not 0 < self.final_learning_rate_ratio <= 1:
            raise ValueError("final_learning_rate_ratio must be in (0, 1]")
        if self.schedule_epochs < 1:
            raise ValueError("schedule_epochs must be positive")
        if self.early_stopping_patience < 1:
            raise ValueError("early_stopping_patience must be positive")
        if not 1 <= self.minimum_epochs <= self.epochs:
            raise ValueError("minimum_epochs must be between 1 and epochs")
        if self.minimum_validation_improvement < 0:
            raise ValueError("minimum_validation_improvement must be non-negative")
        if self.device not in {"cpu", "cuda"}:
            raise ValueError("device must be 'cpu' or 'cuda'")
