from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class SemanticOperation:
    """Renderer-independent operation truth.

    ``op_id`` and symbol names are stable semantic identifiers, not source
    locations.  An oracle can therefore be compiled without parsing MATLAB.
    """

    op_id: str
    task_id: str
    role: str
    definitions: tuple[str, ...] = ()
    reads: tuple[str, ...] = ()
    mutations: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticEdge:
    source_op: str
    target_op: str
    kind: str
    symbol_or_branch: str = ""
    loop_carried: bool = False


@dataclass(frozen=True, slots=True)
class SemanticBoundaryTruth:
    boundary_id: str
    left_task_id: str
    right_task_id: str
    label: str = "cut"
    completion_chain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.label not in {"cut", "no_cut", "ambiguous"}:
            raise ValueError(f"unsupported boundary label: {self.label}")


@dataclass(frozen=True, slots=True)
class SemanticTask:
    task_id: str
    role: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    internal_steps: int = 2
    control: str = "none"
    completion_tail: int = 0
    module_id: str = ""

    def __post_init__(self) -> None:
        if self.internal_steps < 1 or self.completion_tail < 0:
            raise ValueError("task lengths must be non-negative")
        if self.control not in {"none", "if", "ifelse", "for", "while", "nested", "loop_branch"}:
            raise ValueError(f"unsupported control structure: {self.control}")


@dataclass(frozen=True, slots=True)
class SemanticTaskGraph:
    graph_id: str
    tasks: tuple[SemanticTask, ...]
    shared_config: tuple[str, ...] = ()
    factors: dict[str, str] = field(default_factory=dict)
    operations: tuple[SemanticOperation, ...] = ()
    edges: tuple[SemanticEdge, ...] = ()
    boundaries: tuple[SemanticBoundaryTruth, ...] = ()

    def __post_init__(self) -> None:
        if not self.tasks:
            raise ValueError("semantic graph requires at least one task")
        ids = [item.task_id for item in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task ids must be unique")
        op_ids = {item.op_id for item in self.operations}
        if len(op_ids) != len(self.operations):
            raise ValueError("operation ids must be unique")
        if any(edge.source_op not in op_ids or edge.target_op not in op_ids for edge in self.edges):
            raise ValueError("semantic edge references an unknown operation")
        task_ids = set(ids)
        if any(
            boundary.left_task_id not in task_ids or boundary.right_task_id not in task_ids
            for boundary in self.boundaries
        ):
            raise ValueError("semantic boundary references an unknown task")
        pairs = [(item.left_task_id, item.right_task_id) for item in self.boundaries]
        if len(pairs) != len(set(pairs)):
            raise ValueError("semantic task pair may have only one boundary truth")

    @property
    def true_task_boundaries(self) -> tuple[int, ...]:
        """Legacy logical cut ordinals; renderers project stable IDs to statements."""
        total = 0
        cuts = []
        truth = {(item.left_task_id, item.right_task_id): item for item in self.boundaries}
        for index, task in enumerate(self.tasks[:-1]):
            total += task.internal_steps + task.completion_tail
            boundary = truth.get((task.task_id, self.tasks[index + 1].task_id))
            if boundary is None or boundary.label == "cut":
                cuts.append(total)
        return tuple(cuts)

    def boundary_truth(self, left_task_id: str, right_task_id: str) -> SemanticBoundaryTruth:
        for item in self.boundaries:
            if (item.left_task_id, item.right_task_id) == (left_task_id, right_task_id):
                return item
        left = next(task for task in self.tasks if task.task_id == left_task_id)
        right = next(task for task in self.tasks if task.task_id == right_task_id)
        left_module = left.module_id or left.task_id
        right_module = right.module_id or right.task_id
        return SemanticBoundaryTruth(
            f"{left_task_id}->{right_task_id}",
            left_task_id,
            right_task_id,
            "no_cut" if left_module == right_module else "cut",
        )

    @property
    def semantic_program_id(self) -> str:
        payload = asdict(self)
        payload.pop("graph_id", None)
        payload.pop("factors", None)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def resolved_operations(self) -> tuple[SemanticOperation, ...]:
        if self.operations:
            return self.operations
        result: list[SemanticOperation] = []
        for task in self.tasks:
            prior = task.inputs
            for index in range(task.internal_steps):
                output = (
                    task.outputs[min(index, len(task.outputs) - 1)]
                    if task.outputs
                    else task.task_id
                )
                result.append(
                    SemanticOperation(
                        f"{task.task_id}.op{index + 1}",
                        task.task_id,
                        task.role,
                        definitions=(output,),
                        reads=prior,
                    )
                )
                prior = (output,)
            for index in range(task.completion_tail):
                result.append(
                    SemanticOperation(
                        f"{task.task_id}.completion{index + 1}",
                        task.task_id,
                        "shaping",
                        definitions=(f"{task.task_id}.final{index + 1}",),
                        reads=prior,
                    )
                )
                prior = (f"{task.task_id}.final{index + 1}",)
        return tuple(result)
