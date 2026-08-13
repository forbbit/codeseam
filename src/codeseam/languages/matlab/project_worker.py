from __future__ import annotations

import json
import sys
from pathlib import Path

from codeseam.core.raw_facts import extract_raw_facts
from codeseam.languages.matlab.frontend import MatlabFrontend


def main() -> int:
    path = Path(sys.argv[1])
    program = MatlabFrontend().analyze_source(path.read_bytes(), str(path))
    functions = [
        region.name for region in program.regions if region.kind == "function" and region.name
    ]
    calls = sorted(
        {
            call
            for region in program.regions
            for statement in region.statements
            for call in statement.calls
        }
    )
    facts = [fact for region in program.regions for fact in extract_raw_facts(region)]
    print(
        json.dumps(
            {
                "functions": functions,
                "has_script": any(region.kind == "script" for region in program.regions),
                "calls": calls,
                "diagnostics": program.diagnostics,
                "raw_boundaries": len(facts),
                "low_parse_confidence": sum(fact.reliability.parse < 1 for fact in facts),
                "low_dependency_confidence": sum(
                    fact.reliability.dependency < 1 for fact in facts
                ),
                "dynamic_workspace_boundaries": sum(
                    fact.reliability.dynamic_workspace_risk > 0 for fact in facts
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
