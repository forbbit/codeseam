from __future__ import annotations

from collections import defaultdict

from codeseam.core.ir import (
    ControlFlowGraph,
    DependenceKind,
    ProgramDependenceEdge,
    ProgramDependenceGraph,
)


def predecessors(graph: ControlFlowGraph) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    for edge in graph.edges:
        result[edge.target].add(edge.source)
    return {node.id: result[node.id] for node in graph.nodes}


def successors(graph: ControlFlowGraph) -> dict[int, set[int]]:
    result: dict[int, set[int]] = defaultdict(set)
    for edge in graph.edges:
        result[edge.source].add(edge.target)
    return {node.id: result[node.id] for node in graph.nodes}


def reaching_definition_edges(graph: ControlFlowGraph) -> list[ProgramDependenceEdge]:
    """Compute path-sensitive def-use edges with a classic forward fixed point."""
    pred = predecessors(graph)
    nodes = {node.id: node for node in graph.nodes}
    incoming: dict[int, dict[str, set[int]]] = {node_id: {} for node_id in nodes}
    outgoing: dict[int, dict[str, set[int]]] = {node_id: {} for node_id in nodes}

    changed = True
    while changed:
        changed = False
        for node in graph.nodes:
            merged: dict[str, set[int]] = defaultdict(set)
            for parent in pred[node.id]:
                for symbol, definitions in outgoing[parent].items():
                    merged[symbol].update(definitions)
            new_in = dict(merged)
            new_out = {symbol: set(definitions) for symbol, definitions in new_in.items()}
            for symbol in node.definitions | node.mutations:
                new_out[symbol] = {node.id}
            if new_in != incoming[node.id] or new_out != outgoing[node.id]:
                incoming[node.id] = new_in
                outgoing[node.id] = new_out
                changed = True

    edges: set[ProgramDependenceEdge] = set()
    for node in graph.nodes:
        for symbol in node.reads | node.mutations:
            for definition in incoming[node.id].get(symbol, set()):
                edges.add(ProgramDependenceEdge(definition, node.id, DependenceKind.DATA, symbol))
    return sorted(edges, key=lambda edge: (edge.source, edge.target, edge.symbol or ""))


def postdominators(graph: ControlFlowGraph) -> dict[int, set[int]]:
    succ = successors(graph)
    node_ids = {node.id for node in graph.nodes}
    result = {
        node_id: ({node_id} if node_id == graph.exit else set(node_ids)) for node_id in node_ids
    }
    changed = True
    while changed:
        changed = False
        for node_id in node_ids - {graph.exit}:
            children = succ[node_id] or {graph.exit}
            updated = {node_id} | set.intersection(*(result[child] for child in children))
            if updated != result[node_id]:
                result[node_id] = updated
                changed = True
    return result


def immediate_postdominators(graph: ControlFlowGraph) -> dict[int, int | None]:
    postdom = postdominators(graph)
    result: dict[int, int | None] = {graph.exit: None}
    for node in graph.nodes:
        if node.id == graph.exit:
            continue
        strict = postdom[node.id] - {node.id}
        result[node.id] = next(
            (
                candidate
                for candidate in strict
                if not any(candidate in postdom[other] for other in strict - {candidate})
            ),
            None,
        )
    return result


def control_dependence_edges(graph: ControlFlowGraph) -> list[ProgramDependenceEdge]:
    postdom = postdominators(graph)
    ipdom = immediate_postdominators(graph)
    edges: set[ProgramDependenceEdge] = set()
    for flow_edge in graph.edges:
        if flow_edge.target in postdom[flow_edge.source]:
            continue
        runner: int | None = flow_edge.target
        stop = ipdom[flow_edge.source]
        while runner is not None and runner != stop:
            edges.add(ProgramDependenceEdge(flow_edge.source, runner, DependenceKind.CONTROL))
            runner = ipdom[runner]
    return sorted(edges, key=lambda edge: (edge.source, edge.target))


def program_dependence_graph(graph: ControlFlowGraph) -> ProgramDependenceGraph:
    edges = reaching_definition_edges(graph) + control_dependence_edges(graph)
    return ProgramDependenceGraph([node.id for node in graph.nodes], edges)
