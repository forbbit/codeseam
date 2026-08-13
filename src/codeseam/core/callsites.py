from __future__ import annotations

from codeseam.core.ir import CallAbstraction, CallForm, CallSite, StatementIR

DIRECT_FORMS = {
    CallForm.DIRECT_ASSIGNMENT,
    CallForm.DIRECT_MULTI_OUTPUT,
    CallForm.EFFECT_ONLY,
    CallForm.COMMAND,
}


def standalone_calls(statement: StatementIR) -> list[CallSite]:
    return [
        call
        for call in statement.call_sites
        if call.is_standalone_statement and call.form in DIRECT_FORMS
    ]


def existing_call_module_support(statement: StatementIR) -> float:
    """Structural support for reusing one already encapsulated call as a module."""
    calls = standalone_calls(statement)
    if len(calls) != 1 or not calls[0].is_only_operation:
        return 0.0
    call = calls[0]
    if call.abstraction is CallAbstraction.PRIMITIVE:
        return 0.0
    has_contract = bool(call.input_symbols or call.output_symbols) or call.form in {
        CallForm.EFFECT_ONLY,
        CallForm.COMMAND,
    }
    return call.resolution_reliability if has_contract else 0.0


def callsite_reliability(statements: list[StatementIR]) -> float:
    calls = [call for statement in statements for call in statement.call_sites]
    return min((call.resolution_reliability for call in calls), default=1.0)
