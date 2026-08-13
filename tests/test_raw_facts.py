from codeseam.core.features import extract_boundaries
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.languages.matlab import MatlabFrontend


def _region(source: bytes):
    return MatlabFrontend().analyze_source(source, "facts.m").regions[0]


def test_raw_facts_reconstruct_all_legacy_report_fields():
    region = _region(b"x = rand(4, 1);\ny = mean(x);\nz = y + 1;\ndisp(z);\n")
    raw = extract_raw_facts(region)
    boundaries = extract_boundaries(region)
    assert len(raw) == len(boundaries)
    for facts, boundary in zip(raw, boundaries, strict=True):
        assert boundary.dead_symbols == list(facts.dead_symbols)
        assert boundary.born_symbols == list(facts.born_symbols)
        assert boundary.cross_symbols == list(facts.cross_symbols)
        assert boundary.raw_features["cross_dependency_count"] == facts.cross_dependency_count
        assert facts.schema_version == "boundary-raw-facts-callsite"


def test_dynamic_workspace_is_low_confidence_not_zero_evidence():
    facts = extract_raw_facts(_region(b"x = 1;\neval('y = x');\nz = y + 1;\n"))[1]
    assert facts.reliability.dynamic_workspace_risk == 1.0
    assert 0.0 < facts.reliability.dependency < 1.0
    assert "dynamic_evaluation" in facts.risks


def test_code_semantic_facts_do_not_need_comments():
    source = (
        b"obj.source.power = 1;\n"
        b"obj.source.rate = 2;\n"
        b"obj.detector.gain = 3;\n"
        b"obj.detector.offset = 4;\n"
    )
    facts = extract_raw_facts(_region(source))[1]
    assert facts.left_access_domains == ("obj.source",)
    assert facts.right_access_domains == ("obj.detector",)


def test_terminal_control_is_extracted_from_control_flow_syntax():
    facts = extract_raw_facts(_region(b"x = 1;\nreturn\ny = 2;\n"))[1]
    assert facts.terminal_control_left is True


def test_call_kind_distinguishes_resolved_index_and_external_call():
    facts = extract_raw_facts(
        _region(b"x = zeros(3,1);\ny = x(1);\nz = custom_solver(y);\nout = z + 1;\n")
    )[1]
    assert ("index_access", 1) in facts.left_call_kind_histogram
    assert ("external_or_unresolved_call", 1) in facts.right_call_kind_histogram
    assert facts.right_calls == ("custom_solver",)


def test_callsite_facts_separate_pipeline_setup_finalization_and_primitives():
    pipeline = extract_raw_facts(
        _region(b"raw = load_data(path);\nclean = preprocess(raw);\n")
    )[0]
    assert pipeline.standalone_call_transition > 0
    assert pipeline.artifact_handoff == 1.0

    setup = extract_raw_facts(
        _region(b"opts = defaults;\nresult = solve(data, opts);\n")
    )[0]
    assert setup.unfinished_call_setup > 0

    finalization = extract_raw_facts(
        _region(b"result = analyze(data);\ndisp(result);\n")
    )[0]
    assert finalization.unfinished_call_finalization == 1.0

    primitives = extract_raw_facts(
        _region(b"flat = reshape(data, [], 1);\nvalue = mean(flat);\n")
    )[0]
    assert primitives.primitive_call_chain == 1.0
