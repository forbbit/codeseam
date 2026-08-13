from codeseam.core.features import extract_boundaries
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.languages.matlab import MatlabFrontend


def _region(source: bytes):
    return MatlabFrontend().analyze_source(source, "facts.m").regions[0]


def test_raw_facts_reconstruct_all_legacy_report_fields():
    region = _region(b"x = rand(4, 1);\ny = mean(x);\nz = y + 1;\ndisp(z);\n")
    raw = extract_raw_facts(region)
    legacy = extract_boundaries(region)
    assert len(raw) == len(legacy)
    for facts, boundary in zip(raw, legacy, strict=True):
        assert boundary.dead_symbols == list(facts.dead_symbols)
        assert boundary.born_symbols == list(facts.born_symbols)
        assert boundary.cross_symbols == list(facts.cross_symbols)
        assert boundary.raw_features["cross_dependency_count"] == facts.cross_dependency_count
        assert facts.schema_version == "boundary-raw-facts-v2"


def test_dynamic_workspace_is_low_confidence_not_zero_evidence():
    facts = extract_raw_facts(_region(b"x = 1;\neval('y = x');\nz = y + 1;\n"))[1]
    assert facts.reliability.dynamic_workspace_risk == 1.0
    assert 0.0 < facts.reliability.dependency < 1.0
    assert "dynamic_evaluation" in facts.risks
