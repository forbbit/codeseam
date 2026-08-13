from __future__ import annotations

import random
from dataclasses import dataclass

from codeseam.corpus.semantic_graph import SemanticOperation, SemanticTask, SemanticTaskGraph


@dataclass(frozen=True, slots=True)
class RenderedMatlab:
    source: str
    true_cuts: tuple[int, ...]
    task_lines: tuple[tuple[int, int], ...]
    renderer_style: str
    semantic_program_id: str = ""
    renderer_variant_id: str = ""
    symbol_map: tuple[tuple[str, str], ...] = ()
    operation_statements: tuple[tuple[str, int], ...] = ()
    boundary_cuts: tuple[tuple[str, int], ...] = ()


def render_matlab(
    graph: SemanticTaskGraph, *, seed: int = 0, style: str = "vectorized"
) -> RenderedMatlab:
    rng = random.Random(seed)
    lines: list[str] = []
    ranges: list[tuple[int, int]] = []
    cuts: list[int] = []
    operation_statements: list[tuple[str, int]] = []
    boundary_cuts: list[tuple[str, int]] = []
    symbol_map: dict[str, str] = {}
    used_names: set[str] = set()
    operations = graph.resolved_operations()
    by_task = {task.task_id: [] for task in graph.tasks}
    for operation in operations:
        by_task.setdefault(operation.task_id, []).append(operation)
    for task_index, task in enumerate(graph.tasks):
        start = len(lines) + 1
        task_operations = by_task.get(task.task_id, [])
        rendered = [
            _render_operation(op, symbol_map, used_names, rng, style) for op in task_operations
        ]
        block, offsets = _wrap_control(task, rendered, symbol_map, used_names, rng, style)
        base = len(lines)
        lines.extend(block)
        for operation, offset in zip(task_operations, offsets, strict=True):
            operation_statements.append((operation.op_id, base + offset))
        ranges.append((start, len(lines)))
        if task_index < len(graph.tasks) - 1:
            cut = len(lines)
            cuts.append(cut)
            boundary_id = (
                graph.boundaries[task_index].boundary_id
                if task_index < len(graph.boundaries)
                else f"{task.task_id}->{graph.tasks[task_index + 1].task_id}"
            )
            boundary_cuts.append((boundary_id, cut))
    return RenderedMatlab(
        "\n".join(lines) + "\n",
        tuple(cuts),
        tuple(ranges),
        style,
        graph.semantic_program_id,
        f"{style}:{seed}",
        tuple(sorted(symbol_map.items())),
        tuple(operation_statements),
        tuple(boundary_cuts),
    )


def counterfactual_pair(
    graph: SemanticTaskGraph, *, seed: int = 0
) -> tuple[RenderedMatlab, RenderedMatlab]:
    return render_matlab(graph, seed=seed, style="descriptive"), render_matlab(
        graph, seed=seed + 1, style="reused"
    )


def _wrap_control(task: SemanticTask, statements: list[str], names, used, rng, style):
    if task.control == "none":
        return statements, list(range(1, len(statements) + 1))
    condition_key = task.inputs[0] if task.inputs else f"{task.task_id}_condition"
    condition = _name(condition_key, names, used, rng, style)
    if task.control == "for":
        header = "for loop_index = 1:2"
    elif task.control == "while":
        header = f"while any({condition}(:))"
    else:
        header = f"if any({condition}(:))"
    body = [header] + [f"    {line}" for line in statements]
    offsets = list(range(2, len(statements) + 2))
    if task.control == "ifelse":
        body.extend(["else", "    fallback_value = 0;"])
    body.append("end")
    return body, offsets


def _render_operation(op: SemanticOperation, names, used, rng, style: str) -> str:
    reads = [_name(item, names, used, rng, style) for item in op.reads]
    outputs = [_name(item, names, used, rng, style) for item in op.definitions]
    source = reads[0] if reads else "randn(16, 1)"
    expression = {
        "acquisition": "randn(16, 1)",
        "transformation": f"fft({source})",
        "aggregation": f"mean({source})",
        "normalization": f"{source} / (norm({source}) + eps)",
        "shaping": f"reshape({source}, [], 1)",
        "decision": f"{source} > median({source})",
        "output": source,
    }.get(op.role.lower(), f"{source} + 1")
    if op.calls:
        expression = f"{op.calls[0]}({source})"
    if op.role.lower() == "output" and not outputs:
        return f"disp({expression});"
    output = outputs[0] if outputs else _name(op.op_id, names, used, rng, style)
    return f"{output} = {expression};"


def _name(key: str, names: dict[str, str], used: set[str], rng: random.Random, style: str) -> str:
    if key in names:
        return names[key]
    if style == "descriptive":
        stem = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in key) + "_value"
    elif style == "reused":
        # Reuse a vocabulary pattern, never an identifier: alpha-renaming must
        # remain injective or it changes defs/reads and therefore semantics.
        stem = f"state_{len(names) + 1}"
    else:
        stem = f"v{rng.randrange(1000):03d}"
    value = stem
    suffix = 2
    while value in used:
        value, suffix = f"{stem}_{suffix}", suffix + 1
    names[key] = value
    used.add(value)
    return value
