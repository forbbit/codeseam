from __future__ import annotations

from script_boundary.core.dependencies import projected_dependence_edges, symbol_occurrences
from script_boundary.core.ir import DependenceKind, ExecutableRegion, ModuleQuality

MODULE_WEIGHTS = {
    "internal_cohesion": 0.27,
    "external_compactness": 0.22,
    "symbol_locality": 0.18,
    "size_fitness": 0.14,
    "finalization_completeness": 0.12,
    "orphan_resistance": 0.07,
}


def evaluate_module(region: ExecutableRegion, start: int, end: int) -> ModuleQuality:
    """Evaluate the inclusive statement interval [start, end]."""
    if not (0 <= start <= end < len(region.statements)):
        raise ValueError("invalid module interval")
    statements = region.statements[start : end + 1]
    dependence_edges = projected_dependence_edges(region, include_internal=True)
    all_edges = [edge for edge in dependence_edges if edge.kind == DependenceKind.DATA]
    internal_edges = [edge for edge in all_edges if start <= edge.source <= edge.target <= end]
    incoming_edges = [edge for edge in all_edges if edge.source < start <= edge.target <= end]
    outgoing_edges = [edge for edge in all_edges if start <= edge.source <= end < edge.target]
    internal_control_edges = [
        edge
        for edge in dependence_edges
        if edge.kind == DependenceKind.CONTROL and start <= edge.source <= edge.target <= end
    ]
    inputs = sorted({edge.symbol for edge in incoming_edges})
    outputs = sorted({edge.symbol for edge in outgoing_edges})
    symbols = set().union(*(item.definitions | item.reads | item.mutations for item in statements))
    occurrences = symbol_occurrences(region)
    local_symbols = {
        symbol
        for symbol in symbols
        if symbol in occurrences
        and start <= occurrences[symbol][0] <= occurrences[symbol][-1] <= end
    }
    statement_count = len(statements)
    possible_links = max(1, statement_count - 1)
    # Control edges are structural cohesion evidence, but deliberately count less
    # than value flow so a large conditional cannot dominate module quality.
    cohesion_mass = len(internal_edges) + 0.35 * len(internal_control_edges)
    cohesion = cohesion_mass / (cohesion_mass + possible_links)
    interface_count = len(inputs) + len(outputs)
    external_compactness = 1.0 / (1.0 + 0.35 * interface_count)
    locality = len(local_symbols) / len(symbols) if symbols else 1.0
    size_fitness = _size_fitness(statement_count)
    trailing_compound = statements[-1].is_compound
    trailing_outputs = len(
        {edge.symbol for edge in outgoing_edges if edge.source == statements[-1].index}
    )
    finalization = 1.0 / (1.0 + trailing_outputs) if trailing_compound else 1.0
    orphan = 0.0 if statement_count == 1 and _is_terminal_effect(statements[0]) else 1.0
    features = {
        "internal_cohesion": cohesion,
        "external_compactness": external_compactness,
        "symbol_locality": locality,
        "size_fitness": size_fitness,
        "finalization_completeness": finalization,
        "orphan_resistance": orphan,
    }
    score = sum(MODULE_WEIGHTS[name] * value for name, value in features.items())
    return ModuleQuality(
        start_statement=start + 1,
        end_statement=end + 1,
        start_line=statements[0].source.start_line,
        end_line=statements[-1].source.end_line,
        score=score,
        features=features,
        raw_features={
            "statement_count": float(statement_count),
            "internal_edge_count": float(len(internal_edges)),
            "internal_control_edge_count": float(len(internal_control_edges)),
            "input_count": float(len(inputs)),
            "output_count": float(len(outputs)),
            "local_symbol_count": float(len(local_symbols)),
            "symbol_count": float(len(symbols)),
            "trailing_compound_output_count": float(trailing_outputs),
        },
        inputs=inputs,
        outputs=outputs,
    )


def attach_adjacent_module_quality(region: ExecutableRegion, boundaries, *, window: int) -> None:
    for boundary in boundaries:
        split = boundary.boundary
        left_start = max(0, split - window)
        right_end = min(len(region.statements) - 1, split + window - 1)
        boundary.left_module_quality = evaluate_module(region, left_start, split - 1)
        boundary.right_module_quality = evaluate_module(region, split, right_end)


def _size_fitness(count: int) -> float:
    if count == 1:
        return 0.0
    if count == 2:
        return 0.5
    if count == 3:
        return 0.75
    if count <= 40:
        return 1.0
    return 1.0 / (1.0 + 0.002 * (count - 40))


def _is_terminal_effect(statement) -> bool:
    return bool({effect.value for effect in statement.effects} & {"output", "file_write"})
