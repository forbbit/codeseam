from __future__ import annotations

from dataclasses import dataclass

import torch

from codeseam.core.ir import ExecutableRegion
from codeseam.core.structured_energy import StructuredScorer
from codeseam.training.config import TrainingConfig
from codeseam.training.structured_loss import structured_nll


@dataclass(frozen=True, slots=True)
class StructuredExample:
    region: ExecutableRegion
    true_cuts: tuple[int, ...]
    sample_id: str


def train_structured(
    examples: list[StructuredExample],
    *,
    scorer: StructuredScorer | None = None,
    config: TrainingConfig | None = None,
) -> tuple[StructuredScorer, dict[str, object]]:
    if not examples:
        raise ValueError("structured training requires examples")
    scorer = scorer or StructuredScorer()
    config = config or TrainingConfig()
    optimizer = torch.optim.Adam(
        scorer.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    history = []
    gradient_magnitudes: dict[str, float] = {}
    for _ in range(config.epochs):
        optimizer.zero_grad()
        losses = [
            structured_nll(
                scorer(item.region), list(item.true_cuts),
                temperature=config.soft_dp_temperature,
            )
            for item in examples
        ]
        loss = torch.stack(losses).mean()
        if not torch.isfinite(loss):
            raise FloatingPointError("non-finite structured loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(scorer.parameters(), config.gradient_clip)
        gradient_magnitudes = {
            name: float(parameter.grad.detach().norm())
            for name, parameter in scorer.named_parameters()
            if parameter.grad is not None
        }
        optimizer.step()
        history.append(float(loss.detach()))
    return scorer, {
        "train_structured_nll": history[-1],
        "initial_structured_nll": history[0],
        "epochs": config.epochs,
        "gradient_magnitudes": gradient_magnitudes,
        "history": history,
    }
