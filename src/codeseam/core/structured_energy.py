from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from codeseam.core.feature_model import ContinuousFeatureModel, FeatureDecomposition
from codeseam.core.ir import ExecutableRegion
from codeseam.core.module_quality import evaluate_module
from codeseam.core.raw_facts import BoundaryRawFacts, extract_raw_facts

ENERGY_SCHEMA_VERSION = "structured-energy-v2"
MODULE_FEATURE_NAMES = (
    "internal_cohesion", "external_compactness", "symbol_locality",
    "size_fitness", "finalization_completeness", "orphan_resistance",
)


@dataclass(frozen=True, slots=True)
class StructuredEnergy:
    boundary: Tensor
    segments: Tensor
    legal_boundaries: Tensor
    decomposition: FeatureDecomposition

    @property
    def statement_count(self) -> int:
        return self.segments.shape[0] - 1


class ContinuousModuleQuality(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.weights = nn.Parameter(torch.tensor([0.27, 0.22, 0.18, 0.14, 0.12, 0.07]))
        self.raw_size_scale = nn.Parameter(torch.tensor(_inverse_softplus(3.0)))
        self.raw_orphan_temperature = nn.Parameter(torch.tensor(_inverse_softplus(0.5)))

    def forward(self, region: ExecutableRegion) -> Tensor:
        count = len(region.statements)
        matrix = self.weights.new_full((count + 1, count + 1), float("-inf"))
        size_scale = F.softplus(self.raw_size_scale) + 1e-6
        orphan_temperature = F.softplus(self.raw_orphan_temperature) + 1e-6
        for start in range(count):
            for end in range(start + 1, count + 1):
                legacy = evaluate_module(region, start, end - 1)
                raw = legacy.raw_features
                length = self.weights.new_tensor(raw["statement_count"])
                terminal_strength = self.weights.new_tensor(
                    float(length.item() == 1 and legacy.features["orphan_resistance"] == 0)
                )
                features = self.weights.new_tensor(
                    [legacy.features[name] for name in MODULE_FEATURE_NAMES]
                )
                features[3] = (1.0 - torch.exp(-length / size_scale)) * torch.exp(
                    -torch.relu(length - 40.0) / 100.0
                )
                features[5] = torch.sigmoid((length - 1.5) / orphan_temperature) * (
                    1.0 - terminal_strength
                )
                matrix[start, end] = torch.dot(self.weights, features)
        return matrix


class StructuredScorer(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.feature_model = ContinuousFeatureModel()
        self.module_model = ContinuousModuleQuality()
        self.raw_cut_penalty = nn.Parameter(torch.tensor(_inverse_softplus(0.5)))

    @property
    def cut_penalty(self) -> Tensor:
        return F.softplus(self.raw_cut_penalty)

    def forward(
        self, region: ExecutableRegion, facts: list[BoundaryRawFacts] | None = None
    ) -> StructuredEnergy:
        facts = facts or extract_raw_facts(region)
        decomposition = self.feature_model(facts)
        legal = torch.tensor(
            [not item.constraints and item.after_line != item.before_line for item in facts],
            dtype=torch.bool,
            device=decomposition.boundary_energy.device,
        )
        boundary = decomposition.boundary_energy - self.cut_penalty
        boundary = torch.where(legal, boundary, torch.full_like(boundary, float("-inf")))
        return StructuredEnergy(boundary, self.module_model(region), legal, decomposition)


def segmentation_energy(energy: StructuredEnergy, cuts: list[int]) -> Tensor:
    points = [0, *sorted(cuts), energy.statement_count]
    value = energy.segments.new_zeros(())
    for start, end in pairwise(points):
        value = value + energy.segments[start, end]
    for cut in cuts:
        value = value + energy.boundary[cut - 1]
    return value


def _inverse_softplus(value: float) -> float:
    return math.log(math.expm1(value))
