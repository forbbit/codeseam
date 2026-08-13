from __future__ import annotations

from dataclasses import dataclass

from codeseam.core.dependencies import semantic_def_use_edges
from codeseam.core.ir import BoundaryAnalysis, ExecutableRegion
from codeseam.core.module_quality import attach_adjacent_module_quality
from codeseam.core.raw_facts import BoundaryRawFacts, extract_raw_facts

NORMALIZATION_VERSION = "boundary-features-callsite"


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    window: int = 4
    medium_window: int = 12


def extract_boundaries(
    region: ExecutableRegion, config: FeatureConfig | None = None
) -> list[BoundaryAnalysis]:
    """Build explainable boundary output exclusively from stable Raw Facts."""
    config = config or FeatureConfig()
    edges = semantic_def_use_edges(region)
    results = [
        legacy_boundary_from_raw(facts, edges, config)
        for facts in extract_raw_facts(
            region, window=config.window, medium_window=config.medium_window
        )
    ]
    attach_adjacent_module_quality(region, results, window=config.window)
    return results


def legacy_boundary_from_raw(facts: BoundaryRawFacts, edges, config: FeatureConfig) -> BoundaryAnalysis:
    boundary = facts.boundary_index - 1
    left_start = max(0, boundary - config.window + 1)
    right_end = boundary + facts.right_context_size
    medium_start = max(0, boundary - config.medium_window + 1)
    medium_end = boundary + config.medium_window
    left_effects = {name for name, _ in facts.left_effect_histogram}
    right_effects = {name for name, _ in facts.right_effect_histogram}
    control_completion = (
        1.0 / (1.0 + facts.control_followup_edge_count)
        if facts.compound_ends_here
        else 0.5
    )
    left_cohesion = _edge_cohesion(
        facts.left_internal_data_edge_count, facts.left_context_size
    )
    right_cohesion = _edge_cohesion(
        facts.right_internal_data_edge_count, facts.right_context_size
    )
    dependency_dispersion = (
        1.0
        if not facts.cross_edges
        else facts.dependency_target_count / len(facts.cross_edges)
    )
    features = {
        "variable_death": _ratio(facts.dead_symbol_count, facts.left_symbol_count, 2.0),
        "variable_birth": _ratio(facts.born_symbol_count, facts.right_symbol_count, 2.0),
        "interface_compactness": 1.0 / (1.0 + 0.45 * facts.cross_symbol_count),
        "dependency_drop": _dependency_retention(edges, boundary, left_start, right_end),
        "medium_dependency_drop": _dependency_retention(
            edges, boundary, medium_start, medium_end
        ),
        "vocabulary_shift": _vocabulary_shift(facts),
        "structural_completion": float(facts.compound_ends_here) * control_completion,
        "input_interface_compactness": 1.0 / (1.0 + 0.35 * facts.input_interface_count),
        "output_interface_compactness": 1.0 / (1.0 + 0.35 * facts.output_interface_count),
        "local_cohesion_support": (left_cohesion + right_cohesion) / 2.0,
        "call_set_change": _set_change(set(facts.left_calls), set(facts.right_calls)),
        "effect_set_change": _set_change(left_effects, right_effects),
        "control_followup_completion": control_completion,
        "dependency_target_dispersion": dependency_dispersion,
        "task_completion": float(facts.completion_chain_length == 0),
        "standalone_call_transition": facts.standalone_call_transition,
        "artifact_handoff": facts.artifact_handoff,
        "call_setup_completion": 1.0 - facts.unfinished_call_setup,
        "call_finalization_completion": 1.0 - facts.unfinished_call_finalization,
        "nonprimitive_call_chain": 1.0 - facts.primitive_call_chain,
    }
    return BoundaryAnalysis(
        region_id=facts.region_id,
        boundary=facts.boundary_index,
        after_line=facts.after_line,
        before_line=facts.before_line,
        score=0.0,
        features=features,
        raw_features={
            "dead_symbol_count": float(facts.dead_symbol_count),
            "born_symbol_count": float(facts.born_symbol_count),
            "cross_symbol_count": float(facts.cross_symbol_count),
            "input_interface_count": float(facts.input_interface_count),
            "output_interface_count": float(facts.output_interface_count),
            "cross_dependency_count": float(facts.cross_dependency_count),
            "local_cross_dependency_count": float(facts.local_cross_dependency_count),
            "nearby_dependency_count": float(facts.nearby_dependency_count),
            "left_internal_edge_count": float(facts.left_internal_data_edge_count),
            "right_internal_edge_count": float(facts.right_internal_data_edge_count),
            "left_call_count": float(facts.left_call_count),
            "right_call_count": float(facts.right_call_count),
            "left_effect_count": float(facts.left_effect_count),
            "right_effect_count": float(facts.right_effect_count),
            "control_followup_edge_count": float(facts.control_followup_edge_count),
            "dependency_target_count": float(facts.dependency_target_count),
            "raw_structural_completion": float(facts.compound_ends_here),
            "unfinished_completion_chain": float(facts.completion_chain_length > 0),
            "unfinished_call_setup": facts.unfinished_call_setup,
            "unfinished_call_finalization": facts.unfinished_call_finalization,
            "primitive_call_chain": facts.primitive_call_chain,
        },
        normalization_version=NORMALIZATION_VERSION,
        dead_symbols=list(facts.dead_symbols),
        born_symbols=list(facts.born_symbols),
        cross_symbols=list(facts.cross_symbols),
        cross_edges=list(facts.cross_edges),
        constraints=list(facts.constraints),
        risks=list(facts.risks),
        completion_roles=list(facts.completion_roles),
        completion_symbols=list(facts.completion_symbols),
    )


def _ratio(numerator: int, denominator: int, scale: float) -> float:
    return 0.0 if denominator == 0 else min(1.0, scale * numerator / denominator)


def _edge_cohesion(edge_count: int, statement_count: int) -> float:
    return edge_count / (edge_count + max(1, statement_count - 1))


def _set_change(left: set[str], right: set[str]) -> float:
    union = left | right
    return 0.0 if not union else 1.0 - len(left & right) / len(union)


def _vocabulary_shift(facts: BoundaryRawFacts) -> float:
    left, right = set(facts.left_symbols), set(facts.right_symbols)
    union = left | right
    return 1.0 if not union else 1.0 - len(left & right) / len(union)


def _dependency_retention(edges, boundary: int, start: int, end: int) -> float:
    nearby = [
        edge for edge in edges if start <= edge.source_statement < edge.target_statement <= end
    ]
    if not nearby:
        return 0.5
    crossing = sum(edge.source_statement <= boundary < edge.target_statement for edge in nearby)
    return 1.0 - crossing / len(nearby)
