from __future__ import annotations

import torch
from torch import Tensor

from codeseam.core.structured_energy import StructuredEnergy


def log_partition(energy: StructuredEnergy, *, temperature: float = 1.0) -> Tensor:
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    n = energy.statement_count
    values: list[Tensor] = [energy.segments.new_zeros(())]
    for end in range(1, n + 1):
        alternatives = []
        for start in range(end):
            score = values[start] + energy.segments[start, end]
            if start:
                score = score + energy.boundary[start - 1]
            alternatives.append(score / temperature)
        values.append(temperature * torch.logsumexp(torch.stack(alternatives), dim=0))
    return values[n]


def boundary_marginals(energy: StructuredEnergy, *, temperature: float = 1.0) -> Tensor:
    log_z = log_partition(energy, temperature=temperature)
    gradients = torch.autograd.grad(log_z, energy.boundary, create_graph=True, allow_unused=True)[0]
    return gradients if gradients is not None else torch.zeros_like(energy.boundary)
