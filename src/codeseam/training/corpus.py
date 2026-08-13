from __future__ import annotations

import json
from pathlib import Path

from codeseam.languages.matlab import MatlabFrontend
from codeseam.training.trainer import StructuredExample


def load_structured_examples(corpus: Path, split: str) -> list[StructuredExample]:
    examples = []
    for line in (corpus / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["split"] != split:
            continue
        path = corpus / record["relative_path"]
        program = MatlabFrontend().analyze_source(path.read_bytes(), str(path))
        segments_by_region: dict[str, list[dict]] = {}
        for segment in record.get("segments", []):
            segments_by_region.setdefault(segment.get("region_id", "script:top-level"), []).append(segment)
        for region in program.regions:
            segments = sorted(
                segments_by_region.get(region.id, []), key=lambda item: item["start_line"]
            )
            if segments:
                cuts = tuple(
                    index
                    for index, statement in enumerate(region.statements[:-1], start=1)
                    if any(statement.source.end_line == segment["end_line"] for segment in segments[:-1])
                )
            else:
                cuts = tuple(
                    item["boundary"]
                    for item in record["boundaries"]
                    if item.get("region_id", "script:top-level") == region.id
                    and item["label"] == "preferred_cut"
                    and item.get("boundary") is not None
                )
            examples.append(StructuredExample(region, cuts, f"{record['sample_id']}:{region.id}"))
    return examples
