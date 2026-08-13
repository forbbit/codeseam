from __future__ import annotations

import hashlib
import json

from codeseam.core.raw_facts import BoundaryRawFacts


def raw_fingerprint(facts: BoundaryRawFacts) -> dict[str, object]:
    return facts.fingerprint()


def fingerprint_id(facts: BoundaryRawFacts) -> str:
    payload = json.dumps(raw_fingerprint(facts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def numeric_fingerprint(facts: BoundaryRawFacts) -> tuple[float, ...]:
    r = facts.reliability
    return tuple(float(value) for value in (
        facts.dead_symbol_count, facts.born_symbol_count, facts.cross_symbol_count,
        facts.input_interface_count, facts.output_interface_count,
        facts.cross_dependency_count, facts.dependency_span_mean,
        facts.dependency_span_max, facts.dependency_reuse_mass,
        facts.unfinished_work_mass, facts.completion_chain_length,
        facts.left_context_size, facts.right_context_size,
        r.parse, r.call_resolution, r.dependency, r.role,
        r.dynamic_workspace_risk, r.alias_uncertainty,
    ))
