from script_boundary.core.analyzer import analyze_program
from script_boundary.languages.matlab import MatlabFrontend


def analyze(source: bytes):
    return analyze_program(MatlabFrontend().analyze_source(source, "memory.m"))


def test_dependent_aggregation_and_normalization_extend_completion_frontier() -> None:
    result = analyze(
        b"""values = randn(1, 100);
state = zeros(size(values));
for index = 2:length(values)
    state(index) = state(index - 1) + values(index);
end
energy = sum(abs(state).^2);
normalizedEnergy = energy / length(state);
spectrum = fft(state);
"""
    )
    after_loop = next(item for item in result.boundaries if item.after_line == 5)
    after_energy = next(item for item in result.boundaries if item.after_line == 6)
    before_spectrum = next(item for item in result.boundaries if item.after_line == 7)
    assert after_loop.features["task_completion"] == 0.0
    assert "aggregation" in after_loop.completion_roles
    assert after_energy.features["task_completion"] == 0.0
    assert "normalization" in after_energy.completion_roles
    assert before_spectrum.features["task_completion"] == 1.0


def test_independent_aggregation_does_not_extend_previous_task() -> None:
    result = analyze(
        b"""left = randn(1, 100);
prepared = detrend(left);
other = randn(1, 100);
summary = mean(other);
"""
    )
    boundary = next(item for item in result.boundaries if item.after_line == 2)
    assert boundary.features["task_completion"] == 1.0


def test_new_aggregation_stage_may_consume_previous_task_output() -> None:
    result = analyze(
        b"""data = randn(1, 128);
transformed = fft(data);
centered = transformed - mean(transformed);
energy = sum(abs(centered).^2);
"""
    )
    boundary = next(item for item in result.boundaries if item.after_line == 2)
    assert boundary.features["task_completion"] == 1.0
