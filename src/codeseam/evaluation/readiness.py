from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True, slots=True)
class GateResult:
    gate: str
    status: GateStatus
    reasons: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    overall: str
    gates: tuple[GateResult, ...]
    policy_version: str = "training-readiness-v2"

    def to_dict(self):
        return asdict(self)


def evaluate_training_readiness(evidence: Mapping[str, Mapping[str, object]]) -> ReadinessReport:
    results = []
    for gate in "ABCDEFGH":
        item = evidence.get(gate)
        if item is None:
            results.append(
                GateResult(gate, GateStatus.NOT_EVALUATED, ("required evidence is missing",))
            )
            continue
        declared = item.get("status")
        if declared == GateStatus.NOT_EVALUATED.value:
            results.append(
                GateResult(
                    gate,
                    GateStatus.NOT_EVALUATED,
                    tuple(str(x) for x in item.get("reasons", ())),
                    tuple(item.get("artifact_refs", ())),
                )
            )
            continue
        passed = bool(item.get("pass", False))
        reasons = tuple(str(x) for x in item.get("reasons", ()))
        results.append(
            GateResult(
                gate,
                GateStatus.PASS if passed else GateStatus.FAIL,
                reasons,
                tuple(item.get("artifact_refs", ())),
            )
        )
    ready = all(item.status is GateStatus.PASS for item in results)
    return ReadinessReport(f"READY FOR FORMAL TRAINING: {'YES' if ready else 'NO'}", tuple(results))
