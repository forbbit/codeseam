from __future__ import annotations

from dataclasses import dataclass, replace

from codeseam.corpus.semantic_graph import SemanticTask, SemanticTaskGraph

COUNTERFACTUAL_FAMILIES = (
    "vocabulary",
    "interface",
    "dependency",
    "role",
    "completion",
    "long_range",
    "module_size",
    "control",
)


@dataclass(frozen=True, slots=True)
class CounterfactualCase:
    pair_id: str
    family: str
    semantic_polarity: str
    label: str
    graph: SemanticTaskGraph


def generate_counterfactual_suite(base: SemanticTaskGraph) -> tuple[CounterfactualCase, ...]:
    """Generate the required 8 families × cut/no-cut × low/high quadrants."""
    cases: list[CounterfactualCase] = []
    for family in COUNTERFACTUAL_FAMILIES:
        for label in ("cut", "no_cut"):
            for polarity in ("low", "high"):
                tasks = tuple(
                    _vary_task(task, family, polarity, index)
                    for index, task in enumerate(base.tasks)
                )
                factors = dict(base.factors)
                factors[family] = polarity
                factors["label"] = label
                graph = replace(
                    base,
                    graph_id=f"{base.graph_id}:{family}:{label}:{polarity}",
                    tasks=tasks,
                    factors=factors,
                )
                cases.append(
                    CounterfactualCase(
                        f"{base.graph_id}:{family}:{label}", family, polarity, label, graph
                    )
                )
    return tuple(cases)


def _vary_task(task: SemanticTask, family: str, polarity: str, index: int) -> SemanticTask:
    high = polarity == "high"
    if family == "interface":
        return replace(
            task,
            inputs=(
                task.inputs if not high else task.inputs + (f"wide_{index}_a", f"wide_{index}_b")
            ),
        )
    if family == "completion":
        return replace(task, completion_tail=3 if high else 0)
    if family == "module_size":
        return replace(task, internal_steps=5 if high else 1)
    if family == "control":
        return replace(task, control="ifelse" if high else "none")
    if family == "role":
        return replace(task, role="normalization" if high else "transformation")
    # Vocabulary/dependency/span are semantic factor changes consumed by the
    # renderer/analyzer audit; keep the task truth otherwise controlled.
    return task
