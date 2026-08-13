from pathlib import Path

from codeseam.core.ir import CallAbstraction, CallForm, Effect, OperationRole, Risk
from codeseam.languages.matlab import MatlabFrontend

FIXTURES = Path(__file__).parent / "fixtures" / "matlab"


def test_mixed_script_and_local_function_are_separate_regions() -> None:
    path = FIXTURES / "mixed_pipeline.m"
    program = MatlabFrontend().analyze_source(path.read_bytes(), str(path))
    assert [region.id for region in program.regions] == [
        "script:top-level",
        "function:finalizeBlocks",
    ]
    assert program.regions[1].parameters == {"input", "blockSize"}
    assert program.regions[1].declared_outputs == {"output"}
    assert all(
        statement.kind != "comment" for region in program.regions for statement in region.statements
    )


def test_assignment_and_ambiguous_call_or_index_facts() -> None:
    source = b"x = raw(:, 1);\ny(2) = x(1) + mean(x);\n"
    program = MatlabFrontend().analyze_source(source, "memory.m")
    first, second = program.regions[0].statements
    assert first.definitions == {"x"}
    assert "raw" in first.calls
    assert Risk.AMBIGUOUS_CALL_OR_INDEX in first.risks
    assert second.mutations == {"y"}
    assert {"x", "y"} <= second.reads
    assert "mean" in second.calls
    assert "mean" in second.resolved_calls
    assert "x" in second.resolved_indexes
    assert "raw" in first.unresolved_calls


def test_builtin_call_and_defined_variable_index_are_classified_separately() -> None:
    source = b"signal = randn(1, 10);\nvalue = signal(2) + mean(signal);\n"
    statements = MatlabFrontend().analyze_source(source, "memory.m").regions[0].statements
    assert statements[0].resolved_calls == {"randn"}
    assert "signal" in statements[1].resolved_indexes
    assert "mean" in statements[1].resolved_calls
    assert not statements[1].unresolved_calls


def test_operation_roles_are_extracted_without_comments() -> None:
    source = b"energy = sum(abs(signal).^2);\nnormalized = signal / sqrt(energy);\n"
    first, second = MatlabFrontend().analyze_source(source, "memory.m").regions[0].statements
    assert OperationRole.AGGREGATION in first.roles
    assert OperationRole.NORMALIZATION in second.roles


def test_self_overwrite_retains_rhs_read_for_def_use() -> None:
    source = b"signal = randn(1, 10);\nsignal = signal / max(abs(signal));\n"
    second = MatlabFrontend().analyze_source(source, "memory.m").regions[0].statements[1]
    assert "signal" in second.definitions
    assert "signal" in second.reads


def test_workspace_command_is_explicit_risk() -> None:
    source = b"load input.mat\nx = value + 1;\nsave output.mat x\n"
    program = MatlabFrontend().analyze_source(source, "memory.m")
    load, _, save = program.regions[0].statements
    assert {Effect.FILE_READ, Effect.WORKSPACE_WRITE} <= load.effects
    assert Risk.WORKSPACE_INJECTION in load.risks
    assert Effect.FILE_WRITE in save.effects
    assert "x" in save.reads


def test_dynamic_workspace_call_and_path_mutation_are_risks() -> None:
    source = b"assignin('base', 'x', value);\naddpath(folder);\n"
    program = MatlabFrontend().analyze_source(source, "memory.m")
    assignin, addpath = program.regions[0].statements
    assert {Effect.WORKSPACE_READ, Effect.WORKSPACE_WRITE} <= assignin.effects
    assert {Risk.DYNAMIC_EVALUATION, Risk.WORKSPACE_INJECTION} <= assignin.risks
    assert Effect.PATH_MUTATION in addpath.effects
    assert Risk.PATH_DEPENDENCY in addpath.risks


def test_struct_field_name_is_not_treated_as_a_variable() -> None:
    source = b"record.value = input;\nrecord.(fieldName) = secondInput;\n"
    program = MatlabFrontend().analyze_source(source, "memory.m")
    direct, indirect = program.regions[0].statements
    assert direct.mutations == {"record"}
    assert "value" not in direct.reads
    assert indirect.mutations == {"record"}
    assert "fieldName" in indirect.reads


def test_external_script_forbids_cuts_on_both_sides() -> None:
    source = b"x = 1;\nrun mutate_workspace.m\ny = x + injected;\n"
    program = MatlabFrontend().analyze_source(source, "memory.m")
    run = program.regions[0].statements[1]
    assert run.forbid_cut_before == {"external_script_shared_workspace"}
    assert run.forbid_cut_after == {"external_script_shared_workspace"}


def test_global_persistent_and_function_handles_are_explicit_risks() -> None:
    source = b"""function output = calculate(input)
global shared
persistent cache
transform = @fft;
anonymous = @(value) value.^2;
output = feval(transform, input) + shared;
end
"""
    program = MatlabFrontend().analyze_source(source, "memory.m")
    statements = program.regions[0].statements
    assert Risk.GLOBAL_STATE in statements[0].risks
    assert Risk.PERSISTENT_STATE in statements[1].risks
    assert {Effect.FUNCTION_HANDLE} <= statements[2].effects
    assert Risk.INDIRECT_CALL in statements[2].risks
    assert Risk.INDIRECT_CALL in statements[3].risks
    assert {Risk.DYNAMIC_EVALUATION, Risk.INDIRECT_CALL} <= statements[4].risks


def test_deeply_nested_cell_index_fixture_is_stable() -> None:
    path = Path(__file__).parent / "fixtures" / "matlab" / "nested_cell_index.m"
    program = MatlabFrontend().analyze_source(path.read_bytes(), str(path))
    assert program.regions
    assert any(statement.mutations for region in program.regions for statement in region.statements)


def test_call_sites_preserve_direct_nested_and_effect_only_structure() -> None:
    source = (
        b"raw = load_data(path);\n"
        b"score = mean(normalize(raw));\n"
        b"save_results(score, output_path);\n"
    )
    statements = MatlabFrontend().analyze_source(source, "memory.m").regions[0].statements
    load_call = statements[0].call_sites[0]
    assert load_call.form is CallForm.DIRECT_ASSIGNMENT
    assert load_call.is_standalone_statement and load_call.is_only_operation
    assert load_call.input_symbols == {"path"}
    assert load_call.output_symbols == {"raw"}
    assert [call.form for call in statements[1].call_sites] == [
        CallForm.DIRECT_ASSIGNMENT,
        CallForm.NESTED_EXPRESSION,
    ]
    assert not any(call.is_only_operation for call in statements[1].call_sites)
    assert statements[2].call_sites[0].form is CallForm.EFFECT_ONLY


def test_matlab_primitive_classification_is_frontend_evidence() -> None:
    statement = MatlabFrontend().analyze_source(
        b"flat = reshape(data, [], 1);\n", "memory.m"
    ).regions[0].statements[0]
    assert statement.call_sites[0].abstraction is CallAbstraction.PRIMITIVE


def test_index_access_is_not_a_high_level_call_candidate() -> None:
    statements = MatlabFrontend().analyze_source(
        b"x = zeros(3, 1);\ny = x(1);\n", "memory.m"
    ).regions[0].statements
    assert statements[1].call_sites[0].origin.value == "index_access"
    assert statements[1].call_sites[0].abstraction is CallAbstraction.PRIMITIVE


def test_object_method_call_includes_receiver_in_structural_inputs() -> None:
    statement = MatlabFrontend().analyze_source(
        b"result = engine.process(data);\n", "memory.m"
    ).regions[0].statements[0]
    call = statement.call_sites[0]
    assert call.form is CallForm.DIRECT_ASSIGNMENT
    assert call.input_symbols == {"engine", "data"}
