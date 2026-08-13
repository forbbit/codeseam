from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from codeseam.core.dependencies import projected_dependence_edges, symbol_occurrences
from codeseam.core.feature_model import ContinuousFeatureModel, FeatureDecomposition
from codeseam.core.ir import ExecutableRegion
from codeseam.core.module_quality import evaluate_module
from codeseam.core.raw_facts import BoundaryRawFacts, extract_raw_facts

ENERGY_SCHEMA_VERSION = "structured-energy"
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
        initial = torch.tensor([0.27, 0.22, 0.18, 0.14, 0.12, 0.07])
        self.raw_weights = nn.Parameter(torch.log(torch.expm1(initial)))
        self.raw_size_scale = nn.Parameter(torch.tensor(_inverse_softplus(3.0)))
        self.raw_orphan_temperature = nn.Parameter(torch.tensor(_inverse_softplus(0.5)))
        self._static_cache: dict[int, tuple[Tensor, Tensor, Tensor, Tensor, Tensor]] = {}

    def forward(self, region: ExecutableRegion) -> Tensor:
        base, lengths, terminal_strength, existing_call_support, valid = self._static(region)
        weights = F.softplus(self.raw_weights)
        base = base.to(dtype=weights.dtype, device=weights.device)
        lengths = lengths.to(dtype=weights.dtype, device=weights.device)
        terminal_strength = terminal_strength.to(
            dtype=weights.dtype, device=weights.device
        )
        existing_call_support = existing_call_support.to(
            dtype=weights.dtype, device=weights.device
        )
        valid = valid.to(device=weights.device)
        size_scale = F.softplus(self.raw_size_scale) + 1e-6
        orphan_temperature = F.softplus(self.raw_orphan_temperature) + 1e-6
        learned_size = (1.0 - torch.exp(-lengths / size_scale)) * torch.exp(
            -torch.relu(lengths - 40.0) / 100.0
        )
        learned_size = torch.maximum(learned_size, existing_call_support)
        learned_orphan = torch.sigmoid((lengths - 1.5) / orphan_temperature) * (
            1.0 - terminal_strength
        )
        learned_orphan = torch.maximum(learned_orphan, existing_call_support)
        features = torch.stack(
            (
                base[..., 0],
                base[..., 1],
                base[..., 2],
                learned_size,
                base[..., 4],
                learned_orphan,
            ),
            dim=-1,
        )
        scores = torch.sum(features * weights, dim=-1)
        return torch.where(valid, scores, torch.full_like(scores, float("-inf")))

    def _static(self, region: ExecutableRegion) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor]:
        key = id(region)
        cached = self._static_cache.get(key)
        if cached is not None:
            return cached
        count = len(region.statements)
        base = torch.zeros((count + 1, count + 1, len(MODULE_FEATURE_NAMES)))
        lengths = torch.zeros((count + 1, count + 1))
        terminal_strength = torch.zeros((count + 1, count + 1))
        existing_call_support = torch.zeros((count + 1, count + 1))
        valid = torch.zeros((count + 1, count + 1), dtype=torch.bool)
        dependence_edges = projected_dependence_edges(region, include_internal=True)
        occurrences = symbol_occurrences(region)
        for start in range(count):
            for end in range(start + 1, count + 1):
                quality = evaluate_module(
                    region,
                    start,
                    end - 1,
                    dependence_edges=dependence_edges,
                    occurrences=occurrences,
                )
                raw = quality.raw_features
                lengths[start, end] = raw["statement_count"]
                terminal_strength[start, end] = float(
                    raw["statement_count"] == 1
                    and quality.features["orphan_resistance"] == 0
                )
                existing_call_support[start, end] = raw["existing_call_module_support"]
                base[start, end] = torch.tensor(
                    [quality.features[name] for name in MODULE_FEATURE_NAMES]
                )
                valid[start, end] = True
        cached = (base, lengths, terminal_strength, existing_call_support, valid)
        self._static_cache[key] = cached
        return cached


class StructuredScorer(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.feature_model = ContinuousFeatureModel()
        self.module_model = ContinuousModuleQuality()
        self.raw_cut_penalty = nn.Parameter(torch.tensor(_inverse_softplus(0.5)))
        self._facts_cache: dict[int, list[BoundaryRawFacts]] = {}

    @property
    def cut_penalty(self) -> Tensor:
        return F.softplus(self.raw_cut_penalty)

    def forward(
        self, region: ExecutableRegion, facts: list[BoundaryRawFacts] | None = None
    ) -> StructuredEnergy:
        if facts is None:
            facts = self._facts_cache.get(id(region))
            if facts is None:
                facts = extract_raw_facts(region)
                self._facts_cache[id(region)] = facts
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
