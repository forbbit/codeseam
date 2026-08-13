import math

import pytest
import torch

from codeseam.core.feature_model import FEATURE_NAMES, ContinuousFeatureModel
from codeseam.core.hard_dp import best_segmentation
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.core.soft_dp import log_partition
from codeseam.core.structured_energy import StructuredEnergy, StructuredScorer
from codeseam.languages.matlab import MatlabFrontend
from codeseam.training.structured_loss import balanced_boundary_loss, structured_nll


def _region(source=b"a = rand(4,1);\nb = mean(a);\nc = fft(b);\ndisp(c);\n"):
    return MatlabFrontend().analyze_source(source, "structured.m").regions[0]


def _manual_energy(boundaries, segments):
    boundary = torch.tensor(boundaries, dtype=torch.float64, requires_grad=True)
    matrix = torch.full((len(boundaries) + 2, len(boundaries) + 2), float("-inf"), dtype=torch.float64)
    for (start, end), value in segments.items():
        matrix[start, end] = value
    decomposition = type("D", (), {"boundary_energy": boundary})()
    return StructuredEnergy(boundary, matrix, torch.ones(len(boundaries), dtype=torch.bool), decomposition)


def test_continuous_features_have_finite_nonzero_gradients():
    model = ContinuousFeatureModel()
    output = model(extract_raw_facts(_region()))
    assert torch.isfinite(output.values).all()
    assert ((0 <= output.values) & (output.values <= 1)).all()
    output.boundary_energy.sum().backward()
    assert model.raw_alpha.grad is not None
    assert torch.isfinite(model.raw_alpha.grad).all()
    assert model.raw_alpha.grad.abs().sum() > 0
    assert (model.raw_alpha.grad.abs() > 0).all()


def test_code_semantic_features_respond_without_comment_evidence():
    region = _region(
        b"obj.source.power = 1;\nobj.source.rate = 2;\n"
        b"obj.detector.gain = 3;\nobj.detector.offset = 4;\n"
    )
    output = ContinuousFeatureModel()(extract_raw_facts(region))
    shift = FEATURE_NAMES.index("access_domain_shift")
    assert float(output.values[1, shift].detach()) == pytest.approx(1.0)


def test_interaction_residual_starts_neutral_and_can_learn():
    model = ContinuousFeatureModel()
    output = model(extract_raw_facts(_region()))
    assert torch.equal(output.interaction_energy, torch.zeros_like(output.interaction_energy))
    output.boundary_energy.sum().backward()
    assert model.interactions[-1].weight.grad is not None
    assert model.interactions[-1].weight.grad.abs().sum() > 0


def test_soft_dp_matches_explicit_tiny_partition_and_hard_dp():
    energy = _manual_energy(
        [0.7, -0.2],
        {(0, 3): 0.1, (0, 1): 0.2, (1, 3): 0.4, (0, 2): -0.1,
         (2, 3): 0.3, (1, 2): 0.0},
    )
    explicit = torch.logsumexp(torch.tensor([0.1, 1.3, 0.0, 1.0], dtype=torch.float64), 0)
    assert torch.allclose(log_partition(energy), explicit)
    cuts, score = best_segmentation(energy)
    assert cuts == [1]
    assert score == pytest.approx(1.3)


def test_structured_loss_gradient_matches_finite_difference():
    scorer = StructuredScorer()
    region = _region()
    parameter = scorer.feature_model.bias
    # Bias cancels when all paths have the same cut count only; this sample has varied counts.
    loss = structured_nll(scorer(region), [2])
    loss.backward()
    auto = float(parameter.grad)
    epsilon = 1e-4
    original = float(parameter.detach())
    with torch.no_grad():
        parameter.fill_(original + epsilon)
    high = float(structured_nll(scorer(region), [2]).detach())
    with torch.no_grad():
        parameter.fill_(original - epsilon)
    low = float(structured_nll(scorer(region), [2]).detach())
    with torch.no_grad():
        parameter.fill_(original)
    finite = (high - low) / (2 * epsilon)
    assert math.isfinite(auto)
    assert auto == pytest.approx(finite, abs=2e-3)


def test_balanced_boundary_loss_rewards_truth_without_class_imbalance():
    energy = _manual_energy([0.0, 0.0, 0.0], {(0, 4): 0.0})
    before = balanced_boundary_loss(energy, [2])
    improved = _manual_energy([-2.0, 2.0, -2.0], {(0, 4): 0.0})
    after = balanced_boundary_loss(improved, [2])
    assert after < before
    after.backward()
    assert improved.boundary.grad is not None


def test_cached_module_quality_preserves_values_and_gradients():
    region = _region()
    scorer = StructuredScorer()
    first = scorer(region)
    first_value = first.segments[0, len(region.statements)]
    first_value.backward()
    first_gradient = scorer.module_model.raw_weights.grad.detach().clone()
    scorer.zero_grad()
    second = scorer(region)
    second_value = second.segments[0, len(region.statements)]
    second_value.backward()
    assert torch.equal(first.segments, second.segments)
    assert torch.equal(first_gradient, scorer.module_model.raw_weights.grad)
    assert len(scorer.module_model._static_cache) == 1
    assert len(scorer._facts_cache) == 1


@pytest.mark.parametrize("boundaries", [1, 10, 100, 1000])
def test_soft_dp_is_numerically_stable_for_long_sequences(boundaries):
    boundary = torch.linspace(-1, 1, boundaries)
    n = boundaries + 1
    segments = torch.full((n + 1, n + 1), float("-inf"))
    for end in range(1, n + 1):
        segments[:end, end] = -0.001 * torch.arange(end - 1, -1, -1)
    energy = StructuredEnergy(
        boundary, segments, torch.ones(boundaries, dtype=torch.bool),
        type("D", (), {"boundary_energy": boundary})(),
    )
    assert torch.isfinite(log_partition(energy))
