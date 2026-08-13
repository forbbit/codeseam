from dataclasses import replace

import pytest

from codeseam.core.completion import completion_frontiers
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.corpus.counterfactual import COUNTERFACTUAL_FAMILIES, generate_counterfactual_suite
from codeseam.corpus.coverage import CoverageDesign, FingerprintSample, audit_coverage
from codeseam.corpus.fingerprint import (
    fit_fingerprint_schema,
    mixed_distance,
    normalize_fingerprint,
)
from codeseam.corpus.matlab_renderer import counterfactual_pair, render_matlab
from codeseam.corpus.semantic_graph import SemanticTask, SemanticTaskGraph
from codeseam.evaluation.diagnostics import DiagnosticRow, feature_diagnostics
from codeseam.evaluation.readiness import GateStatus, evaluate_training_readiness
from codeseam.languages.matlab import MatlabFrontend


def _graph():
    return SemanticTaskGraph(
        "g",
        (
            SemanticTask("a", "acquisition", outputs=("x",)),
            SemanticTask("b", "aggregation", inputs=("x",), outputs=("y",)),
        ),
    )


def _facts():
    rendered = render_matlab(_graph(), seed=1)
    region = MatlabFrontend().analyze_source(rendered.source.encode(), "x.m").regions[0]
    return extract_raw_facts(region)


def test_renderer_reused_style_is_injective_and_has_stable_trace():
    left, right = counterfactual_pair(_graph(), seed=4)
    assert len(dict(right.symbol_map).values()) == len(set(dict(right.symbol_map).values()))
    assert left.semantic_program_id == right.semantic_program_id
    assert left.boundary_cuts and right.boundary_cuts


def test_eight_counterfactual_families_have_four_quadrants():
    suite = generate_counterfactual_suite(_graph())
    assert {item.family for item in suite} == set(COUNTERFACTUAL_FAMILIES)
    for family in COUNTERFACTUAL_FAMILIES:
        assert {
            (item.label, item.semantic_polarity) for item in suite if item.family == family
        } == {("cut", "low"), ("cut", "high"), ("no_cut", "low"), ("no_cut", "high")}


def test_fingerprint_fit_is_train_only_and_schema_mismatch_is_rejected():
    facts = _facts()
    schema = fit_fingerprint_schema(facts)
    with pytest.raises(ValueError):
        fit_fingerprint_schema(facts, split="validation")
    value = normalize_fingerprint(facts[0], schema)
    assert value.schema_id == schema.schema_id and len(value.values) == len(value.observed_mask)
    other = replace(value, schema_id="different")
    with pytest.raises(ValueError):
        mixed_distance(value, other)


def test_coverage_enumerates_unobserved_design_cells_and_leakage():
    items = [
        FingerprintSample(
            "a", label="cut", factors={"x": "low"}, semantic_program_id="p", split="train"
        ),
        FingerprintSample(
            "b", label="no_cut", factors={"x": "high"}, semantic_program_id="p", split="test"
        ),
    ]
    report = audit_coverage(items, CoverageDesign({"x": ("low", "high")}))
    assert report["factor_label"]["x"]["empty_cells"]
    assert report["leakage"]["count"] == 1


def test_diagnostics_reject_missing_features_and_gate_never_defaults_pass():
    with pytest.raises(ValueError):
        feature_diagnostics(
            [DiagnosticRow({"a": 1.0}, {}, {}, "cut"), DiagnosticRow({"b": 1.0}, {}, {}, "cut")]
        )
    report = evaluate_training_readiness({"A": {"pass": True}})
    assert report.overall.endswith("NO")
    assert report.gates[1].status is GateStatus.NOT_EVALUATED
    explicit = evaluate_training_readiness({"A": {"status": "NOT_EVALUATED"}})
    assert explicit.gates[0].status is GateStatus.NOT_EVALUATED


def test_completion_frontier_preserves_full_unfinished_suffix():
    source = b"""x = randn(8,1);
for i = 1:8
    state(i) = x(i);
end
energy = sum(state);
normalized = energy / length(state);
"""
    region = MatlabFrontend().analyze_source(source, "completion.m").regions[0]
    evidence = completion_frontiers(region)
    compound = next(i for i, statement in enumerate(region.statements) if statement.is_compound)
    assert evidence[compound].through_statement - compound >= 2
