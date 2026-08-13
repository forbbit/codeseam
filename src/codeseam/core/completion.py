from __future__ import annotations

from dataclasses import dataclass

from codeseam.core.dependencies import semantic_def_use_edges
from codeseam.core.ir import ExecutableRegion, OperationRole

COMPLETION_ROLES = {
    OperationRole.AGGREGATION,
    OperationRole.NORMALIZATION,
    OperationRole.SHAPING,
}


@dataclass(frozen=True, slots=True)
class CompletionEvidence:
    through_statement: int
    roles: tuple[str, ...]
    symbols: tuple[str, ...]


def completion_frontiers(
    region: ExecutableRegion, *, maximum_followup_statements: int = 4
) -> dict[int, CompletionEvidence]:
    """Return boundaries that precede a dependent completion chain.

    Keys are zero-based source statement indexes: key ``i`` denotes the boundary
    after statement ``i``.
    """
    edges = semantic_def_use_edges(region)
    incoming: dict[int, list] = {}
    for edge in edges:
        incoming.setdefault(edge.target_statement, []).append(edge)
    evidence: dict[int, CompletionEvidence] = {}
    statements = region.statements
    for boundary in range(len(statements) - 1):
        producer = statements[boundary]
        if not producer.is_compound:
            continue
        chain: list[tuple[int, set[str], set[str]]] = []
        frontier_sources = {boundary}
        for target in range(
            boundary + 1,
            min(len(statements), boundary + 1 + maximum_followup_statements),
        ):
            statement = statements[target]
            roles = statement.roles & COMPLETION_ROLES
            target_edges = incoming.get(target, [])
            feeding = [edge for edge in target_edges if edge.source_statement in frontier_sources]
            if not roles or not feeding:
                break
            # Alternative reaching definitions for the same symbol describe paths,
            # not additional inputs. Measure coverage by symbols so an if/loop merge
            # does not dilute genuine completion evidence.
            feeding_symbols = {edge.symbol for edge in feeding}
            incoming_symbols = {edge.symbol for edge in target_edges}
            if len(feeding_symbols) / max(1, len(incoming_symbols)) <= 0.5:
                break
            frontier_sources.add(target)
            chain.append((target, {role.value for role in roles}, feeding_symbols))
        # Each boundary preceding a member sees the complete unfinished suffix.
        # The previous implementation stored ``through=target`` immediately,
        # making every observed chain length exactly one.
        for offset, (target, _, _) in enumerate(chain):
            suffix = chain[offset:]
            evidence[target - 1] = CompletionEvidence(
                through_statement=chain[-1][0],
                roles=tuple(sorted(set().union(*(item[1] for item in suffix)))),
                symbols=tuple(sorted(set().union(*(item[2] for item in suffix)))),
            )
    return evidence
