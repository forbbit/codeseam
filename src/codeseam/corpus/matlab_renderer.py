from __future__ import annotations

import random
from dataclasses import dataclass

from codeseam.corpus.semantic_graph import SemanticTask, SemanticTaskGraph


@dataclass(frozen=True, slots=True)
class RenderedMatlab:
    source: str
    true_cuts: tuple[int, ...]
    task_lines: tuple[tuple[int, int], ...]
    renderer_style: str


def render_matlab(
    graph: SemanticTaskGraph, *, seed: int = 0, style: str = "vectorized"
) -> RenderedMatlab:
    rng = random.Random(seed)
    lines: list[str] = []
    ranges = []
    cuts = []
    symbol_map: dict[str, str] = {}
    for task_index, task in enumerate(graph.tasks):
        start = len(lines) + 1
        for step in range(task.internal_steps):
            lines.append(_render_step(task, step, symbol_map, rng, style))
        for tail in range(task.completion_tail):
            source = _name(task.outputs[0] if task.outputs else task.task_id, symbol_map, rng, style)
            target = f"{source}_final{tail + 1}"
            lines.append(f"{target} = reshape({source}, [], 1);")
            symbol_map[task.outputs[0] if task.outputs else task.task_id] = target
        ranges.append((start, len(lines)))
        if task_index < len(graph.tasks) - 1:
            cuts.append(len(lines))
    return RenderedMatlab("\n".join(lines) + "\n", tuple(cuts), tuple(ranges), style)


def counterfactual_pair(graph: SemanticTaskGraph, *, seed: int = 0) -> tuple[RenderedMatlab, RenderedMatlab]:
    """Same semantic labels, deliberately different vocabulary fingerprints."""
    return (
        render_matlab(graph, seed=seed, style="descriptive"),
        render_matlab(graph, seed=seed + 1, style="reused"),
    )


def _render_step(task: SemanticTask, step: int, names, rng, style: str) -> str:
    inputs = [_name(name, names, rng, style) for name in task.inputs]
    output_key = task.outputs[min(step, len(task.outputs) - 1)] if task.outputs else task.task_id
    output = _name(output_key, names, rng, style)
    source = inputs[0] if inputs else "randn(16, 1)"
    calls = {
        "acquisition": "randn(16, 1)",
        "transformation": f"fft({source})",
        "aggregation": f"mean({source})",
        "normalization": f"{source} / (norm({source}) + eps)",
        "shaping": f"reshape({source}, [], 1)",
        "decision": f"{source} > median({source})",
        "output": source,
    }
    expression = calls.get(task.role.lower(), f"{source} + {step + 1}")
    if task.role.lower() == "output":
        return f"disp({expression});"
    if step:
        expression = f"{output} + {step}"
    return f"{output} = {expression};"


def _name(key: str, names: dict[str, str], rng: random.Random, style: str) -> str:
    if key in names:
        return names[key]
    if style == "reused":
        value = "state"
    elif style == "descriptive":
        value = f"{key}_value"
    else:
        value = f"v{rng.randrange(1000):03d}"
    names[key] = value
    return value
