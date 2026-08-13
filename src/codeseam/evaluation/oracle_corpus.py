from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from codeseam.evaluation.semantic_oracle import (
    OracleObservation,
    evaluate_oracle,
    region_observations,
)
from codeseam.languages.matlab import MatlabFrontend


@dataclass(frozen=True, slots=True)
class HandOracleCase:
    case_id: str
    source: bytes
    expected_definitions: dict[int, set[str]]
    expected_reads: dict[int, set[str]]
    expected_mutations: dict[int, set[str]]
    expected_calls: dict[int, set[str]] | None = None
    expected_roles: dict[int, set[str]] | None = None
    expected_effects: dict[int, set[str]] | None = None


def hand_oracle_cases() -> tuple[HandOracleCase, ...]:
    """Independent, human-authored facts; no renderer or analyzer derives truth."""
    return (
        HandOracleCase(
            "assignment",
            b"x = 1;\ny = x + 1;\n",
            {0: {"x"}, 1: {"y"}},
            {0: set(), 1: {"x"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "overwrite",
            b"x = 1;\nx = x + 1;\n",
            {0: {"x"}, 1: {"x"}},
            {0: set(), 1: {"x"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "index_mutation",
            b"x = zeros(2);\nx(1) = 2;\n",
            {0: {"x"}, 1: set()},
            {0: set(), 1: set()},
            {0: set(), 1: {"x"}},
        ),
        HandOracleCase(
            "field_mutation",
            b"s.a = 1;\ny = s.a;\n",
            {0: set(), 1: {"y"}},
            {0: set(), 1: {"s"}},
            {0: {"s"}, 1: set()},
        ),
        HandOracleCase(
            "builtin_call",
            b"x = randn(2);\ny = mean(x);\n",
            {0: {"x"}, 1: {"y"}},
            {0: set(), 1: {"x"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "if_condition",
            b"flag = true;\nif flag\n x = 1;\nend\n",
            {0: {"flag"}, 1: {"x"}},
            {0: set(), 1: {"flag"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "while_condition",
            b"x = 0;\nwhile x < 2\n x = x + 1;\nend\n",
            {0: {"x"}, 1: {"x"}},
            {0: set(), 1: {"x"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "for_loop",
            b"s = 0;\nfor i = 1:2\n s = s + i;\nend\n",
            {0: {"s"}, 1: {"i", "s"}},
            {0: set(), 1: {"s"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "aggregation",
            b"x = randn(2);\ny = sum(x);\n",
            {0: {"x"}, 1: {"y"}},
            {0: set(), 1: {"x"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "normalization",
            b"x = randn(2);\ny = x / norm(x);\n",
            {0: {"x"}, 1: {"y"}},
            {0: set(), 1: {"x"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "shaping",
            b"x = randn(2);\ny = reshape(x,[],1);\n",
            {0: {"x"}, 1: {"y"}},
            {0: set(), 1: {"x"}},
            {0: set(), 1: set()},
        ),
        HandOracleCase(
            "external_call", b"x = project_worker(input);\n", {0: {"x"}}, {0: {"input"}}, {0: set()}
        ),
    )


def _enrich_oracle_cases(cases: tuple[HandOracleCase, ...]) -> tuple[HandOracleCase, ...]:
    """Attach independently specified call/role/effect truth to selected cases."""
    truth = {
        "builtin_call": (
            {0: {"randn"}, 1: {"mean"}},
            {0: {"acquisition"}, 1: {"aggregation"}},
            {0: {"call_or_index"}, 1: {"call_or_index"}},
        ),
        "aggregation": (
            {0: {"randn"}, 1: {"sum"}},
            {0: {"acquisition"}, 1: {"aggregation"}},
            {0: {"call_or_index"}, 1: {"call_or_index"}},
        ),
        "normalization": (
            {0: {"randn"}, 1: {"norm"}},
            {0: {"acquisition"}, 1: {"aggregation", "normalization"}},
            {0: {"call_or_index"}, 1: {"call_or_index"}},
        ),
        "shaping": (
            {0: {"randn"}, 1: {"reshape"}},
            {0: {"acquisition"}, 1: {"shaping"}},
            {0: {"call_or_index"}, 1: {"call_or_index"}},
        ),
        "external_call": ({0: {"project_worker"}}, {0: {"unknown"}}, {0: {"call_or_index"}}),
    }
    return tuple(
        HandOracleCase(
            case.case_id,
            case.source,
            case.expected_definitions,
            case.expected_reads,
            case.expected_mutations,
            *(truth.get(case.case_id, (None, None, None))),
        )
        for case in cases
    )


def run_hand_oracle() -> dict[str, object]:
    frontend = MatlabFrontend()
    observations: list[OracleObservation] = []
    case_results = {}
    for case in _enrich_oracle_cases(hand_oracle_cases()):
        program = frontend.analyze_source(case.source, f"{case.case_id}.m")
        region = program.regions[0]
        items = region_observations(
            region,
            expected_definitions=case.expected_definitions,
            expected_reads=case.expected_reads,
            expected_mutations=case.expected_mutations,
        )
        for family, expected, attribute in (
            ("calls", case.expected_calls, "calls"),
            ("roles", case.expected_roles, "roles"),
            ("effects", case.expected_effects, "effects"),
        ):
            if expected is None:
                continue
            for index, values in expected.items():
                observed = {
                    item.value if hasattr(item, "value") else item
                    for item in getattr(region.statements[index], attribute)
                }
                items.append(OracleObservation(family, frozenset(values), frozenset(observed)))
        observations.extend(items)
        case_results[case.case_id] = evaluate_oracle(items)["overall"]
    report = evaluate_oracle(observations)
    report["cases"] = case_results
    report["case_count"] = len(case_results)
    return report


def materialize_hand_oracle(directory: Path) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": "semantic-oracle-v2", "cases": []}
    for case in _enrich_oracle_cases(hand_oracle_cases()):
        source_path = directory / f"{case.case_id}.m"
        truth_path = directory / f"{case.case_id}.json"
        if not source_path.exists():
            source_path.write_bytes(case.source)
        source_bytes = source_path.read_bytes()
        truth = {
            "schema_version": "semantic-oracle-v2",
            "case_id": case.case_id,
            "case_kind": "hand_authored",
            "source_path": source_path.name,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "regions": [
                {
                    "region_key": "top-level",
                    "definitions": {
                        str(key): sorted(value) for key, value in case.expected_definitions.items()
                    },
                    "reads": {
                        str(key): sorted(value) for key, value in case.expected_reads.items()
                    },
                    "mutations": {
                        str(key): sorted(value) for key, value in case.expected_mutations.items()
                    },
                    "calls": {
                        str(key): sorted(value)
                        for key, value in (case.expected_calls or {}).items()
                    },
                    "roles": {
                        str(key): sorted(value)
                        for key, value in (case.expected_roles or {}).items()
                    },
                    "effects": {
                        str(key): sorted(value)
                        for key, value in (case.expected_effects or {}).items()
                    },
                }
            ],
        }
        truth_path.write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["cases"].append(
            {"case_id": case.case_id, "source": source_path.name, "truth": truth_path.name}
        )
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
