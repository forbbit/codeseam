from __future__ import annotations

import json
import sys
from pathlib import Path

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
    print(
        json.dumps(
            {
                "functions": functions,
                "has_script": any(region.kind == "script" for region in program.regions),
                "calls": calls,
                "diagnostics": program.diagnostics,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
