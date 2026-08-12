from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codeseam.corpus.schema import BoundaryLabel
from codeseam.languages.matlab import MatlabFrontend


def create_annotation_template(source_path: Path, output: Path, annotator: str) -> dict:
    source = source_path.read_bytes()
    program = MatlabFrontend().analyze_source(source, str(source_path))
    boundaries = [
        {
            "region_id": region.id,
            "after_line": statement.source.end_line,
            "label": "neutral",
            "reason": "",
        }
        for region in program.regions
        for statement in region.statements[:-1]
    ]
    document = {
        "schema_version": "1.0",
        "source_path": str(source_path),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "annotator": annotator,
        "boundaries": boundaries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def validate_annotation(annotation_path: Path, source_path: Path) -> list[str]:
    errors: list[str] = []
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    source = source_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != annotation.get("source_sha256"):
        errors.append("source checksum mismatch")
    program = MatlabFrontend().analyze_source(source, str(source_path))
    legal = {
        (region.id, statement.source.end_line)
        for region in program.regions
        for statement in region.statements[:-1]
    }
    seen: set[tuple[str, int]] = set()
    allowed = {label.value for label in BoundaryLabel}
    for item in annotation.get("boundaries", []):
        key = (item.get("region_id"), item.get("after_line"))
        if key in seen:
            errors.append(f"duplicate boundary: {key}")
        seen.add(key)
        if key not in legal:
            errors.append(f"illegal boundary: {key}")
        if item.get("label") not in allowed:
            errors.append(f"invalid label at {key}: {item.get('label')}")
        if item.get("label") != BoundaryLabel.NEUTRAL.value and not item.get("reason", "").strip():
            errors.append(f"non-neutral boundary requires a reason: {key}")
    if seen != legal:
        errors.append("annotation must cover every legal boundary exactly once")
    return errors


def agreement(left_path: Path, right_path: Path) -> dict[str, float | int]:
    left = json.loads(left_path.read_text(encoding="utf-8"))
    right = json.loads(right_path.read_text(encoding="utf-8"))
    if left.get("source_sha256") != right.get("source_sha256"):
        raise ValueError("annotations refer to different source versions")
    left_labels = {
        (item["region_id"], item["after_line"]): item["label"] for item in left["boundaries"]
    }
    right_labels = {
        (item["region_id"], item["after_line"]): item["label"] for item in right["boundaries"]
    }
    keys = sorted(set(left_labels) & set(right_labels))
    exact = sum(left_labels[key] == right_labels[key] for key in keys)
    binary = sum(_positive(left_labels[key]) == _positive(right_labels[key]) for key in keys)
    return {
        "compared_boundaries": len(keys),
        "exact_agreement": exact / len(keys) if keys else 0.0,
        "cut_vs_noncut_agreement": binary / len(keys) if keys else 0.0,
    }


def _positive(label: str) -> bool:
    return label in {BoundaryLabel.PREFERRED.value, BoundaryLabel.ACCEPTABLE.value}
