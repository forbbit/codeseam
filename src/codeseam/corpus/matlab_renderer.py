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
    candidate_labels: tuple[tuple[int, str], ...] = ()
    ambiguous_boundaries: tuple[int, ...] = ()
    renderer_trace_id: str = ""


def render_matlab(
    graph: SemanticTaskGraph, *, seed: int = 0, style: str = "vectorized"
) -> RenderedMatlab:
    rng = random.Random(seed)
    lines: list[str] = []
    ranges: list[tuple[int, int]] = []
    cuts: list[int] = []
    operation_statements: list[tuple[str, int]] = []
    boundary_cuts: list[tuple[str, int]] = []
    candidate_labels: dict[int, str] = {}
    symbol_map: dict[str, str] = {}
    used_names: set[str] = set()
    statement_total = 0
    operations = graph.resolved_operations()
    by_task = {task.task_id: [] for task in graph.tasks}
    for operation in operations:
        by_task.setdefault(operation.task_id, []).append(operation)
    for task_index, task in enumerate(graph.tasks):
        start = len(lines) + 1
        task_operations = by_task.get(task.task_id, [])
        main_operations = [op for op in task_operations if ".completion" not in op.op_id]
        completion_operations = [op for op in task_operations if ".completion" in op.op_id]
        rendered_main = [
            _render_operation(op, symbol_map, used_names, rng, style) for op in main_operations
        ]
        block, offsets = _wrap_control(task, rendered_main, symbol_map, used_names, rng, style)
        base = len(lines)
        lines.extend(block)
        for operation, offset in zip(main_operations, offsets, strict=True):
            operation_statements.append((operation.op_id, base + offset))
        statement_total += 1 if task.control != "none" else len(main_operations)
        for operation in completion_operations:
            lines.append(_render_operation(operation, symbol_map, used_names, rng, style))
            operation_statements.append((operation.op_id, len(lines)))
            statement_total += 1
        ranges.append((start, len(lines)))
        if task_index < len(graph.tasks) - 1:
            cut = statement_total
            truth = graph.boundary_truth(task.task_id, graph.tasks[task_index + 1].task_id)
            if truth.label == "cut":
                cuts.append(cut)
            candidate_labels[cut] = truth.label
            boundary_id = truth.boundary_id
            boundary_cuts.append((boundary_id, cut))
    for candidate in range(1, statement_total):
        candidate_labels.setdefault(candidate, "no_cut")
    trace_payload = "|".join(
        [graph.semantic_program_id, style, str(seed)]
        + [f"{op}:{statement}" for op, statement in operation_statements]
        + [f"{boundary}:{cut}" for boundary, cut in boundary_cuts]
    )
    import hashlib

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
        tuple(sorted(candidate_labels.items())),
        tuple(index for index, label in sorted(candidate_labels.items()) if label == "ambiguous"),
        hashlib.sha256(trace_payload.encode()).hexdigest(),
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
    elif task.control == "nested":
        body = (
            [header, f"    if all({condition}(:))"]
            + [f"        {line}" for line in statements]
            + ["    end"]
        )
        offsets = list(range(3, len(statements) + 3))
    elif task.control == "loop_branch":
        body = (
            ["for loop_index = 1:2", f"    if any({condition}(:))"]
            + [f"        {line}" for line in statements]
            + ["    end"]
        )
        offsets = list(range(3, len(statements) + 3))
    body.append("end")
    return body, offsets


def _render_operation(op: SemanticOperation, names, used, rng, style: str) -> str:
    reads = [_name(item, names, used, rng, style) for item in op.reads]
    outputs = [_name(item, names, used, rng, style) for item in op.definitions]
    source = reads[0] if reads else "randn(16, 1)"
    all_inputs = source if len(reads) < 2 else " + ".join(f"({item})" for item in reads)
    expression = {
        "acquisition": "randn(16, 1)",
        "transformation": f"fft({all_inputs})",
        "aggregation": f"mean({all_inputs})",
        "normalization": f"({all_inputs}) / (norm({all_inputs}) + eps)",
        "shaping": f"reshape({all_inputs}, [], 1)",
        "decision": f"({all_inputs}) > median({all_inputs})",
        "output": all_inputs,
    }.get(op.role.lower(), f"{all_inputs} + 1")
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
