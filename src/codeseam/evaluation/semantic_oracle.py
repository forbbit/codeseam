from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from codeseam.core.flow import program_dependence_graph
from codeseam.core.ir import ExecutableRegion


class OracleStatus(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OracleObservation:
    fact_family: str
    expected: frozenset
    observed: frozenset
    confidence: float = 1.0

    @property
    def status(self) -> OracleStatus:
        if self.confidence < 1.0:
            return OracleStatus.UNKNOWN
        return OracleStatus.CORRECT if self.expected == self.observed else OracleStatus.WRONG


def evaluate_oracle(observations: Iterable[OracleObservation]) -> dict[str, object]:
    grouped: dict[str, list[OracleObservation]] = {}
    for item in observations:
        grouped.setdefault(item.fact_family, []).append(item)
    families = {name: _family_metrics(items) for name, items in sorted(grouped.items())}
    all_items = [item for items in grouped.values() for item in items]
    return {"families": families, "overall": _family_metrics(all_items)}


def region_observations(
    region: ExecutableRegion,
    *,
    expected_definitions: dict[int, set[str]] | None = None,
    expected_reads: dict[int, set[str]] | None = None,
    expected_mutations: dict[int, set[str]] | None = None,
    expected_data_edges: set[tuple[int, int, str | None]] | None = None,
    expected_control_edges: set[tuple[int, int, str | None]] | None = None,
) -> list[OracleObservation]:
    result: list[OracleObservation] = []
    for family, expected, attribute in (
        ("definitions", expected_definitions, "definitions"),
        ("reads", expected_reads, "reads"),
        ("mutations", expected_mutations, "mutations"),
    ):
        if expected is None:
            continue
        for index, values in expected.items():
            statement = region.statements[index]
            result.append(
                OracleObservation(
                    family,
                    frozenset(values),
                    frozenset(getattr(statement, attribute)),
                    float(statement.parse_reliable),
                )
            )
    if expected_data_edges is not None or expected_control_edges is not None:
        graph = program_dependence_graph(region.control_flow)
        for family, expected, kind in (
            ("data_edges", expected_data_edges, "data"),
            ("control_edges", expected_control_edges, "control"),
        ):
            if expected is None:
                continue
            observed = {
                (edge.source, edge.target, edge.symbol)
                for edge in graph.edges
                if edge.kind.value == kind
            }
            result.append(OracleObservation(family, frozenset(expected), frozenset(observed)))
    return result


def _family_metrics(items: list[OracleObservation]) -> dict[str, float | int]:
    correct = sum(item.status is OracleStatus.CORRECT for item in items)
    wrong = sum(item.status is OracleStatus.WRONG for item in items)
    unknown = sum(item.status is OracleStatus.UNKNOWN for item in items)
    known = correct + wrong
    return {
        "correct": correct,
        "wrong": wrong,
        "unknown": unknown,
        "accuracy": correct / known if known else 0.0,
        "unknown_coverage": unknown / len(items) if items else 0.0,
    }
