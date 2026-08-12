from __future__ import annotations

from collections import defaultdict

from codeseam.core.flow import program_dependence_graph
from codeseam.core.ir import (
    DependenceKind,
    DependencyEdge,
    ExecutableRegion,
    ProgramDependenceEdge,
)


def symbol_occurrences(region: ExecutableRegion) -> dict[str, list[int]]:
    occurrences: dict[str, list[int]] = defaultdict(list)
    for statement in region.statements:
        symbols = statement.definitions | statement.reads | statement.mutations
        for symbol in symbols:
            occurrences[symbol].append(statement.index)
    return {symbol: sorted(set(indexes)) for symbol, indexes in occurrences.items()}


def def_use_edges(region: ExecutableRegion) -> list[DependencyEdge]:
    last_write: dict[str, int] = {}
    edges: list[DependencyEdge] = []
    for statement in region.statements:
        for symbol in sorted(statement.reads | statement.mutations):
            source = last_write.get(symbol)
            if source is not None and source != statement.index:
                edges.append(DependencyEdge(source, statement.index, symbol))
        for symbol in statement.definitions | statement.mutations:
            last_write[symbol] = statement.index
    return edges


def semantic_def_use_edges(region: ExecutableRegion) -> list[DependencyEdge]:
    """Return path-sensitive dependencies projected onto legal top-level cuts.

    The linear implementation remains the fallback for language frontends that do
    not emit a CFG yet.
    """
    if region.control_flow is None:
        return def_use_edges(region)
    nodes = {node.id: node for node in region.control_flow.nodes}
    projected: set[tuple[int, int, str]] = set()
    for edge in program_dependence_graph(region.control_flow).edges:
        if edge.kind != DependenceKind.DATA or edge.symbol is None:
            continue
        source = nodes[edge.source].top_level_statement
        target = nodes[edge.target].top_level_statement
        if source < 0 or target < 0 or source == target:
            continue
        projected.add((source, target, edge.symbol))
    return [DependencyEdge(*item) for item in sorted(projected)]


def projected_dependence_edges(
    region: ExecutableRegion, *, include_internal: bool = False
) -> list[ProgramDependenceEdge]:
    """Project the PDG onto top-level statements for interval-quality analysis."""
    if region.dependence_cache is None and region.control_flow is None:
        region.dependence_cache = [
            ProgramDependenceEdge(
                edge.source_statement, edge.target_statement, DependenceKind.DATA, edge.symbol
            )
            for edge in def_use_edges(region)
        ]
    elif region.dependence_cache is None:
        nodes = {node.id: node for node in region.control_flow.nodes}
        projected: set[ProgramDependenceEdge] = set()
        for edge in program_dependence_graph(region.control_flow).edges:
            source = nodes[edge.source].top_level_statement
            target = nodes[edge.target].top_level_statement
            if source < 0 or target < 0:
                continue
            projected.add(ProgramDependenceEdge(source, target, edge.kind, edge.symbol))
        region.dependence_cache = sorted(
            projected,
            key=lambda edge: (edge.source, edge.target, edge.kind.value, edge.symbol or ""),
        )
    if include_internal:
        return region.dependence_cache
    return [edge for edge in region.dependence_cache if edge.source != edge.target]
