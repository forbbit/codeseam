from __future__ import annotations

import torch
from torch import Tensor
from torch.nn import functional as F

from codeseam.core.soft_dp import log_partition
from codeseam.core.structured_energy import StructuredEnergy, segmentation_energy


def structured_nll(
    energy: StructuredEnergy, true_cuts: list[int], *, temperature: float = 1.0
) -> Tensor:
    if any(cut < 1 or cut >= energy.statement_count for cut in true_cuts):
        raise ValueError("ground-truth cut lies outside the region")
    if any(not bool(energy.legal_boundaries[cut - 1]) for cut in true_cuts):
        raise ValueError("ground-truth cut violates a hard constraint")
    return log_partition(energy, temperature=temperature) - segmentation_energy(
        energy, true_cuts
    )


def balanced_boundary_loss(energy: StructuredEnergy, true_cuts: list[int]) -> Tensor:
    """Balanced auxiliary supervision over legal boundary logits.

    Positive and negative legal positions each contribute half the loss, preventing
    the much larger no-cut class from making the all-no-cut solution attractive.
    """
    legal = energy.legal_boundaries
    logits = energy.boundary[legal]
    if logits.numel() == 0:
        return energy.boundary.new_zeros(())
    legal_indices = torch.nonzero(legal, as_tuple=False).flatten() + 1
    targets = torch.zeros_like(logits)
    if true_cuts:
        truth = torch.tensor(true_cuts, device=logits.device)
        targets = torch.isin(legal_indices, truth).to(logits.dtype)
    positive = targets == 1
    negative = ~positive
    parts = []
    if positive.any():
        parts.append(F.binary_cross_entropy_with_logits(logits[positive], targets[positive]))
    if negative.any():
        parts.append(F.binary_cross_entropy_with_logits(logits[negative], targets[negative]))
    return torch.stack(parts).mean()
