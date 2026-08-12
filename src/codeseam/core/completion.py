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
        chain_roles: set[str] = set()
        chain_symbols: set[str] = set()
        frontier_sources = {boundary}
        through = boundary
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
            through = target
            frontier_sources.add(target)
            chain_roles.update(role.value for role in roles)
            chain_symbols.update(feeding_symbols)
            evidence[target - 1] = CompletionEvidence(
                through_statement=through,
                roles=tuple(sorted(chain_roles)),
                symbols=tuple(sorted(chain_symbols)),
            )
    return evidence
