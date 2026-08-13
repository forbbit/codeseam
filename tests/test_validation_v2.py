from dataclasses import replace

import pytest

from codeseam.core.completion import completion_frontiers
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.corpus.counterfactual import (
    COUNTERFACTUAL_FAMILIES,
    generate_counterfactual_suite,
    generate_pairwise_suite,
)
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
            (item.target_boundary_truth.label, item.semantic_polarity)
            for item in suite
            if item.family == family
        } == {("cut", "low"), ("cut", "high"), ("no_cut", "low"), ("no_cut", "high")}


def test_candidate_labels_come_from_true_cuts_and_no_cut_is_semantic():
    cases = generate_counterfactual_suite(_graph())
    chosen = [
        item for item in cases if item.family == "interface" and item.semantic_polarity == "low"
    ]
    cut = next(item for item in chosen if item.target_boundary_truth.label == "cut")
    no_cut = next(item for item in chosen if item.target_boundary_truth.label == "no_cut")
    cut_render, no_cut_render = render_matlab(cut.graph), render_matlab(no_cut.graph)
    cut_index = dict(cut_render.boundary_cuts)[cut.target_boundary_id]
    no_cut_index = dict(no_cut_render.boundary_cuts)[no_cut.target_boundary_id]
    assert dict(cut_render.candidate_labels)[cut_index] == "cut"
    assert dict(no_cut_render.candidate_labels)[no_cut_index] == "no_cut"
    assert cut_index in cut_render.true_cuts and no_cut_index not in no_cut_render.true_cuts
    assert cut.graph.tasks[0].module_id != cut.graph.tasks[1].module_id
    assert no_cut.graph.tasks[0].module_id == no_cut.graph.tasks[1].module_id


def test_renderer_reads_all_semantic_inputs_and_maps_boundary():
    case = next(
        item
        for item in generate_counterfactual_suite(_graph())
        if item.family == "interface"
        and item.semantic_polarity == "high"
        and item.target_boundary_truth.label == "cut"
    )
    rendered = render_matlab(case.graph)
    for semantic_input in ("primary", "interface_a", "interface_b"):
        assert dict(rendered.symbol_map)[semantic_input] in rendered.source
    assert dict(rendered.boundary_cuts)[case.target_boundary_id] in rendered.true_cuts


def test_core_factor_and_pairwise_raw_observability():
    frontend, cases = MatlabFrontend(), generate_counterfactual_suite(_graph())

    def target(family, polarity):
        case = next(
            item
            for item in cases
            if item.family == family
            and item.semantic_polarity == polarity
            and item.target_boundary_truth.label == "cut"
        )
        rendered = render_matlab(case.graph)
        region = frontend.analyze_source(rendered.source.encode(), "factor.m").regions[0]
        return extract_raw_facts(region)[dict(rendered.boundary_cuts)[case.target_boundary_id] - 1]

    dep_low, dep_high = target("dependency", "low"), target("dependency", "high")
    assert dep_high.cross_dependency_count > dep_low.cross_dependency_count
    assert dep_high.dependency_reuse_mass > dep_low.dependency_reuse_mass
    assert (
        target("interface", "high").input_interface_count
        > target("interface", "low").input_interface_count
    )
    assert target("role", "low").right_role_histogram != target("role", "high").right_role_histogram
    assert len(target("completion", "high").right_role_histogram) > len(
        target("completion", "low").right_role_histogram
    )
    pair = next(
        item
        for item in generate_pairwise_suite()
        if dict(item.requested_factors) == {"dependency": "high", "interface": "high"}
    )
    rendered = render_matlab(pair.graph)
    facts = extract_raw_facts(
        frontend.analyze_source(rendered.source.encode(), "pair.m").regions[0]
    )
    fact = facts[dict(rendered.boundary_cuts)[pair.target_boundary_id] - 1]
    assert fact.input_interface_count >= 3 and fact.cross_dependency_count >= 3


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
