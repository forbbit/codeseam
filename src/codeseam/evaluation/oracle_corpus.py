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


def run_hand_oracle() -> dict[str, object]:
    frontend = MatlabFrontend()
    observations: list[OracleObservation] = []
    case_results = {}
    for case in hand_oracle_cases():
        program = frontend.analyze_source(case.source, f"{case.case_id}.m")
        region = program.regions[0]
        items = region_observations(
            region,
            expected_definitions=case.expected_definitions,
            expected_reads=case.expected_reads,
            expected_mutations=case.expected_mutations,
        )
        observations.extend(items)
        case_results[case.case_id] = evaluate_oracle(items)["overall"]
    report = evaluate_oracle(observations)
    report["cases"] = case_results
    report["case_count"] = len(case_results)
    return report


def materialize_hand_oracle(directory: Path) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": "semantic-oracle-v2", "cases": []}
    for case in hand_oracle_cases():
        source_path = directory / f"{case.case_id}.m"
        truth_path = directory / f"{case.case_id}.json"
        source_path.write_bytes(case.source)
        truth = {
            "schema_version": "semantic-oracle-v2",
            "case_id": case.case_id,
            "case_kind": "hand_authored",
            "source_path": source_path.name,
            "source_sha256": hashlib.sha256(case.source).hexdigest(),
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
