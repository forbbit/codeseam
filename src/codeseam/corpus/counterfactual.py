from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product

from codeseam.corpus.semantic_graph import (
    SemanticBoundaryTruth,
    SemanticOperation,
    SemanticTask,
    SemanticTaskGraph,
)

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
REQUIRED_FACTOR_PAIRS = (
    ("interface", "dependency"),
    ("interface", "role"),
    ("dependency", "completion"),
    ("role", "completion"),
    ("control", "dependency"),
    ("control", "completion"),
)


@dataclass(frozen=True, slots=True)
class CounterfactualCase:
    pair_id: str
    family: str
    semantic_polarity: str
    target_boundary_id: str
    target_boundary_truth: SemanticBoundaryTruth
    counterfactual_intent: str
    graph: SemanticTaskGraph
    requested_factors: tuple[tuple[str, str], ...]


def generate_counterfactual_suite(base: SemanticTaskGraph) -> tuple[CounterfactualCase, ...]:
    del base  # only the caller-provided graph id formerly varied; truth is explicit below
    cases = []
    for family in COUNTERFACTUAL_FAMILIES:
        for label, polarity in product(("cut", "no_cut"), ("low", "high")):
            graph = semantic_factor_graph(
                f"cf:{family}:{label}:{polarity}", {family: polarity}, label
            )
            truth = graph.boundaries[0]
            cases.append(
                CounterfactualCase(
                    f"cf:{family}:{label}",
                    family,
                    polarity,
                    truth.boundary_id,
                    truth,
                    f"observe {family}={polarity} at an explicit semantic {label} boundary",
                    graph,
                    ((family, polarity),),
                )
            )
    return tuple(cases)


def generate_pairwise_suite() -> tuple[CounterfactualCase, ...]:
    cases = []
    for left, right in REQUIRED_FACTOR_PAIRS:
        for left_value, right_value in product(("low", "high"), repeat=2):
            factors = {left: left_value, right: right_value}
            graph = semantic_factor_graph(
                f"pair:{left}:{right}:{left_value}:{right_value}", factors, "cut"
            )
            truth = graph.boundaries[0]
            cases.append(
                CounterfactualCase(
                    f"pair:{left}:{right}",
                    f"{left}×{right}",
                    f"{left_value}×{right_value}",
                    truth.boundary_id,
                    truth,
                    "pairwise semantic-factor coverage",
                    graph,
                    tuple(sorted(factors.items())),
                )
            )
    return tuple(cases)


def semantic_factor_graph(
    graph_id: str, requested: dict[str, str], boundary_label: str
) -> SemanticTaskGraph:
    factors = {family: "low" for family in COUNTERFACTUAL_FAMILIES}
    factors.update(requested)
    same_module = boundary_label == "no_cut"
    left_count = 1 if factors["module_size"] == "low" else 5
    completion = 0
    control = "none" if factors["control"] == "low" else "ifelse"
    right_role = "aggregation" if factors["role"] == "high" else "transformation"
    left_role = (
        "aggregation"
        if requested.get("role") == "low" and requested.get("completion") == "high"
        else "transformation"
    )
    left = SemanticTask(
        "producer",
        left_role,
        outputs=("primary",),
        internal_steps=left_count,
        control=control,
        completion_tail=completion,
        module_id="combined" if same_module else "producer_module",
    )
    right = SemanticTask(
        "consumer",
        right_role,
        inputs=("primary",),
        internal_steps=4,
        module_id="combined" if same_module else "consumer_module",
    )
    operations: list[SemanticOperation] = []
    produced = []
    for index in range(left_count):
        symbol = "primary" if index == left_count - 1 else f"intermediate_{index + 1}"
        reads = (produced[-1],) if produced else ("seed_input",)
        operations.append(
            SemanticOperation(
                f"producer.op{index + 1}",
                "producer",
                left_role,
                definitions=(symbol,),
                reads=reads,
            )
        )
        produced.append(symbol)
    if factors["interface"] == "high":
        for name in ("interface_a", "interface_b"):
            operations.append(
                SemanticOperation(
                    f"producer.{name}", "producer", "transformation", definitions=(name,)
                )
            )
            produced.append(name)
        left = replace(left, internal_steps=left.internal_steps + 2)
    for index in range(completion):
        source = "primary" if index == 0 else f"completion_{index}"
        operations.append(
            SemanticOperation(
                f"producer.completion{index + 1}",
                "producer",
                ("aggregation", "normalization", "shaping")[min(index, 2)],
                definitions=(f"completion_{index + 1}",),
                reads=(source,),
            )
        )
    interface_reads = (
        ("primary", "interface_a", "interface_b")
        if factors["interface"] == "high"
        else ("primary",)
    )
    for index in range(4):
        if factors["dependency"] == "high":
            reads = tuple(produced[-3:])
        elif factors["long_range"] == "high" and index == 3:
            reads = ("primary", "shared_config")
        elif index == 0:
            reads = interface_reads
        else:
            reads = (f"consumer_{index}",)
        operation_role = right_role
        if factors["completion"] == "high":
            if requested.get("role") == "high":
                operation_role = ("aggregation", "normalization", "shaping", "aggregation")[index]
            elif "role" not in requested or requested.get("role") == "low":
                operation_role = ("aggregation", "aggregation", "normalization", "shaping")[index]
            reads = ("primary",) if index == 0 else (f"consumer_{index}",)
        if factors["dependency"] == "high":
            reads = tuple(produced[-3:])
        output = "primary" if factors["vocabulary"] == "high" else f"consumer_{index + 1}"
        operations.append(
            SemanticOperation(
                f"consumer.op{index + 1}",
                "consumer",
                operation_role,
                definitions=(output,),
                reads=reads,
            )
        )
    truth = SemanticBoundaryTruth(
        "producer->consumer",
        "producer",
        "consumer",
        boundary_label,
        tuple(f"producer.completion{index + 1}" for index in range(completion)),
    )
    return SemanticTaskGraph(
        graph_id,
        (left, right),
        shared_config=("shared_config",),
        factors=factors,
        operations=tuple(operations),
        boundaries=(truth,),
    )
