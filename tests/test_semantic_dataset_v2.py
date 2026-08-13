from codeseam.core.raw_facts import extract_raw_facts
from codeseam.corpus.coverage import (
    FingerprintSample,
    contradictory_collisions,
    coverage_sample,
)
from codeseam.corpus.fingerprint import numeric_fingerprint
from codeseam.corpus.matlab_renderer import counterfactual_pair, render_matlab
from codeseam.corpus.semantic_graph import SemanticTask, SemanticTaskGraph
from codeseam.languages.matlab import MatlabFrontend


def _graph():
    return SemanticTaskGraph(
        "pipeline",
        (
            SemanticTask("load", "acquisition", outputs=("raw",), internal_steps=2),
            SemanticTask(
                "transform", "transformation", inputs=("raw",), outputs=("clean",),
                internal_steps=2, completion_tail=1,
            ),
            SemanticTask("report", "output", inputs=("clean",), internal_steps=1),
        ),
        factors={"interface": "small", "role_transition": "strong"},
    )


def test_ground_truth_exists_before_rendering_and_survives_styles():
    graph = _graph()
    assert graph.true_task_boundaries == (2, 5)
    left, right = counterfactual_pair(graph, seed=7)
    assert left.true_cuts == right.true_cuts == graph.true_task_boundaries
    assert left.source != right.source


def test_rendered_matlab_parses_and_exports_fingerprint():
    rendered = render_matlab(_graph(), seed=3)
    region = MatlabFrontend().analyze_source(rendered.source.encode(), "rendered.m").regions[0]
    facts = extract_raw_facts(region)
    assert len(facts) == len(region.statements) - 1
    assert len(numeric_fingerprint(facts[0])) >= 15


def test_coverage_sampler_and_collision_report():
    items = [
        FingerprintSample("a", (0.0, 0.0), "cut"),
        FingerprintSample("b", (0.0, 0.0), "no-cut"),
        FingerprintSample("c", (10.0, 10.0), "cut"),
    ]
    collisions = contradictory_collisions(items)
    assert collisions == [("a", "b", 0.0)]
    selected = coverage_sample(items, 2)
    assert {item.sample_id for item in selected} == {"a", "c"}
