from __future__ import annotations

import json
import sys
from pathlib import Path

from codeseam.core.analyzer import analyze_program
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.languages.matlab import MatlabFrontend


def main() -> int:
    # Real GitHub MATLAB is detection/stress input only. This worker emits no
    # ground truth and its predictions must never be recycled into training.
    path = Path(sys.argv[1])
    program = MatlabFrontend().analyze_source(path.read_bytes(), str(path))
    result = analyze_program(program)
    facts = [fact for region in program.regions for fact in extract_raw_facts(region)]
    recommendations = sorted(
        (
            {
                "region": item.region_id,
                "boundary": item.boundary,
                "after_line": item.after_line,
                "before_line": item.before_line,
                "score": item.score,
                "features": item.features,
            }
            for item in result.boundaries
            if item.recommended
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    print(
        json.dumps(
            {
                "path": str(path),
                "diagnostics": program.diagnostics,
                "regions": len(program.regions),
                "statements": sum(len(region.statements) for region in program.regions),
                "boundaries": len(result.boundaries),
                "recommendations": recommendations,
                "low_parse_boundaries": sum(fact.reliability.parse < 1 for fact in facts),
                "low_dependency_boundaries": sum(
                    fact.reliability.dependency < 0.95 for fact in facts
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
