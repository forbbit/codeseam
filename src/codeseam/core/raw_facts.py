from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from codeseam.core.callsites import (
    callsite_reliability,
    existing_call_module_support,
    standalone_calls,
)
from codeseam.core.completion import completion_frontiers
from codeseam.core.dependencies import semantic_def_use_edges, symbol_occurrences
from codeseam.core.ir import ControlEffect, DependencyEdge, ExecutableRegion, OperationRole, Risk

RAW_FACT_SCHEMA_VERSION = "boundary-raw-facts-callsite"


@dataclass(frozen=True, slots=True)
class Reliability:
    """Confidence in a fact family; low confidence is not negative evidence."""

    parse: float = 1.0
    call_resolution: float = 1.0
    dependency: float = 1.0
    role: float = 1.0
    effect: float = 1.0
    callsite: float = 1.0
    dynamic_workspace_risk: float = 0.0
    alias_uncertainty: float = 0.0
    dependency_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "parse",
            "call_resolution",
            "dependency",
            "role",
            "effect",
            "callsite",
            "dynamic_workspace_risk",
            "alias_uncertainty",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class BoundaryRawFacts:
    schema_version: str
    region_id: str
    boundary_index: int
    after_line: int
    before_line: int
    left_context_size: int
    right_context_size: int
    left_symbol_count: int
    right_symbol_count: int
    left_symbols: tuple[str, ...]
    right_symbols: tuple[str, ...]
    dead_symbols: tuple[str, ...]
    born_symbols: tuple[str, ...]
    cross_symbols: tuple[str, ...]
    input_symbols: tuple[str, ...]
    output_symbols: tuple[str, ...]
    cross_edges: tuple[DependencyEdge, ...]
    local_cross_dependency_count: int
    nearby_dependency_count: int
    left_internal_data_edge_count: int
    right_internal_data_edge_count: int
    dependency_span_mean: float
    dependency_span_max: int
    dependency_target_count: int
    dependency_reuse_mass: float
    left_calls: tuple[str, ...]
    right_calls: tuple[str, ...]
    left_access_domains: tuple[str, ...]
    right_access_domains: tuple[str, ...]
    left_call_kind_histogram: tuple[tuple[str, int], ...]
    right_call_kind_histogram: tuple[tuple[str, int], ...]
    standalone_call_transition: float
    artifact_handoff: float
    unfinished_call_setup: float
    unfinished_call_finalization: float
    primitive_call_chain: float
    terminal_control_left: bool
    left_effect_histogram: tuple[tuple[str, int], ...]
    right_effect_histogram: tuple[tuple[str, int], ...]
    left_role_histogram: tuple[tuple[str, int], ...]
    right_role_histogram: tuple[tuple[str, int], ...]
    compound_ends_here: bool
    control_followup_edge_count: int
    unfinished_work_mass: float
    completion_chain_length: int
    completion_roles: tuple[str, ...]
    completion_symbols: tuple[str, ...]
    constraints: tuple[str, ...]
    risks: tuple[str, ...]
    reliability: Reliability

    @property
    def dead_symbol_count(self) -> int:
        return len(self.dead_symbols)

    @property
    def born_symbol_count(self) -> int:
        return len(self.born_symbols)

    @property
    def cross_symbol_count(self) -> int:
        return len(self.cross_symbols)

    @property
    def input_interface_count(self) -> int:
        return len(self.input_symbols)

    @property
    def output_interface_count(self) -> int:
        return len(self.output_symbols)

    @property
    def cross_dependency_count(self) -> int:
        return len(self.cross_edges)

    @property
    def left_call_count(self) -> int:
        return len(self.left_calls)

    @property
    def right_call_count(self) -> int:
        return len(self.right_calls)

    @property
    def left_effect_count(self) -> int:
        return len(self.left_effect_histogram)

    @property
    def right_effect_count(self) -> int:
        return len(self.right_effect_histogram)

    def fingerprint(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("region_id")
        value.pop("after_line")
        value.pop("before_line")
        value.pop("dead_symbols")
        value.pop("born_symbols")
        value.pop("cross_symbols")
        value.pop("input_symbols")
        value.pop("output_symbols")
        value.pop("left_symbols")
        value.pop("right_symbols")
        value.pop("cross_edges")
        return value


def extract_raw_facts(
    region: ExecutableRegion, *, window: int = 4, medium_window: int = 12
) -> list[BoundaryRawFacts]:
    del medium_window  # retained for the public analysis API
    statements = region.statements
    if len(statements) < 2:
        return []
    occurrences = symbol_occurrences(region)
    edges = semantic_def_use_edges(region)
    completion = completion_frontiers(region)
    first = {symbol: indexes[0] for symbol, indexes in occurrences.items()}
    last = {symbol: indexes[-1] for symbol, indexes in occurrences.items()}
    facts: list[BoundaryRawFacts] = []
    for boundary in range(len(statements) - 1):
        left_start = max(0, boundary - window + 1)
        right_end = min(len(statements) - 1, boundary + window)
        left_slice = statements[left_start : boundary + 1]
        right_slice = statements[boundary + 1 : right_end + 1]
        left_statement = statements[boundary]
        right_statement = statements[boundary + 1]
        left_symbols = _symbols(left_slice)
        right_symbols = _symbols(right_slice)
        dead = {symbol for symbol in left_symbols if last[symbol] == boundary}
        born = {symbol for symbol in right_symbols if first[symbol] == boundary + 1}
        cross = {
            symbol
            for symbol, indexes in occurrences.items()
            if indexes[0] <= boundary < indexes[-1]
        }
        cross_edges = tuple(
            edge for edge in edges if edge.source_statement <= boundary < edge.target_statement
        )
        nearby = tuple(
            edge
            for edge in edges
            if left_start <= edge.source_statement < edge.target_statement <= right_end
        )
        local_cross = tuple(
            edge for edge in nearby if edge.source_statement <= boundary < edge.target_statement
        )
        left_edges = tuple(
            edge
            for edge in nearby
            if left_start <= edge.source_statement < edge.target_statement <= boundary
        )
        right_edges = tuple(
            edge
            for edge in nearby
            if boundary < edge.source_statement < edge.target_statement <= right_end
        )
        input_symbols = {edge.symbol for edge in cross_edges}
        output_symbols = {
            symbol
            for symbol in input_symbols
            if any(symbol in item.definitions or symbol in item.mutations for item in left_slice)
        }
        followup = tuple(
            edge
            for edge in cross_edges
            if edge.source_statement == boundary
            and edge.target_statement <= min(right_end, boundary + 2)
        )
        evidence = completion.get(boundary)
        left_direct = standalone_calls(left_statement)
        right_direct = standalone_calls(right_statement)
        left_support = existing_call_module_support(left_statement)
        right_support = existing_call_module_support(right_statement)
        left_outputs = set().union(*(call.output_symbols for call in left_direct))
        right_inputs = set().union(*(call.input_symbols for call in right_direct))
        handoff_symbols = left_outputs & right_inputs
        setup_target = next(
            (
                item
                for item in statements[boundary + 1 : min(len(statements), boundary + 4)]
                if existing_call_module_support(item) > 0.0
            ),
            None,
        )
        setup_target_inputs = (
            set().union(*(call.input_symbols for call in standalone_calls(setup_target)))
            if setup_target is not None
            else set()
        )
        setup_symbols = (
            (left_statement.definitions | left_statement.mutations) & setup_target_inputs
            if setup_target is not None and left_support == 0.0
            else set()
        )
        finalization_symbols = (
            left_outputs & (right_statement.reads | right_statement.mutations)
            if left_support > 0.0 and right_support == 0.0
            else set()
        )
        left_primitive = bool(left_direct) and all(
            call.abstraction.value == "primitive" for call in left_direct
        )
        right_primitive = bool(right_direct) and all(
            call.abstraction.value == "primitive" for call in right_direct
        )
        spans = [edge.target_statement - edge.source_statement for edge in cross_edges]
        reuse = Counter(edge.symbol for edge in cross_edges)
        reliability = _reliability(left_slice + right_slice)
        constraints = set(
            statements[boundary].forbid_cut_after | statements[boundary + 1].forbid_cut_before
        )
        if not statements[boundary].parse_reliable or not statements[boundary + 1].parse_reliable:
            constraints.add("adjacent_parse_error")
        risks = {
            risk.value
            for item in left_slice + right_slice
            for risk in item.risks
            if risk is not Risk.PARSE_ERROR
        }
        facts.append(
            BoundaryRawFacts(
                schema_version=RAW_FACT_SCHEMA_VERSION,
                region_id=region.id,
                boundary_index=boundary + 1,
                after_line=statements[boundary].source.end_line,
                before_line=statements[boundary + 1].source.start_line,
                left_context_size=len(left_slice),
                right_context_size=len(right_slice),
                left_symbol_count=len(left_symbols),
                right_symbol_count=len(right_symbols),
                left_symbols=tuple(sorted(left_symbols)),
                right_symbols=tuple(sorted(right_symbols)),
                dead_symbols=tuple(sorted(dead)),
                born_symbols=tuple(sorted(born)),
                cross_symbols=tuple(sorted(cross)),
                input_symbols=tuple(sorted(input_symbols)),
                output_symbols=tuple(sorted(output_symbols)),
                cross_edges=cross_edges,
                local_cross_dependency_count=len(local_cross),
                nearby_dependency_count=len(nearby),
                left_internal_data_edge_count=len(left_edges),
                right_internal_data_edge_count=len(right_edges),
                dependency_span_mean=sum(spans) / len(spans) if spans else 0.0,
                dependency_span_max=max(spans, default=0),
                dependency_target_count=len({edge.target_statement for edge in cross_edges}),
                dependency_reuse_mass=sum(count * count for count in reuse.values()),
                left_calls=tuple(sorted(_calls(left_slice))),
                right_calls=tuple(sorted(_calls(right_slice))),
                left_access_domains=tuple(sorted(_access_domains(left_slice))),
                right_access_domains=tuple(sorted(_access_domains(right_slice))),
                left_call_kind_histogram=_histogram(_call_kinds(left_slice)),
                right_call_kind_histogram=_histogram(_call_kinds(right_slice)),
                standalone_call_transition=min(left_support, right_support),
                artifact_handoff=(
                    len(handoff_symbols) / max(1, len(left_outputs | right_inputs))
                    if left_support > 0.0 and right_support > 0.0
                    else 0.0
                ),
                unfinished_call_setup=(
                    len(setup_symbols) / max(1, len(setup_target_inputs))
                ),
                unfinished_call_finalization=(
                    len(finalization_symbols) / max(1, len(left_outputs))
                ),
                primitive_call_chain=float(left_primitive and right_primitive),
                terminal_control_left=bool(
                    statements[boundary].control_effects
                    & {ControlEffect.RETURN, ControlEffect.THROW}
                ),
                left_effect_histogram=_histogram(
                    effect.value for item in left_slice for effect in item.effects
                ),
                right_effect_histogram=_histogram(
                    effect.value for item in right_slice for effect in item.effects
                ),
                left_role_histogram=_histogram(
                    role.value for item in left_slice for role in item.roles
                ),
                right_role_histogram=_histogram(
                    role.value for item in right_slice for role in item.roles
                ),
                compound_ends_here=statements[boundary].is_compound,
                control_followup_edge_count=len(followup),
                unfinished_work_mass=sum(
                    (1.0 + reuse[edge.symbol]) / max(1, edge.target_statement - boundary)
                    for edge in cross_edges
                ),
                completion_chain_length=(evidence.through_statement - boundary if evidence else 0),
                completion_roles=evidence.roles if evidence else (),
                completion_symbols=evidence.symbols if evidence else (),
                constraints=tuple(sorted(constraints)),
                risks=tuple(sorted(risks)),
                reliability=reliability,
            )
        )
    return facts


def _symbols(statements: Iterable) -> set[str]:
    return set().union(*(item.definitions | item.reads | item.mutations for item in statements))


def _calls(statements: Iterable) -> set[str]:
    return set().union(
        *(
            (item.resolved_calls | item.unresolved_calls)
            if item.call_resolution_available
            else item.calls
            for item in statements
        )
    )


def _access_domains(statements: Iterable) -> set[str]:
    return set().union(*(item.access_domains for item in statements))


def _call_kinds(statements: Iterable) -> Iterable[str]:
    for item in statements:
        if item.resolved_calls:
            yield "resolved_call"
        if item.unresolved_calls:
            yield "external_or_unresolved_call"
        if item.resolved_indexes:
            yield "index_access"
        if Risk.INDIRECT_CALL in item.risks:
            yield "indirect_call"


def _histogram(values: Iterable[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(Counter(values).items()))


def _reliability(statements: list) -> Reliability:
    parse = min(float(item.parse_reliable) for item in statements)
    resolved = sum(len(item.resolved_calls) + len(item.resolved_indexes) for item in statements)
    unresolved = sum(len(item.unresolved_calls) for item in statements)
    call_resolution = resolved / (resolved + unresolved) if resolved + unresolved else 1.0
    risks = {risk for item in statements for risk in item.risks}
    dynamic = bool(
        risks
        & {
            Risk.DYNAMIC_EVALUATION,
            Risk.WORKSPACE_INJECTION,
            Risk.GLOBAL_STATE,
            Risk.PERSISTENT_STATE,
        }
    )
    alias = bool(risks & {Risk.AMBIGUOUS_CALL_OR_INDEX, Risk.INDIRECT_CALL})
    reasons = []
    if parse < 1.0:
        reasons.append("parse_error")
    if unresolved:
        reasons.append("unresolved_call")
    if Risk.AMBIGUOUS_CALL_OR_INDEX in risks:
        reasons.append("ambiguous_call_index")
    if Risk.INDIRECT_CALL in risks:
        reasons.append("indirect_call")
    if dynamic:
        reasons.append("dynamic_workspace")
    if Risk.EXTERNAL_DEPENDENCY in risks:
        reasons.append("external_dependency")
    if Risk.PATH_DEPENDENCY in risks:
        reasons.append("path_dependency")
    if Risk.GLOBAL_STATE in risks or Risk.PERSISTENT_STATE in risks:
        reasons.append("global_persistent_state")
    unknown_role = any(OperationRole.UNKNOWN in item.roles or not item.roles for item in statements)
    if unknown_role:
        reasons.append("unknown_role")
    dependency = parse * (0.35 if dynamic else 1.0) * (0.7 if alias else 1.0)
    role = parse * (0.7 if unknown_role else 1.0)
    return Reliability(
        parse=parse,
        call_resolution=call_resolution,
        dependency=dependency,
        role=role,
        effect=parse,
        callsite=parse * callsite_reliability(statements),
        dynamic_workspace_risk=float(dynamic),
        alias_uncertainty=float(alias),
        dependency_reason_codes=tuple(reasons),
    )
