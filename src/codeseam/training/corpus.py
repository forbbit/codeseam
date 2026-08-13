from __future__ import annotations

import json
from pathlib import Path

from codeseam.languages.matlab import MatlabFrontend
from codeseam.training.data_policy import require_trainable_record
from codeseam.training.trainer import StructuredExample


def load_structured_examples(corpus: Path, split: str) -> list[StructuredExample]:
    examples = []
    for line in (corpus / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["split"] != split:
            continue
        require_trainable_record(record)
        path = corpus / record["relative_path"]
        program = MatlabFrontend().analyze_source(path.read_bytes(), str(path))
        segments_by_region: dict[str, list[dict]] = {}
        for segment in record.get("segments", []):
            segments_by_region.setdefault(segment.get("region_id", "script:top-level"), []).append(segment)
        boundaries_by_region: dict[str, list[dict]] = {}
        for boundary in record.get("boundaries", []):
            boundaries_by_region.setdefault(
                boundary.get("region_id", "script:top-level"), []
            ).append(boundary)
        for region in program.regions:
            if region.id not in segments_by_region:
                # Real gold files may contain unreviewed local helper functions.
                # Absence from the manifest means "unlabeled", never "no cuts".
                continue
            # Statement indices are the training truth. Physical lines are only
            # presentation metadata because MATLAB permits multiple statements
            # on one line and compound statements can span many lines.
            region_boundaries = boundaries_by_region.get(region.id, [])
            if any(item.get("boundary") is None for item in region_boundaries):
                raise ValueError(
                    f"{record['sample_id']}:{region.id} lacks statement-index truth"
                )
            cuts = tuple(
                sorted(
                    item["boundary"]
                    for item in region_boundaries
                    if item["label"] in {"preferred_cut", "acceptable_cut"}
                )
            )
            examples.append(
                StructuredExample(
                    region,
                    cuts,
                    f"{record['sample_id']}:{region.id}",
                    str(record.get("provenance", {}).get("project", "unknown")),
                    split,
                )
            )
    return examples
