from __future__ import annotations

from torch import Tensor

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
