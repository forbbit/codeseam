from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_matlab
from tree_sitter import Node

from codeseam.core.ir import (
    ControlEffect,
    Effect,
    ExecutableRegion,
    OperationRole,
    ProgramIR,
    Risk,
    SourceRange,
    StatementIR,
)
from codeseam.languages.matlab.control_flow import MatlabControlFlowBuilder
from codeseam.languages.matlab.symbols import BUILTIN_FUNCTIONS
from codeseam.parsing.tree_sitter_runtime import TreeSitterRuntime

COMMENT_NODES = {"comment"}
COMPOUND_NODES = {
    "for_statement",
    "while_statement",
    "if_statement",
    "switch_statement",
    "try_statement",
    "parfor_statement",
    "spmd_statement",
}
CONTROL_NODES = {
    "break_statement": ControlEffect.BREAK,
    "continue_statement": ControlEffect.CONTINUE,
    "return_statement": ControlEffect.RETURN,
}
DECLARATION_NODES = {"function_definition", "class_definition"}
DYNAMIC_NAMES = {"eval", "evalin", "assignin", "feval", "str2func"}
WORKSPACE_COMMANDS = {"load", "run", "clear", "who", "whos"}
FILE_WRITE_COMMANDS = {"save"}
PATH_COMMANDS = {"addpath", "rmpath", "path", "cd"}
OUTPUT_COMMANDS = {"disp", "fprintf"}
AGGREGATION_CALLS = {"sum", "mean", "median", "std", "max", "min", "norm"}
TRANSFORMATION_CALLS = {"fft", "ifft", "eig", "filter", "conv", "detrend", "corrcoef"}
SHAPING_CALLS = {"reshape", "transpose", "permute", "squeeze", "cat", "horzcat", "vertcat"}
DECISION_CALLS = {"find", "sort", "max", "min"}
ACQUISITION_CALLS = {"rand", "randi", "randn", "load", "readmatrix", "readtable"}


def _source_range(node: Node) -> SourceRange:
    return SourceRange(
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
    )


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _identifier_texts(node: Node, source: bytes) -> set[str]:
    found: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "identifier":
            found.add(_text(current, source))
        else:
            stack.extend(reversed(current.named_children))
    return found


class MatlabFrontend:
    language_id = "matlab"

    def __init__(self) -> None:
        self._runtime = TreeSitterRuntime(tree_sitter_matlab.language())

    def analyze_source(self, source: bytes, path: str) -> ProgramIR:
        tree = self._runtime.parse(source)
        root = tree.root_node
        diagnostics: list[str] = []
        if root.has_error:
            for error in self._error_nodes(root):
                diagnostics.append(
                    f"parse error at lines {error.start_point.row + 1}-{error.end_point.row + 1}"
                )

        regions: list[ExecutableRegion] = []
        script_nodes = [
            node
            for node in root.named_children
            if node.type not in COMMENT_NODES | DECLARATION_NODES
        ]
        if script_nodes:
            regions.append(self._make_region("script", None, root, script_nodes, source))

        function_count = 0
        for node in self._walk(root):
            if node.type != "function_definition":
                continue
            function_count += 1
            name_node = node.child_by_field_name("name")
            name = _text(name_node, source) if name_node else f"anonymous-{function_count}"
            body = next((child for child in node.named_children if child.type == "block"), None)
            if body is None:
                continue
            statements = [
                child
                for child in body.named_children
                if child.type not in COMMENT_NODES | DECLARATION_NODES
            ]
            region = self._make_region("function", name, body, statements, source)
            args = next(
                (child for child in node.named_children if child.type == "function_arguments"),
                None,
            )
            output = next(
                (child for child in node.named_children if child.type == "function_output"),
                None,
            )
            region.parameters = _identifier_texts(args, source) if args else set()
            region.declared_outputs = _identifier_texts(output, source) if output else set()
            regions.append(region)

        program = ProgramIR(
            language=self.language_id,
            path=Path(path),
            source_hash=hashlib.sha256(source).hexdigest(),
            regions=regions,
            diagnostics=diagnostics,
        )
        self._classify_calls(program)
        return program

    @staticmethod
    def _classify_calls(program: ProgramIR) -> None:
        for region in program.regions:
            known_variables = set(region.parameters)
            for statement in region.statements:
                statement.call_resolution_available = True
                statement.resolved_indexes = statement.calls & known_variables
                remaining = statement.calls - statement.resolved_indexes
                if statement.kind == "command":
                    statement.resolved_calls = remaining & (
                        BUILTIN_FUNCTIONS
                        | WORKSPACE_COMMANDS
                        | FILE_WRITE_COMMANDS
                        | PATH_COMMANDS
                        | OUTPUT_COMMANDS
                    )
                else:
                    statement.resolved_calls = remaining & BUILTIN_FUNCTIONS
                statement.unresolved_calls = remaining - statement.resolved_calls
                if not statement.unresolved_calls:
                    statement.risks.discard(Risk.AMBIGUOUS_CALL_OR_INDEX)
                known_variables |= statement.definitions | statement.mutations

    def _make_region(
        self,
        kind: str,
        name: str | None,
        container: Node,
        nodes: list[Node],
        source: bytes,
    ) -> ExecutableRegion:
        region_name = name or "top-level"
        statements = [self._statement(index, node, source) for index, node in enumerate(nodes)]
        region = ExecutableRegion(
            id=f"{kind}:{region_name}",
            kind=kind,
            name=name,
            source=_source_range(container),
            statements=statements,
        )
        region.control_flow = MatlabControlFlowBuilder(
            source, self._statement, region.source
        ).build(nodes)
        return region

    def _statement(self, index: int, node: Node, source: bytes) -> StatementIR:
        statement = StatementIR(
            index=index,
            kind=self._generic_kind(node.type),
            source=_source_range(node),
            is_compound=node.type in COMPOUND_NODES,
            parse_reliable=not node.has_error,
        )
        if node.has_error:
            statement.risks.add(Risk.PARSE_ERROR)
        self._collect(node, statement, source)
        self._assign_roles(node, statement, source)
        return statement

    @staticmethod
    def _assign_roles(node: Node, statement: StatementIR, source: bytes) -> None:
        calls = statement.calls
        expression = _text(node, source)
        if statement.is_compound:
            statement.roles.add(OperationRole.CONTROL_COMPUTATION)
        if calls & ACQUISITION_CALLS or Effect.FILE_READ in statement.effects:
            statement.roles.add(OperationRole.ACQUISITION)
        if calls & AGGREGATION_CALLS:
            statement.roles.add(OperationRole.AGGREGATION)
        if calls & TRANSFORMATION_CALLS:
            statement.roles.add(OperationRole.TRANSFORMATION)
        if calls & SHAPING_CALLS or any(token in expression for token in (".'", "(:)")):
            statement.roles.add(OperationRole.SHAPING)
        if calls & DECISION_CALLS or any(
            token in expression for token in (">=", "<=", "==", "~=", ">", "<")
        ):
            statement.roles.add(OperationRole.DECISION)
        if Effect.OUTPUT in statement.effects or Effect.FILE_WRITE in statement.effects:
            statement.roles.add(OperationRole.OUTPUT)
        if node.type == "assignment" and any(token in expression for token in ("/", "\\")):
            statement.roles.add(OperationRole.NORMALIZATION)
        if not statement.roles:
            statement.roles.add(OperationRole.UNKNOWN)

    def _collect(self, node: Node, statement: StatementIR, source: bytes) -> None:
        if node.type in COMMENT_NODES or node.type in DECLARATION_NODES:
            return
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left:
                self._collect_assignment_target(left, statement, source)
            if right:
                self._collect_expression(right, statement, source)
            return
        if node.type == "command":
            self._collect_command(node, statement, source)
            return
        if node.type == "function_call":
            self._collect_expression(node, statement, source)
            return
        if node.type in {"global_operator", "global_statement"}:
            statement.definitions |= _identifier_texts(node, source)
            statement.effects.add(Effect.WORKSPACE_WRITE)
            statement.risks.add(Risk.GLOBAL_STATE)
            return
        if node.type in {"persistent_operator", "persistent_statement"}:
            statement.definitions |= _identifier_texts(node, source)
            statement.risks.add(Risk.PERSISTENT_STATE)
            return
        if node.type in CONTROL_NODES:
            statement.control_effects.add(CONTROL_NODES[node.type])
        if node.type == "identifier":
            statement.reads.add(_text(node, source))
            return
        for child in node.named_children:
            self._collect(child, statement, source)

    def _collect_assignment_target(self, node: Node, statement: StatementIR, source: bytes) -> None:
        if node.type == "identifier":
            statement.definitions.add(_text(node, source))
            return
        if node.type == "multioutput_variable":
            statement.definitions |= _identifier_texts(node, source)
            return
        if node.type == "field_expression":
            object_node = node.child_by_field_name("object")
            if object_node:
                object_symbols = _identifier_texts(object_node, source)
                statement.mutations |= object_symbols
                statement.reads |= object_symbols
            field_node = node.child_by_field_name("field")
            if field_node and field_node.type == "indirect_access":
                statement.reads |= _identifier_texts(field_node, source)
            return
        if node.type == "function_call":
            name_node = node.child_by_field_name("name")
            if name_node and name_node.type == "identifier":
                name = _text(name_node, source)
                statement.mutations.add(name)
                statement.reads.add(name)
            for child in node.named_children:
                if not self._same_node(child, name_node):
                    self._collect_expression(child, statement, source)
            return
        identifiers = _identifier_texts(node, source)
        if identifiers:
            base = min(identifiers, key=lambda item: _text(node, source).find(item))
            statement.mutations.add(base)
            statement.reads |= identifiers

    def _collect_expression(self, node: Node, statement: StatementIR, source: bytes) -> None:
        if node.type in COMMENT_NODES:
            return
        if node.type == "handle_operator":
            statement.effects.add(Effect.FUNCTION_HANDLE)
            statement.risks.add(Risk.INDIRECT_CALL)
            statement.calls |= _identifier_texts(node, source)
            return
        if node.type == "lambda":
            statement.effects.add(Effect.FUNCTION_HANDLE)
            statement.risks.add(Risk.INDIRECT_CALL)
            arguments = next(
                (child for child in node.named_children if child.type == "arguments"), None
            )
            parameters = _identifier_texts(arguments, source) if arguments else set()
            expression = node.child_by_field_name("expression")
            if expression:
                before = set(statement.reads)
                self._collect_expression(expression, statement, source)
                statement.reads = before | (statement.reads - parameters)
            return
        if node.type == "function_call":
            name_node = node.child_by_field_name("name")
            if name_node and name_node.type == "identifier":
                name = _text(name_node, source)
                statement.calls.add(name)
                statement.effects.add(Effect.CALL_OR_INDEX)
                statement.risks.add(Risk.AMBIGUOUS_CALL_OR_INDEX)
                if name in DYNAMIC_NAMES:
                    statement.risks.add(Risk.DYNAMIC_EVALUATION)
                    if name in {"feval", "str2func"}:
                        statement.risks.add(Risk.INDIRECT_CALL)
                    if name in {"eval", "evalin", "assignin"}:
                        statement.effects |= {Effect.WORKSPACE_READ, Effect.WORKSPACE_WRITE}
                        statement.risks.add(Risk.WORKSPACE_INJECTION)
                if name in PATH_COMMANDS:
                    statement.effects.add(Effect.PATH_MUTATION)
                    statement.risks.add(Risk.PATH_DEPENDENCY)
                if name in OUTPUT_COMMANDS:
                    statement.effects.add(Effect.OUTPUT)
            for child in node.named_children:
                if not self._same_node(child, name_node):
                    self._collect_expression(child, statement, source)
            return
        if node.type == "identifier":
            statement.reads.add(_text(node, source))
            return
        for child in node.named_children:
            self._collect_expression(child, statement, source)

    def _collect_command(self, node: Node, statement: StatementIR, source: bytes) -> None:
        name_node = next(
            (child for child in node.named_children if child.type == "command_name"), None
        )
        name = _text(name_node, source).strip() if name_node else "unknown"
        statement.calls.add(name)
        arguments = [
            _text(child, source).strip("'\"")
            for child in node.named_children
            if child.type == "command_argument"
        ]
        if name == "load":
            statement.effects |= {Effect.FILE_READ, Effect.WORKSPACE_WRITE}
            statement.risks.add(Risk.WORKSPACE_INJECTION)
        elif name == "run":
            statement.effects |= {Effect.FILE_READ, Effect.WORKSPACE_READ, Effect.WORKSPACE_WRITE}
            statement.risks |= {Risk.WORKSPACE_INJECTION, Risk.EXTERNAL_DEPENDENCY}
            statement.forbid_cut_before.add("external_script_shared_workspace")
            statement.forbid_cut_after.add("external_script_shared_workspace")
        elif name == "clear":
            statement.effects.add(Effect.WORKSPACE_WRITE)
            statement.mutations |= set(arguments)
        elif name in {"who", "whos"}:
            statement.effects.add(Effect.WORKSPACE_READ)
        elif name in FILE_WRITE_COMMANDS:
            statement.effects.add(Effect.FILE_WRITE)
            statement.reads |= {arg for arg in arguments[1:] if arg.isidentifier()}
        elif name in PATH_COMMANDS:
            statement.effects.add(Effect.PATH_MUTATION)
            statement.risks.add(Risk.PATH_DEPENDENCY)
        else:
            statement.risks.add(Risk.EXTERNAL_DEPENDENCY)

    @staticmethod
    def _generic_kind(node_type: str) -> str:
        if node_type == "assignment":
            return "assignment"
        if node_type == "command":
            return "command"
        if node_type in COMPOUND_NODES:
            return "compound"
        return "statement"

    @staticmethod
    def _same_node(left: Node, right: Node | None) -> bool:
        return bool(
            right
            and left.type == right.type
            and left.start_byte == right.start_byte
            and left.end_byte == right.end_byte
        )

    @staticmethod
    def _walk(root: Node):
        stack = [root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.named_children))

    @staticmethod
    def _error_nodes(root: Node):
        for node in MatlabFrontend._walk(root):
            if node.type in {"ERROR", "MISSING"}:
                yield node
