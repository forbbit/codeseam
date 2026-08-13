from __future__ import annotations

from dataclasses import dataclass

from codeseam.core.flow import program_dependence_graph
from codeseam.core.ir import ExecutableRegion, ProgramDependenceGraph, ProgramIR
from codeseam.core.raw_facts import BoundaryRawFacts, extract_raw_facts


@dataclass(frozen=True, slots=True)
class RegionSemantics:
    """Language-neutral semantic evidence compiled from one IR region."""

    region: ExecutableRegion
    dependence_graph: ProgramDependenceGraph
    boundary_facts: tuple[BoundaryRawFacts, ...]


class CommonSemanticAnalyzer:
    """Shared semantic stage between all frontends and feature models."""

    def analyze_region(self, region: ExecutableRegion) -> RegionSemantics:
        return RegionSemantics(
            region=region,
            dependence_graph=program_dependence_graph(region),
            boundary_facts=tuple(extract_raw_facts(region)),
        )

    def analyze_program(self, program: ProgramIR) -> tuple[RegionSemantics, ...]:
        return tuple(self.analyze_region(region) for region in program.regions)
