import math

import pytest
import torch

from codeseam.core.feature_model import ContinuousFeatureModel
from codeseam.core.hard_dp import best_segmentation
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.core.soft_dp import log_partition
from codeseam.core.structured_analyzer import analyze_program_structured
from codeseam.core.structured_energy import StructuredEnergy, StructuredScorer
from codeseam.languages.matlab import MatlabFrontend
from codeseam.training.config import TrainingConfig, load_artifact, save_artifact
from codeseam.training.structured_loss import structured_nll
from codeseam.training.trainer import StructuredExample, train_structured


def _region(source=b"a = rand(4,1);\nb = mean(a);\nc = fft(b);\ndisp(c);\n"):
    return MatlabFrontend().analyze_source(source, "v2.m").regions[0]


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


def test_unified_trainer_updates_all_parameter_families():
    scorer = StructuredScorer()
    before = {name: value.detach().clone() for name, value in scorer.named_parameters()}
    scorer, report = train_structured(
        [StructuredExample(_region(), (2,), "tiny")],
        scorer=scorer,
        config=TrainingConfig(learning_rate=0.01, epochs=2),
    )
    changed = {name for name, value in scorer.named_parameters() if not torch.equal(value, before[name])}
    assert "feature_model.weights" in changed
    assert "module_model.weights" in changed
    assert "raw_cut_penalty" in changed
    assert report["train_structured_nll"] >= 0


def test_artifact_roundtrip_and_structured_inference(tmp_path):
    scorer = StructuredScorer()
    artifact = tmp_path / "model.json"
    save_artifact(artifact, scorer, TrainingConfig(epochs=1), {"ok": True})
    restored = StructuredScorer()
    payload = load_artifact(artifact, restored)
    assert payload["schema_version"] == "codeseam-structured-model-v2"
    program = MatlabFrontend().analyze_source(
        b"a = rand(2,1);\nb = mean(a);\nc = fft(b);\n", "roundtrip.m"
    )
    analysis = analyze_program_structured(program, restored)
    assert analysis.result.boundaries
    assert all(
        item.normalization_version == "boundary-features-v2-structured"
        for item in analysis.result.boundaries
    )


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
