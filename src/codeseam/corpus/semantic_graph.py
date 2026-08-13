from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SemanticTask:
    task_id: str
    role: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    internal_steps: int = 2
    control: str = "none"
    completion_tail: int = 0

    def __post_init__(self) -> None:
        if self.internal_steps < 1 or self.completion_tail < 0:
            raise ValueError("task lengths must be non-negative")


@dataclass(frozen=True, slots=True)
class SemanticTaskGraph:
    graph_id: str
    tasks: tuple[SemanticTask, ...]
    shared_config: tuple[str, ...] = ()
    factors: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tasks:
            raise ValueError("semantic graph requires at least one task")
        ids = [item.task_id for item in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task ids must be unique")

    @property
    def true_task_boundaries(self) -> tuple[int, ...]:
        total = 0
        cuts = []
        for task in self.tasks[:-1]:
            total += task.internal_steps + task.completion_tail
            cuts.append(total)
        return tuple(cuts)
