from codeseam.core.dependencies import projected_dependence_edges, semantic_def_use_edges
from codeseam.core.flow import program_dependence_graph, reaching_definition_edges
from codeseam.core.ir import ControlFlowEdgeKind, DependenceKind
from codeseam.languages.matlab import MatlabFrontend


def _cfg(source: bytes):
    region = MatlabFrontend().analyze_source(source, "memory.m").regions[0]
    assert region.control_flow is not None
    return region.control_flow


def test_if_else_keeps_both_reaching_definitions_at_merge() -> None:
    graph = _cfg(
        b"""if flag
x = left;
else
x = right;
end
y = x;
"""
    )
    data = reaching_definition_edges(graph)
    uses = [edge for edge in data if edge.symbol == "x"]
    assert len(uses) == 2
    assert len({edge.source for edge in uses}) == 2
    assert len({edge.target for edge in uses}) == 1


def test_loop_has_back_path_and_false_exit() -> None:
    graph = _cfg(b"x = 0;\nwhile x < limit\nx = x + 1;\nend\ny = x;\n")
    headers = [node for node in graph.nodes if node.kind == "loop_header"]
    assert len(headers) == 1
    header = headers[0]
    assert any(
        edge.source == header.id and edge.kind == ControlFlowEdgeKind.FALSE for edge in graph.edges
    )
    assert any(edge.target == header.id for edge in graph.edges)


def test_pdg_contains_data_and_control_dependence() -> None:
    graph = _cfg(b"if flag\nx = input;\nend\ny = x;\n")
    pdg = program_dependence_graph(graph)
    assert any(edge.kind == DependenceKind.DATA and edge.symbol == "x" for edge in pdg.edges)
    assert any(edge.kind == DependenceKind.CONTROL for edge in pdg.edges)


def test_continue_targets_loop_header_and_return_targets_exit() -> None:
    graph = _cfg(
        b"""while ready
if skip
continue
end
return
end
after = 1;
"""
    )
    header = next(node for node in graph.nodes if node.kind == "loop_header")
    continue_edge = next(edge for edge in graph.edges if edge.kind == ControlFlowEdgeKind.CONTINUE)
    return_edge = next(edge for edge in graph.edges if edge.kind == ControlFlowEdgeKind.RETURN)
    assert continue_edge.target == header.id
    assert return_edge.target == graph.exit


def test_path_sensitive_dependencies_project_to_top_level_statements() -> None:
    region = (
        MatlabFrontend()
        .analyze_source(
            b"""seed = 1;
if flag
x = seed;
else
x = fallback;
end
result = x;
""",
            "memory.m",
        )
        .regions[0]
    )
    edges = semantic_def_use_edges(region)
    assert any(
        edge.source_statement == 0 and edge.target_statement == 1 and edge.symbol == "seed"
        for edge in edges
    )
    assert any(
        edge.source_statement == 1 and edge.target_statement == 2 and edge.symbol == "x"
        for edge in edges
    )


def test_internal_control_dependence_is_preserved_for_module_quality() -> None:
    region = (
        MatlabFrontend()
        .analyze_source(b"if flag\nx = input;\nelse\nx = fallback;\nend\ny = x;\n", "memory.m")
        .regions[0]
    )
    projected = projected_dependence_edges(region, include_internal=True)
    assert any(
        edge.kind == DependenceKind.CONTROL and edge.source == edge.target == 0
        for edge in projected
    )
