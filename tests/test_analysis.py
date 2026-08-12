from pathlib import Path

from codeseam.service import analyze_file

FIXTURES = Path(__file__).parent / "fixtures" / "matlab"


def test_analysis_produces_bounded_explainable_scores() -> None:
    result = analyze_file(FIXTURES / "two_phases.m", threshold=0.0)
    assert result.boundaries
    assert all(0.0 <= boundary.score <= 1.0 for boundary in result.boundaries)
    assert all(boundary.features for boundary in result.boundaries)
    assert all(boundary.raw_features for boundary in result.boundaries)
    assert all(
        0.0 <= value <= 1.0
        for boundary in result.boundaries
        for value in boundary.features.values()
    )
    assert all(
        "cross_dependency_sparsity" not in boundary.features for boundary in result.boundaries
    )
    assert all(
        boundary.normalization_version == "boundary-features-v6" for boundary in result.boundaries
    )
    assert all(boundary.left_module_quality for boundary in result.boundaries)
    assert all(boundary.right_module_quality for boundary in result.boundaries)
    assert all(boundary.after_line < boundary.before_line for boundary in result.boundaries)


def test_function_definitions_are_not_script_statements() -> None:
    result = analyze_file(FIXTURES / "mixed_pipeline.m")
    script = next(region for region in result.program.regions if region.kind == "script")
    assert all(statement.kind != "function_definition" for statement in script.statements)


def test_same_line_statement_boundaries_are_candidates_but_never_recommended(tmp_path) -> None:
    source = tmp_path / "same_line.m"
    source.write_text("clear; clc; close all;\nx = 1;\ny = x + 1;\nz = y + 1;\nout = z + 1;\n")
    result = analyze_file(source, threshold=0.0, minimum_prominence=0.0)
    same_line = [item for item in result.boundaries if item.after_line == item.before_line]
    assert same_line
    assert all(not item.recommended for item in same_line)
    assert all("same_line_boundary" in item.rejection_reasons for item in same_line)


def test_recommendations_respect_prominence() -> None:
    result = analyze_file(FIXTURES / "two_phases.m")
    selected = [item for item in result.boundaries if item.recommended]
    assert all(item.prominence >= 0.055 for item in selected)


def test_large_cut_penalty_can_prefer_the_unsplit_program() -> None:
    result = analyze_file(FIXTURES / "two_phases.m", cut_penalty=10.0)
    assert not any(item.recommended for item in result.boundaries)


def test_module_deficit_penalty_does_not_increase_cut_count(tmp_path) -> None:
    source = tmp_path / "weak_short_module.m"
    source.write_text("a = 1;\nb = 2;\ndisp(a);\nc = randn(1, 10);\nd = fft(c);\ne = mean(d);\n")
    baseline = analyze_file(source, threshold=0.0, minimum_prominence=0.0)
    penalized = analyze_file(
        source,
        threshold=0.0,
        minimum_prominence=0.0,
        module_quality_floor=0.7,
        module_deficit_penalty=1.0,
    )
    assert sum(item.recommended for item in penalized.boundaries) <= sum(
        item.recommended for item in baseline.boundaries
    )
