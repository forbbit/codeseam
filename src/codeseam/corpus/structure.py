from __future__ import annotations

import hashlib
import json

from codeseam.core.dependencies import def_use_edges
from codeseam.core.ir import ProgramIR


def structure_fingerprint(program: ProgramIR) -> str:
    """Hash identifier-independent syntax/flow structure for leakage detection."""
    regions = []
    for region in program.regions:
        edges = def_use_edges(region)
        regions.append(
            {
                "kind": region.kind,
                "statements": [
                    {
                        "kind": item.kind,
                        "definitions": len(item.definitions),
                        "reads": len(item.reads),
                        "mutations": len(item.mutations),
                        "calls": len(item.calls),
                        "effects": sorted(effect.value for effect in item.effects),
                        "control": sorted(effect.value for effect in item.control_effects),
                        "compound": item.is_compound,
                    }
                    for item in region.statements
                ],
                "edges": sorted(
                    (edge.source_statement, edge.target_statement) for edge in edges
                ),
                "parameters": len(region.parameters),
                "outputs": len(region.declared_outputs),
            }
        )
    canonical = json.dumps(regions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
