from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Effect(StrEnum):
    CALL_OR_INDEX = "call_or_index"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FUNCTION_HANDLE = "function_handle"
    OUTPUT = "output"
    PATH_MUTATION = "path_mutation"
    WORKSPACE_READ = "workspace_read"
    WORKSPACE_WRITE = "workspace_write"
    UNKNOWN = "unknown"


class ControlEffect(StrEnum):
    BREAK = "break"
    CONTINUE = "continue"
    RETURN = "return"
    THROW = "throw"


class OperationRole(StrEnum):
    ACQUISITION = "acquisition"
    CONTROL_COMPUTATION = "control_computation"
    AGGREGATION = "aggregation"
    NORMALIZATION = "normalization"
    TRANSFORMATION = "transformation"
    SHAPING = "shaping"
    DECISION = "decision"
    OUTPUT = "output"
    UNKNOWN = "unknown"


class Risk(StrEnum):
    AMBIGUOUS_CALL_OR_INDEX = "ambiguous_call_or_index"
    DYNAMIC_EVALUATION = "dynamic_evaluation"
    EXTERNAL_DEPENDENCY = "external_dependency"
    GLOBAL_STATE = "global_state"
    INDIRECT_CALL = "indirect_call"
    PARSE_ERROR = "parse_error"
    PATH_DEPENDENCY = "path_dependency"
    PERSISTENT_STATE = "persistent_state"
    WORKSPACE_INJECTION = "workspace_injection"


@dataclass(frozen=True, slots=True)
class SourceRange:
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int


class ControlFlowEdgeKind(StrEnum):
    NEXT = "next"
    TRUE = "true"
    FALSE = "false"
    BACK = "back"
    BREAK = "break"
    CONTINUE = "continue"
    RETURN = "return"


@dataclass(slots=True)
class FlowNode:
    id: int
    kind: str
    source: SourceRange
    top_level_statement: int
    definitions: set[str] = field(default_factory=set)
    reads: set[str] = field(default_factory=set)
    mutations: set[str] = field(default_factory=set)
    roles: set[OperationRole] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    effects: set[Effect] = field(default_factory=set)
    risks: set[Risk] = field(default_factory=set)
    synthetic: bool = False


@dataclass(frozen=True, slots=True)
class ControlFlowEdge:
    source: int
    target: int
    kind: ControlFlowEdgeKind = ControlFlowEdgeKind.NEXT


@dataclass(slots=True)
class ControlFlowGraph:
    nodes: list[FlowNode]
    edges: list[ControlFlowEdge]
    entry: int
    exit: int


@dataclass(slots=True)
class StatementIR:
    index: int
    kind: str
    source: SourceRange
    definitions: set[str] = field(default_factory=set)
    reads: set[str] = field(default_factory=set)
    mutations: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    resolved_calls: set[str] = field(default_factory=set)
    resolved_indexes: set[str] = field(default_factory=set)
    unresolved_calls: set[str] = field(default_factory=set)
    call_resolution_available: bool = False
    effects: set[Effect] = field(default_factory=set)
    control_effects: set[ControlEffect] = field(default_factory=set)
    roles: set[OperationRole] = field(default_factory=set)
    risks: set[Risk] = field(default_factory=set)
    forbid_cut_before: set[str] = field(default_factory=set)
    forbid_cut_after: set[str] = field(default_factory=set)
    is_compound: bool = False
    parse_reliable: bool = True


@dataclass(slots=True)
class ExecutableRegion:
    id: str
    kind: str
    name: str | None
    source: SourceRange
    statements: list[StatementIR]
    parameters: set[str] = field(default_factory=set)
    declared_outputs: set[str] = field(default_factory=set)
    control_flow: ControlFlowGraph | None = None
    dependence_cache: list[ProgramDependenceEdge] | None = field(
        default=None, repr=False, compare=False
    )


@dataclass(slots=True)
class ProgramIR:
    language: str
    path: Path
    source_hash: str
    regions: list[ExecutableRegion]
    diagnostics: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DependencyEdge:
    source_statement: int
    target_statement: int
    symbol: str


class DependenceKind(StrEnum):
    DATA = "data"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class ProgramDependenceEdge:
    source: int
    target: int
    kind: DependenceKind
    symbol: str | None = None


@dataclass(slots=True)
class ProgramDependenceGraph:
    node_ids: list[int]
    edges: list[ProgramDependenceEdge]


@dataclass(slots=True)
class BoundaryAnalysis:
    region_id: str
    boundary: int
    after_line: int
    before_line: int
    score: float
    features: dict[str, float]
    raw_features: dict[str, float]
    normalization_version: str
    dead_symbols: list[str]
    born_symbols: list[str]
    cross_symbols: list[str]
    cross_edges: list[DependencyEdge]
    constraints: list[str]
    risks: list[str]
    completion_roles: list[str] = field(default_factory=list)
    completion_symbols: list[str] = field(default_factory=list)
    left_module_quality: ModuleQuality | None = None
    right_module_quality: ModuleQuality | None = None
    local_peak_candidate: bool = False
    prominence: float = 0.0
    rejection_reasons: list[str] = field(default_factory=list)
    recommended: bool = False


@dataclass(slots=True)
class ModuleQuality:
    start_statement: int
    end_statement: int
    start_line: int
    end_line: int
    score: float
    features: dict[str, float]
    raw_features: dict[str, float]
    inputs: list[str]
    outputs: list[str]


@dataclass(slots=True)
class AnalysisResult:
    program: ProgramIR
    boundaries: list[BoundaryAnalysis]

    def to_dict(self) -> dict[str, Any]:
        def normalize(value: Any) -> Any:
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, (set, frozenset)):
                return sorted(normalize(item) for item in value)
            if isinstance(value, StrEnum):
                return value.value
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        result = normalize(asdict(self))
        # CFG/PDG are internal analysis infrastructure for now. Keeping the graph out of
        # existing reports avoids a large, premature public schema change.
        for region in result["program"]["regions"]:
            region.pop("control_flow", None)
            region.pop("dependence_cache", None)
        return result
