from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from codeseam.core.raw_facts import BoundaryRawFacts

FEATURE_MODEL_VERSION = "boundary-features-v2-structured"
FEATURE_NAMES = (
    "variable_death",
    "variable_birth",
    "vocabulary_shift",
    "interface_compactness",
    "dependency_drop",
    "dependency_mass",
    "long_range_coupling",
    "role_transition",
    "call_set_change",
    "effect_set_change",
    "completion",
    "structural_support",
)


@dataclass(frozen=True, slots=True)
class FeatureDecomposition:
    names: tuple[str, ...]
    values: Tensor
    reliability: Tensor
    contributions: Tensor
    boundary_energy: Tensor

    def to_dict(self) -> dict[str, object]:
        return {
            "features": dict(zip(self.names, self.values.detach().tolist(), strict=True)),
            "reliability": dict(zip(self.names, self.reliability.detach().tolist(), strict=True)),
            "weighted_contributions": dict(
                zip(self.names, self.contributions.detach().tolist(), strict=True)
            ),
            "boundary_energy": float(self.boundary_energy.detach()),
        }


class ContinuousFeatureModel(nn.Module):
    """Fixed interpretable transforms with trainable scalar parameters."""

    def __init__(self) -> None:
        super().__init__()
        self.raw_alpha = nn.Parameter(torch.full((5,), _inverse_softplus(1.0)))
        self.raw_dependency_tau = nn.Parameter(torch.tensor(_inverse_softplus(4.0)))
        self.raw_completion_bias = nn.Parameter(torch.tensor(1.0))
        self.weights = nn.Parameter(torch.full((len(FEATURE_NAMES),), 0.1))
        self.bias = nn.Parameter(torch.tensor(0.0))
        self.unreliable_baseline = nn.Parameter(torch.zeros(len(FEATURE_NAMES)))

    def forward(self, facts: list[BoundaryRawFacts]) -> FeatureDecomposition:
        if not facts:
            empty = self.weights.new_empty((0, len(FEATURE_NAMES)))
            return FeatureDecomposition(FEATURE_NAMES, empty, empty, empty, empty[:, 0])
        rows = torch.stack([self._features(item) for item in facts])
        reliability = torch.stack([self._reliability(item) for item in facts])
        baseline = torch.sigmoid(self.unreliable_baseline)
        effective = reliability * rows + (1.0 - reliability) * baseline
        contributions = effective * self.weights
        energy = self.bias + contributions.sum(dim=-1)
        return FeatureDecomposition(FEATURE_NAMES, rows, reliability, contributions, energy)

    def _features(self, facts: BoundaryRawFacts) -> Tensor:
        dtype = self.weights.dtype
        device = self.weights.device
        value = lambda x: torch.tensor(float(x), dtype=dtype, device=device)
        alpha = F.softplus(self.raw_alpha) + 1e-6
        dead_ratio = value(facts.dead_symbol_count / max(1, facts.left_symbol_count))
        born_ratio = value(facts.born_symbol_count / max(1, facts.right_symbol_count))
        # Cross symbols are computed globally while the side counts are window-local.
        # Clamp the overlap to the local sets so the Jaccard-like distance cannot
        # become negative when a long-range symbol is outside one local window.
        local_overlap = min(
            facts.cross_symbol_count, facts.left_symbol_count, facts.right_symbol_count
        )
        overlap = value(local_overlap)
        union = value(max(1, facts.left_symbol_count + facts.right_symbol_count - local_overlap))
        interface = value(facts.input_interface_count + facts.output_interface_count)
        cross = value(facts.cross_dependency_count)
        nearby = value(facts.nearby_dependency_count)
        mass = value(facts.dependency_reuse_mass)
        span = value(facts.dependency_span_mean)
        role = value(
            _histogram_cosine_distance(facts.left_role_histogram, facts.right_role_histogram)
        )
        calls = value(_set_distance(facts.left_calls, facts.right_calls))
        effects = value(
            _histogram_set_distance(facts.left_effect_histogram, facts.right_effect_histogram)
        )
        unfinished = value(facts.unfinished_work_mass)
        tau = F.softplus(self.raw_dependency_tau) + 1e-6
        completion = torch.sigmoid(self.raw_completion_bias - alpha[4] * unfinished / tau)
        return torch.stack(
            (
                1.0 - torch.exp(-alpha[0] * dead_ratio),
                1.0 - torch.exp(-alpha[1] * born_ratio),
                1.0 - overlap / union,
                torch.exp(-alpha[2] * interface),
                1.0 - torch.clamp(cross / torch.clamp(nearby, min=1.0), 0.0, 1.0),
                # These are cut-support features: stronger coupling must not
                # increase them.  The former formulas had the opposite direction.
                torch.exp(-alpha[3] * mass),
                torch.exp(-span / tau),
                role,
                calls,
                effects,
                completion,
                value(facts.compound_ends_here) * completion,
            )
        )

    def _reliability(self, facts: BoundaryRawFacts) -> Tensor:
        r = facts.reliability
        values = (
            r.parse,
            r.parse,
            r.parse,
            r.dependency,
            r.dependency,
            r.dependency,
            r.dependency,
            r.role,
            r.call_resolution,
            r.effect,
            r.dependency,
            r.parse,
        )
        return self.weights.new_tensor(values)


def _inverse_softplus(value: float) -> float:
    return math.log(math.expm1(value))


def _set_distance(left, right) -> float:
    left, right = set(left), set(right)
    union = left | right
    return 0.0 if not union else 1.0 - len(left & right) / len(union)


def _histogram_set_distance(left, right) -> float:
    return _set_distance((name for name, _ in left), (name for name, _ in right))


def _histogram_cosine_distance(left, right) -> float:
    left, right = dict(left), dict(right)
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    dot = sum(left.get(key, 0) * right.get(key, 0) for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return 1.0 - dot / (left_norm * right_norm + 1e-8)
