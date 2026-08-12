from __future__ import annotations

from collections.abc import Callable

from tree_sitter import Node

from codeseam.core.ir import (
    ControlEffect,
    ControlFlowEdge,
    ControlFlowEdgeKind,
    ControlFlowGraph,
    FlowNode,
    SourceRange,
    StatementIR,
)

SummaryFactory = Callable[[int, Node, bytes], StatementIR]
IGNORED_NODES = {"comment", "function_definition", "class_definition"}


class MatlabControlFlowBuilder:
    """Lower structured MATLAB syntax into a language-neutral statement CFG."""

    def __init__(self, source: bytes, summarize: SummaryFactory, region_source: SourceRange):
        self.source = source
        self.summarize = summarize
        self.region_source = region_source
        self.nodes: list[FlowNode] = []
        self.edges: list[ControlFlowEdge] = []

    def build(self, statements: list[Node]) -> ControlFlowGraph:
        entry = self._synthetic("entry")
        exit_node = self._synthetic("exit")
        first = self._sequence(self._statements(statements), exit_node, None, None, None)
        self._edge(entry, first)
        return ControlFlowGraph(self.nodes, self.edges, entry, exit_node)

    def _sequence(
        self,
        statements: list[Node],
        continuation: int,
        top_level: int | None,
        break_target: int | None,
        continue_target: int | None,
    ) -> int:
        current = continuation
        for local_index, statement in reversed(list(enumerate(statements))):
            owner = local_index if top_level is None else top_level
            current = self._statement(statement, current, owner, break_target, continue_target)
        return current

    def _statement(
        self,
        node: Node,
        continuation: int,
        owner: int,
        break_target: int | None,
        continue_target: int | None,
    ) -> int:
        if node.type == "if_statement":
            return self._if_statement(node, continuation, owner, break_target, continue_target)
        if node.type in {"for_statement", "parfor_statement", "while_statement"}:
            return self._loop_statement(node, continuation, owner)

        flow = self._node(node, owner)
        summary = self.summarize(-1, node, self.source)
        if ControlEffect.RETURN in summary.control_effects:
            self._edge(flow, 1, ControlFlowEdgeKind.RETURN)
        elif ControlEffect.BREAK in summary.control_effects:
            self._edge(flow, break_target or continuation, ControlFlowEdgeKind.BREAK)
        elif ControlEffect.CONTINUE in summary.control_effects:
            self._edge(flow, continue_target or continuation, ControlFlowEdgeKind.CONTINUE)
        else:
            self._edge(flow, continuation)
        return flow

    def _if_statement(
        self,
        node: Node,
        continuation: int,
        owner: int,
        break_target: int | None,
        continue_target: int | None,
    ) -> int:
        condition = node.child_by_field_name("condition")
        condition_id = self._node(condition or node, owner, "condition")
        body = next((child for child in node.named_children if child.type == "block"), None)
        body_entry = self._sequence(
            self._statements(list(body.named_children)) if body else [],
            continuation,
            owner,
            break_target,
            continue_target,
        )
        self._edge(condition_id, body_entry, ControlFlowEdgeKind.TRUE)

        alternative = continuation
        clauses = [
            child for child in node.named_children if child.type in {"elseif_clause", "else_clause"}
        ]
        for clause in reversed(clauses):
            block = next((child for child in clause.named_children if child.type == "block"), None)
            clause_body = self._sequence(
                self._statements(list(block.named_children)) if block else [],
                continuation,
                owner,
                break_target,
                continue_target,
            )
            if clause.type == "else_clause":
                alternative = clause_body
            else:
                clause_condition = clause.child_by_field_name("condition")
                clause_id = self._node(clause_condition or clause, owner, "condition")
                self._edge(clause_id, clause_body, ControlFlowEdgeKind.TRUE)
                self._edge(clause_id, alternative, ControlFlowEdgeKind.FALSE)
                alternative = clause_id
        self._edge(condition_id, alternative, ControlFlowEdgeKind.FALSE)
        return condition_id

    def _loop_statement(self, node: Node, continuation: int, owner: int) -> int:
        header_node = node.child_by_field_name("condition")
        if header_node is None:
            header_node = next(
                (child for child in node.named_children if child.type == "iterator"), node
            )
        header = self._node(header_node, owner, "loop_header")
        if header_node.type == "iterator":
            identifiers = [
                child for child in header_node.named_children if child.type == "identifier"
            ]
            if identifiers:
                name = self.source[identifiers[0].start_byte : identifiers[0].end_byte].decode()
                self.nodes[header].definitions.add(name)
                self.nodes[header].reads.discard(name)
        body = next((child for child in node.named_children if child.type == "block"), None)
        body_entry = self._sequence(
            self._statements(list(body.named_children)) if body else [],
            header,
            owner,
            continuation,
            header,
        )
        self._edge(header, body_entry, ControlFlowEdgeKind.TRUE)
        self._edge(header, continuation, ControlFlowEdgeKind.FALSE)
        return header

    def _node(self, node: Node, owner: int, kind: str | None = None) -> int:
        summary = self.summarize(-1, node, self.source)
        node_id = len(self.nodes)
        self.nodes.append(
            FlowNode(
                id=node_id,
                kind=kind or summary.kind,
                source=summary.source,
                top_level_statement=owner,
                definitions=set(summary.definitions),
                reads=set(summary.reads),
                mutations=set(summary.mutations),
            )
        )
        return node_id

    def _synthetic(self, kind: str) -> int:
        node_id = len(self.nodes)
        self.nodes.append(FlowNode(node_id, kind, self.region_source, -1, synthetic=True))
        return node_id

    def _edge(
        self, source: int, target: int, kind: ControlFlowEdgeKind = ControlFlowEdgeKind.NEXT
    ) -> None:
        self.edges.append(ControlFlowEdge(source, target, kind))

    @staticmethod
    def _statements(nodes: list[Node]) -> list[Node]:
        return [node for node in nodes if node.type not in IGNORED_NODES]
