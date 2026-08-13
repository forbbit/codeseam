from codeseam.core.module_quality import evaluate_module
from codeseam.languages.matlab import MatlabFrontend


def test_module_quality_exposes_raw_interface_and_locality_facts() -> None:
    source = b"""input = randn(1, 100);
offset = mean(input);
centered = input - offset;
scale = std(centered);
normalized = centered / scale;
result = fft(normalized);
"""
    region = MatlabFrontend().analyze_source(source, "memory.m").regions[0]
    quality = evaluate_module(region, 1, 4)
    assert 0.0 <= quality.score <= 1.0
    assert quality.raw_features["statement_count"] == 4
    assert quality.inputs
    assert quality.outputs == ["normalized"]
    assert set(quality.features) == {
        "internal_cohesion",
        "external_compactness",
        "symbol_locality",
        "size_fitness",
        "finalization_completeness",
        "orphan_resistance",
    }


def test_terminal_single_statement_has_orphan_penalty() -> None:
    source = b"value = 1;\ndisp(value);\n"
    region = MatlabFrontend().analyze_source(source, "memory.m").regions[0]
    quality = evaluate_module(region, 1, 1)
    assert quality.features["orphan_resistance"] == 0.0
    assert quality.features["size_fitness"] == 0.0


def test_size_fitness_does_not_penalize_normal_long_modules() -> None:
    source = "\n".join(f"value{i} = {i};" for i in range(20)).encode()
    region = MatlabFrontend().analyze_source(source, "memory.m").regions[0]
    quality = evaluate_module(region, 0, 19)
    assert quality.features["size_fitness"] == 1.0


def test_single_existing_high_level_call_escapes_length_penalty() -> None:
    region = MatlabFrontend().analyze_source(
        b"registered = register_volume(volume, atlas);\n", "memory.m"
    ).regions[0]
    quality = evaluate_module(region, 0, 0)
    assert quality.raw_features["existing_call_module_support"] > 0
    assert quality.features["size_fitness"] > 0
    assert quality.features["orphan_resistance"] > 0


def test_single_primitive_call_keeps_length_penalty() -> None:
    region = MatlabFrontend().analyze_source(
        b"flat = reshape(volume, [], 1);\n", "memory.m"
    ).regions[0]
    quality = evaluate_module(region, 0, 0)
    assert quality.raw_features["existing_call_module_support"] == 0
    assert quality.features["size_fitness"] == 0
    assert quality.features["orphan_resistance"] == 0
