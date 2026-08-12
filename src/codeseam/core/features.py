from __future__ import annotations

from dataclasses import dataclass

from codeseam.core.completion import completion_frontiers
from codeseam.core.dependencies import semantic_def_use_edges, symbol_occurrences
from codeseam.core.ir import BoundaryAnalysis, ExecutableRegion, Risk
from codeseam.core.module_quality import attach_adjacent_module_quality

NORMALIZATION_VERSION = "boundary-features-v6"


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    window: int = 4
    medium_window: int = 12


def extract_boundaries(
    region: ExecutableRegion, config: FeatureConfig | None = None
) -> list[BoundaryAnalysis]:
    config = config or FeatureConfig()
    statements = region.statements
    if len(statements) < 2:
        return []
    occurrences = symbol_occurrences(region)
    edges = semantic_def_use_edges(region)
    completion = completion_frontiers(region)
    first = {symbol: indexes[0] for symbol, indexes in occurrences.items()}
    last = {symbol: indexes[-1] for symbol, indexes in occurrences.items()}
    results: list[BoundaryAnalysis] = []

    for boundary_index in range(len(statements) - 1):
        left_start = max(0, boundary_index - config.window + 1)
        right_end = min(len(statements) - 1, boundary_index + config.window)
        left_symbols = _symbols(statements[left_start : boundary_index + 1])
        right_symbols = _symbols(statements[boundary_index + 1 : right_end + 1])
        dead = {symbol for symbol in left_symbols if last[symbol] == boundary_index}
        born = {symbol for symbol in right_symbols if first[symbol] == boundary_index + 1}
        cross = {
            symbol
            for symbol, indexes in occurrences.items()
            if indexes[0] <= boundary_index < indexes[-1]
        }
        cross_edges = [
            edge
            for edge in edges
            if edge.source_statement <= boundary_index < edge.target_statement
        ]
        nearby_edges = [
            edge
            for edge in edges
            if left_start <= edge.source_statement < edge.target_statement <= right_end
        ]
        local_cross_edges = [
            edge
            for edge in nearby_edges
            if edge.source_statement <= boundary_index < edge.target_statement
        ]
        left_edges = [
            edge
            for edge in nearby_edges
            if left_start <= edge.source_statement < edge.target_statement <= boundary_index
        ]
        right_edges = [
            edge
            for edge in nearby_edges
            if boundary_index < edge.source_statement < edge.target_statement <= right_end
        ]
        input_symbols = {edge.symbol for edge in cross_edges}
        output_symbols = {
            symbol
            for symbol in input_symbols
            if any(
                symbol in statement.definitions or symbol in statement.mutations
                for statement in statements[left_start : boundary_index + 1]
            )
        }

        death = _ratio(len(dead), len(left_symbols), scale=2.0)
        birth = _ratio(len(born), len(right_symbols), scale=2.0)
        interface = 1.0 / (1.0 + 0.45 * len(cross))
        dependency_drop = _dependency_retention(
            edges, boundary_index, left_start, right_end
        )
        medium_dependency_drop = _dependency_retention(
            edges,
            boundary_index,
            max(0, boundary_index - config.medium_window + 1),
            min(len(statements) - 1, boundary_index + config.medium_window),
        )
        union = left_symbols | right_symbols
        vocabulary_shift = (
            1.0 if not union else 1.0 - len(left_symbols & right_symbols) / len(union)
        )
        raw_structural = 1.0 if statements[boundary_index].is_compound else 0.0
        left_cohesion = _edge_cohesion(len(left_edges), boundary_index - left_start + 1)
        right_cohesion = _edge_cohesion(len(right_edges), right_end - boundary_index)
        cohesion_support = (left_cohesion + right_cohesion) / 2.0
        left_calls = set().union(
            *(
                statement.resolved_calls
                if statement.call_resolution_available
                else statement.calls
                for statement in statements[left_start : boundary_index + 1]
            )
        )
        right_calls = set().union(
            *(
                statement.resolved_calls
                if statement.call_resolution_available
                else statement.calls
                for statement in statements[boundary_index + 1 : right_end + 1]
            )
        )
        left_effects = {
            effect.value
            for statement in statements[left_start : boundary_index + 1]
            for effect in statement.effects
        }
        right_effects = {
            effect.value
            for statement in statements[boundary_index + 1 : right_end + 1]
            for effect in statement.effects
        }
        call_set_change = _set_change(left_calls, right_calls)
        effect_set_change = _set_change(left_effects, right_effects)
        followup_edges = [
            edge
            for edge in cross_edges
            if edge.source_statement == boundary_index
            and edge.target_statement <= min(right_end, boundary_index + 2)
        ]
        control_followup_completion = (
            1.0 / (1.0 + len(followup_edges)) if statements[boundary_index].is_compound else 0.5
        )
        structural = raw_structural * control_followup_completion
        dependency_targets = {edge.target_statement for edge in cross_edges}
        dependency_target_dispersion = (
            1.0
            if not cross_edges
            else len(dependency_targets) / len(cross_edges)
        )
        input_compactness = 1.0 / (1.0 + 0.35 * len(input_symbols))
        output_compactness = 1.0 / (1.0 + 0.35 * len(output_symbols))

        constraints = sorted(
            statements[boundary_index].forbid_cut_after
            | statements[boundary_index + 1].forbid_cut_before
        )
        completion_evidence = completion.get(boundary_index)
        if (
            not statements[boundary_index].parse_reliable
            or not statements[boundary_index + 1].parse_reliable
        ):
            constraints.append("adjacent_parse_error")
        constraints = sorted(set(constraints))

        risks = sorted(
            {
                risk.value
                for statement in statements[left_start : right_end + 1]
                for risk in statement.risks
                if risk is not Risk.PARSE_ERROR
            }
        )
        results.append(
            BoundaryAnalysis(
                region_id=region.id,
                boundary=boundary_index + 1,
                after_line=statements[boundary_index].source.end_line,
                before_line=statements[boundary_index + 1].source.start_line,
                score=0.0,
                features={
                    "variable_death": death,
                    "variable_birth": birth,
                    "interface_compactness": interface,
                    "dependency_drop": dependency_drop,
                    "medium_dependency_drop": medium_dependency_drop,
                    "vocabulary_shift": vocabulary_shift,
                    "structural_completion": structural,
                    "input_interface_compactness": input_compactness,
                    "output_interface_compactness": output_compactness,
                    "local_cohesion_support": cohesion_support,
                    "call_set_change": call_set_change,
                    "effect_set_change": effect_set_change,
                    "control_followup_completion": control_followup_completion,
                    "dependency_target_dispersion": dependency_target_dispersion,
                    "task_completion": 0.0 if completion_evidence else 1.0,
                },
                raw_features={
                    "dead_symbol_count": float(len(dead)),
                    "born_symbol_count": float(len(born)),
                    "cross_symbol_count": float(len(cross)),
                    "input_interface_count": float(len(input_symbols)),
                    "output_interface_count": float(len(output_symbols)),
                    "cross_dependency_count": float(len(cross_edges)),
                    "local_cross_dependency_count": float(len(local_cross_edges)),
                    "nearby_dependency_count": float(len(nearby_edges)),
                    "left_internal_edge_count": float(len(left_edges)),
                    "right_internal_edge_count": float(len(right_edges)),
                    "left_call_count": float(len(left_calls)),
                    "right_call_count": float(len(right_calls)),
                    "left_effect_count": float(len(left_effects)),
                    "right_effect_count": float(len(right_effects)),
                    "control_followup_edge_count": float(len(followup_edges)),
                    "dependency_target_count": float(len(dependency_targets)),
                    "raw_structural_completion": raw_structural,
                    "unfinished_completion_chain": float(completion_evidence is not None),
                },
                normalization_version=NORMALIZATION_VERSION,
                dead_symbols=sorted(dead),
                born_symbols=sorted(born),
                cross_symbols=sorted(cross),
                cross_edges=cross_edges,
                constraints=constraints,
                risks=risks,
                completion_roles=(
                    list(completion_evidence.roles) if completion_evidence else []
                ),
                completion_symbols=(
                    list(completion_evidence.symbols) if completion_evidence else []
                ),
            )
        )
    attach_adjacent_module_quality(region, results, window=config.window)
    return results


def _symbols(statements) -> set[str]:
    return set().union(
        *(statement.definitions | statement.reads | statement.mutations for statement in statements)
    )


def _ratio(numerator: int, denominator: int, scale: float) -> float:
    if denominator == 0:
        return 0.0
    return min(1.0, scale * numerator / denominator)


def _edge_cohesion(edge_count: int, statement_count: int) -> float:
    return edge_count / (edge_count + max(1, statement_count - 1))


def _set_change(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return 1.0 - len(left & right) / len(union)


def _dependency_retention(edges, boundary: int, start: int, end: int) -> float:
    nearby = [
        edge
        for edge in edges
        if start <= edge.source_statement < edge.target_statement <= end
    ]
    if not nearby:
        return 0.5
    crossing = sum(
        edge.source_statement <= boundary < edge.target_statement for edge in nearby
    )
    return 1.0 - crossing / len(nearby)
