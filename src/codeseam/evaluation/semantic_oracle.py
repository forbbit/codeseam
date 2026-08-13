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
    disposition: str = "auto"
    reason_codes: tuple[str, ...] = ()
    unit_id: str = ""

    @property
    def status(self) -> OracleStatus:
        unknown = self.disposition == "unknown" or (
            self.disposition == "auto" and self.confidence < 1.0
        )
        if unknown:
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
    expected_definitions=None,
    expected_reads=None,
    expected_mutations=None,
    expected_data_edges=None,
    expected_control_edges=None,
) -> list[OracleObservation]:
    result = []
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
                    unit_id=f"{region.id}:{index}",
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
            result.append(
                OracleObservation(
                    family, frozenset(expected), frozenset(observed), unit_id=region.id
                )
            )
    return result


def _family_metrics(items):
    correct = sum(item.status is OracleStatus.CORRECT for item in items)
    wrong = sum(item.status is OracleStatus.WRONG for item in items)
    unknown = sum(item.status is OracleStatus.UNKNOWN for item in items)
    known = [item for item in items if item.status is not OracleStatus.UNKNOWN]
    tp = fp = fn = 0
    for item in known:
        tp += len(item.expected & item.observed)
        fp += len(item.observed - item.expected)
        fn += len(item.expected - item.observed)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "correct": correct,
        "wrong": wrong,
        "unknown": unknown,
        "accuracy": correct / (correct + wrong) if correct + wrong else 0.0,
        "unknown_coverage": unknown / len(items) if items else 0.0,
        "unknown_expected_positive_atoms": sum(
            len(item.expected) for item in items if item.status is OracleStatus.UNKNOWN
        ),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }
