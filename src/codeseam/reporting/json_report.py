from __future__ import annotations

import json
from pathlib import Path

from codeseam.core.ir import AnalysisResult


def write_json(result: AnalysisResult, path: Path) -> None:
    path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
