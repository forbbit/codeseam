from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from codeseam.core.raw_facts import extract_raw_facts
from codeseam.languages.matlab import MatlabFrontend
from codeseam.training.data_policy import require_trainable_record


def audit_real_gold(corpus: Path) -> dict[str, object]:
    manifest = corpus / "manifest.jsonl"
    errors: list[str] = []
    if not manifest.is_file():
        return {"passed": False, "errors": ["manifest.jsonl is missing"]}
    records = []
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            errors.append(f"manifest line {line_number}: invalid JSON: {error.msg}")

    sample_ids: set[str] = set()
    project_splits: dict[str, str] = {}
    expected_sources: set[Path] = set()
    split_stats = defaultdict(Counter)
    reliability = defaultdict(list)
    reason_codes = Counter()
    same_line_boundaries = 0
    annotated_regions = 0
    module_count = 0
    preferred_count = 0

    for record in records:
        sample_id = record.get("sample_id", "<missing>")
        if sample_id in sample_ids:
            errors.append(f"duplicate sample_id: {sample_id}")
        sample_ids.add(sample_id)
        try:
            require_trainable_record(record)
        except ValueError as error:
            errors.append(f"{sample_id}: {error}")
        split = record.get("split")
        if split not in {"train", "validation", "test"}:
            errors.append(f"{sample_id}: invalid split {split!r}")
            continue
        provenance = record.get("provenance", {})
        project = provenance.get("project")
        if not project:
            errors.append(f"{sample_id}: missing provenance project")
        elif project in project_splits and project_splits[project] != split:
            errors.append(f"project split leakage: {project}")
        else:
            project_splits[project] = split

        relative = Path(record.get("relative_path", ""))
        path = corpus / relative
        expected_sources.add(path.resolve())
        if not path.is_file():
            errors.append(f"{sample_id}: source is missing: {relative.as_posix()}")
            continue
        source = path.read_bytes()
        digest = hashlib.sha256(source).hexdigest()
        if digest != record.get("source_sha256"):
            errors.append(f"{sample_id}: record source hash mismatch")
        if digest != provenance.get("source_sha256"):
            errors.append(f"{sample_id}: provenance source hash mismatch")

        program = MatlabFrontend().analyze_source(source, str(path))
        regions = {region.id: region for region in program.regions}
        segments_by_region = defaultdict(list)
        boundaries_by_region = defaultdict(list)
        for segment in record.get("segments", []):
            segments_by_region[segment.get("region_id", "script:top-level")].append(segment)
        for boundary in record.get("boundaries", []):
            boundaries_by_region[boundary.get("region_id", "script:top-level")].append(boundary)

        for region_id, segments in segments_by_region.items():
            annotated_regions += 1
            module_count += len(segments)
            split_stats[split]["regions"] += 1
            split_stats[split]["modules"] += len(segments)
            region = regions.get(region_id)
            if region is None:
                errors.append(f"{sample_id}: annotated region is missing: {region_id}")
                continue
            boundaries = boundaries_by_region.get(region_id, [])
            expected = set(range(1, len(region.statements)))
            observed = [item.get("boundary") for item in boundaries]
            if any(not isinstance(item, int) for item in observed):
                errors.append(f"{sample_id}:{region_id}: non-integer statement boundary")
                continue
            if len(observed) != len(set(observed)):
                errors.append(f"{sample_id}:{region_id}: duplicate statement boundary")
            if set(observed) != expected:
                errors.append(f"{sample_id}:{region_id}: boundary truth is not exhaustive")
            if len(segments) != 1 + sum(
                item.get("label") in {"preferred_cut", "acceptable_cut"}
                for item in boundaries
            ):
                errors.append(f"{sample_id}:{region_id}: segment and cut counts disagree")

            facts = extract_raw_facts(region)
            by_boundary = {item.boundary_index: item for item in facts}
            for item in boundaries:
                boundary = item["boundary"]
                fact = by_boundary.get(boundary)
                if fact is None:
                    errors.append(f"{sample_id}:{region_id}: boundary S{boundary} not analyzable")
                    continue
                r = fact.reliability
                for name in ("parse", "call_resolution", "dependency", "role", "effect"):
                    reliability[name].append(float(getattr(r, name)))
                reason_codes.update(r.dependency_reason_codes)
                if fact.after_line == fact.before_line:
                    same_line_boundaries += 1
                if item.get("label") in {"preferred_cut", "acceptable_cut"}:
                    preferred_count += 1
                    split_stats[split]["cuts"] += 1
                    if fact.constraints:
                        errors.append(
                            f"{sample_id}:{region_id}: true cut S{boundary} violates "
                            f"constraints {list(fact.constraints)}"
                        )
        split_stats[split]["files"] += 1

    actual_sources = {path.resolve() for path in (corpus / "sources").glob("*.m")}
    for extra in sorted(actual_sources - expected_sources):
        errors.append(f"unreferenced source: {extra.name}")
    for missing in sorted(expected_sources - actual_sources):
        errors.append(f"manifest source outside published source set: {missing.name}")

    project_counts = Counter(project_splits.values())
    report = {
        "schema_version": "real-gold-audit",
        "passed": not errors,
        "errors": errors,
        "dataset_sha256": _dataset_hash(manifest, expected_sources),
        "counts": {
            "records": len(records),
            "projects": len(project_splits),
            "annotated_regions": annotated_regions,
            "modules": module_count,
            "preferred_cuts": preferred_count,
            "same_line_candidate_boundaries": same_line_boundaries,
        },
        "splits": {
            name: {
                **dict(split_stats[name]),
                "projects": project_counts[name],
            }
            for name in ("train", "validation", "test")
        },
        "reliability": {
            name: _distribution(values) for name, values in sorted(reliability.items())
        },
        "reliability_reason_codes": dict(sorted(reason_codes.items())),
    }
    return report


def write_real_gold_audit(corpus: Path, output: Path) -> dict[str, object]:
    report = audit_real_gold(corpus)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "minimum": 0.0, "mean": 0.0, "p10": 0.0, "median": 0.0}
    percentile = lambda p: ordered[round((len(ordered) - 1) * p)]
    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "mean": sum(ordered) / len(ordered),
        "p10": percentile(0.10),
        "median": percentile(0.50),
    }


def _dataset_hash(manifest: Path, sources: set[Path]) -> str:
    digest = hashlib.sha256(manifest.read_bytes())
    for path in sorted(sources):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
