from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

from script_boundary.corpus.metrics import aggregate_matches, match_boundaries_with_ignored
from script_boundary.corpus.schema import (
    AuxiliaryFile,
    BoundaryLabel,
    BoundaryTruth,
    CorpusRecord,
    SegmentTruth,
)
from script_boundary.corpus.structure import structure_fingerprint
from script_boundary.languages.matlab import MatlabFrontend


@dataclass(frozen=True, slots=True)
class GeneratedSample:
    source: str
    boundaries: list[BoundaryTruth]
    tags: list[str]
    segments: list[SegmentTruth] | None = None
    auxiliary_files: dict[str, str] | None = None


FAMILIES = (
    "linear_pipeline",
    "loop_with_finalize",
    "workspace_external",
    "mixed_local_function",
    "nested_branch_pipeline",
    "multi_output_shared_config",
    "false_structural_peak",
    "function_handle_project",
    "adversarial_twin_peaks",
    "adversarial_large_interface",
    "composed_pipeline",
    "branch_merge_finalize",
    "loop_carried_branch",
    "conditional_postprocess",
    "nested_state_machine",
    "mixed_project_control",
    "heldout_branch_loop",
)

FAMILY_SPLITS = {
    "linear_pipeline": "train",
    "loop_with_finalize": "train",
    "workspace_external": "train",
    "mixed_local_function": "train",
    "nested_branch_pipeline": "train",
    "multi_output_shared_config": "validation",
    "false_structural_peak": "test",
    "function_handle_project": "test",
    "adversarial_twin_peaks": "test",
    "adversarial_large_interface": "validation",
    "composed_pipeline": "train",
    "branch_merge_finalize": "train",
    "loop_carried_branch": "train",
    "conditional_postprocess": "validation",
    "nested_state_machine": "validation",
    "mixed_project_control": "test",
    "heldout_branch_loop": "test",
}


def generate_corpus(output: Path, *, count: int = 40, seed: int = 1729) -> list[CorpusRecord]:
    if count < 1:
        raise ValueError("count must be positive")
    output.mkdir(parents=True, exist_ok=True)
    records: list[CorpusRecord] = []
    for index in range(count):
        sample_seed = seed + index * 104729
        family = FAMILIES[index % len(FAMILIES)]
        sample = _generate(family, random.Random(sample_seed))
        sample_id = f"{family}-{index:05d}-{sample_seed}"
        source_bytes = sample.source.encode("utf-8")
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        split = FAMILY_SPLITS[family]
        relative_path = f"{split}/{family}/{sample_id}.m"
        path = output / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        program = MatlabFrontend().analyze_source(source_bytes, relative_path)
        if program.diagnostics:
            raise ValueError(
                f"generator emitted invalid MATLAB for {sample_id}: {program.diagnostics}"
            )
        path.write_bytes(source_bytes)
        auxiliary_files: list[AuxiliaryFile] = []
        for auxiliary_name, auxiliary_source in sorted((sample.auxiliary_files or {}).items()):
            auxiliary_path = path.parent / auxiliary_name
            auxiliary_path.parent.mkdir(parents=True, exist_ok=True)
            auxiliary_bytes = auxiliary_source.encode("utf-8")
            auxiliary_program = MatlabFrontend().analyze_source(
                auxiliary_bytes, str(auxiliary_path)
            )
            if auxiliary_program.diagnostics:
                raise ValueError(
                    f"generator emitted invalid auxiliary MATLAB for {sample_id}: "
                    f"{auxiliary_program.diagnostics}"
                )
            auxiliary_path.write_bytes(auxiliary_bytes)
            auxiliary_files.append(
                AuxiliaryFile(
                    relative_path=str(auxiliary_path.relative_to(output)).replace("\\", "/"),
                    source_sha256=hashlib.sha256(auxiliary_bytes).hexdigest(),
                )
            )
        complete_truth = _complete_boundary_truth(program, sample.boundaries, sample.segments or [])
        records.append(
            CorpusRecord(
                schema_version="1.0",
                sample_id=sample_id,
                family=family,
                split=split,
                seed=sample_seed,
                relative_path=relative_path,
                source_sha256=source_sha256,
                boundaries=complete_truth,
                segments=sample.segments or [],
                auxiliary_files=auxiliary_files,
                tags=sample.tags,
                provenance={
                    "generator": "script-boundary",
                    "recipe_version": "3",
                    "structure_fingerprint": structure_fingerprint(program),
                },
            )
        )
    manifest = output / "manifest.jsonl"
    manifest.write_text(
        "".join(json.dumps(record.to_dict(), sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return records


def audit_corpus(output: Path) -> list[str]:
    manifest = output / "manifest.jsonl"
    errors: list[str] = []
    if not manifest.exists():
        return ["manifest.jsonl is missing"]
    structure_splits: dict[str, set[str]] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(line)
        path = output / record["relative_path"]
        if not path.exists():
            errors.append(f"line {line_number}: missing {record['relative_path']}")
            continue
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != record["source_sha256"]:
            errors.append(f"line {line_number}: checksum mismatch")
        for auxiliary in record.get("auxiliary_files", []):
            auxiliary_path = output / auxiliary["relative_path"]
            if not auxiliary_path.exists():
                errors.append(f"line {line_number}: missing {auxiliary['relative_path']}")
                continue
            if (
                hashlib.sha256(auxiliary_path.read_bytes()).hexdigest()
                != auxiliary["source_sha256"]
            ):
                errors.append(f"line {line_number}: auxiliary checksum mismatch")
        program = MatlabFrontend().analyze_source(source, str(path))
        if program.diagnostics:
            errors.append(f"line {line_number}: parser diagnostics")
        fingerprint = structure_fingerprint(program)
        recorded = record.get("provenance", {}).get("structure_fingerprint")
        if recorded != fingerprint:
            errors.append(f"line {line_number}: structure fingerprint mismatch")
        structure_splits.setdefault(fingerprint, set()).add(record["split"])
        legal_boundaries = {
            (region.id, index + 1, statement.source.end_line)
            for region in program.regions
            for index, statement in enumerate(region.statements[:-1])
        }
        labeled_boundaries = set()
        for truth in record["boundaries"]:
            key = (
                truth.get("region_id", "script:top-level"),
                truth.get("boundary"),
                truth["after_line"],
            )
            if key not in legal_boundaries:
                errors.append(
                    f"line {line_number}: label after line {truth['after_line']} is not a legal boundary"
                )
            if key in labeled_boundaries:
                errors.append(f"line {line_number}: duplicate boundary label {key}")
            labeled_boundaries.add(key)
        missing = legal_boundaries - labeled_boundaries
        if missing:
            errors.append(f"line {line_number}: {len(missing)} legal boundaries are unlabeled")
        for segment in record.get("segments", []):
            if segment["start_line"] > segment["end_line"]:
                errors.append(f"line {line_number}: invalid segment range")
            region = next(
                (item for item in program.regions if item.id == segment["region_id"]), None
            )
            if region is None or not (
                region.source.start_line
                <= segment["start_line"]
                <= segment["end_line"]
                <= region.source.end_line
            ):
                errors.append(f"line {line_number}: segment is outside its executable region")
    for fingerprint, splits in structure_splits.items():
        if len(splits) > 1:
            errors.append(
                f"structure {fingerprint[:12]} leaks across splits: {', '.join(sorted(splits))}"
            )
    return errors


def _complete_boundary_truth(
    program, supplied: list[BoundaryTruth], segments: list[SegmentTruth]
) -> list[BoundaryTruth]:
    supplied_by_line = {(item.region_id, item.after_line): item for item in supplied}
    segment_ends = {(item.region_id, item.end_line): item for item in segments}
    segment_starts = {(item.region_id, item.start_line): item for item in segments}
    complete = []
    for region in program.regions:
        for index, statement in enumerate(region.statements[:-1], 1):
            existing = supplied_by_line.get((region.id, statement.source.end_line))
            left_segment = segment_ends.get((region.id, statement.source.end_line))
            next_line = region.statements[index].source.start_line
            right_segment = segment_starts.get((region.id, next_line))
            if existing is None:
                is_module_transition = left_segment is not None and right_segment is not None
                complete.append(
                    BoundaryTruth(
                        after_line=statement.source.end_line,
                        label=(
                            BoundaryLabel.PREFERRED
                            if is_module_transition
                            else BoundaryLabel.DISCOURAGED
                        ),
                        reason=(
                            "derived transition between ground-truth modules"
                            if is_module_transition
                            else "inside a ground-truth module"
                        ),
                        left_module=left_segment.module_id if left_segment else None,
                        right_module=right_segment.module_id if right_segment else None,
                        region_id=region.id,
                        boundary=index,
                    )
                )
            else:
                complete.append(
                    BoundaryTruth(
                        after_line=existing.after_line,
                        label=existing.label,
                        reason=existing.reason,
                        left_module=existing.left_module,
                        right_module=existing.right_module,
                        region_id=existing.region_id,
                        boundary=index,
                    )
                )
    return complete


def evaluate_corpus(
    output: Path,
    split: str | None = None,
    *,
    tolerance: int = 2,
    scoring_config=None,
) -> dict[str, float | int | str | dict[str, float | int]]:
    from script_boundary.core.analyzer import analyze_program

    manifest = output / "manifest.jsonl"
    if not manifest.exists():
        raise ValueError("manifest.jsonl is missing")
    lines = manifest.read_text(encoding="utf-8").splitlines()
    preferred = preferred_recommended = 0
    discouraged = discouraged_recommended = 0
    forbidden = forbidden_recommended = 0
    recommendations = 0
    statement_count = 0
    strict_exact_matches = []
    strict_tolerant_matches = []
    relaxed_exact_matches = []
    relaxed_tolerant_matches = []
    strict_truth_count = 0
    structure_matches: dict[str, list] = {}
    labeled = pairwise_correct = pairwise_total = 0
    for line in lines:
        record = json.loads(line)
        if split is not None and record["split"] != split:
            continue
        path = output / record["relative_path"]
        result = analyze_program(
            MatlabFrontend().analyze_source(path.read_bytes(), str(path)),
            scoring_config=scoring_config,
        )
        recommendations += sum(boundary.recommended for boundary in result.boundaries)
        statement_count += sum(len(region.statements) for region in result.program.regions)
        lookup = {(item.region_id, item.boundary): item for item in result.boundaries}
        predicted_by_region: dict[str, list[int]] = {}
        strict_by_region: dict[str, list[int]] = {}
        relaxed_by_region: dict[str, list[int]] = {}
        neutral_by_region: dict[str, list[int]] = {}
        for boundary in result.boundaries:
            if boundary.recommended:
                predicted_by_region.setdefault(boundary.region_id, []).append(boundary.boundary)
        truth_items: list[tuple[str, float]] = []
        for truth in record["boundaries"]:
            key = (truth.get("region_id", "script:top-level"), truth.get("boundary"))
            boundary = lookup.get(key)
            if boundary is None:
                continue
            labeled += 1
            label = truth["label"]
            truth_items.append((label, boundary.score))
            if label == BoundaryLabel.PREFERRED.value:
                preferred += 1
                preferred_recommended += int(boundary.recommended)
                strict_by_region.setdefault(boundary.region_id, []).append(boundary.boundary)
                relaxed_by_region.setdefault(boundary.region_id, []).append(boundary.boundary)
                strict_truth_count += 1
            elif label == BoundaryLabel.ACCEPTABLE.value:
                relaxed_by_region.setdefault(boundary.region_id, []).append(boundary.boundary)
            elif label == BoundaryLabel.NEUTRAL.value:
                neutral_by_region.setdefault(boundary.region_id, []).append(boundary.boundary)
            elif label == BoundaryLabel.DISCOURAGED.value:
                discouraged += 1
                discouraged_recommended += int(boundary.recommended)
            elif label == BoundaryLabel.FORBIDDEN.value:
                forbidden += 1
                forbidden_recommended += int(boundary.recommended)
        region_ids = (
            set(predicted_by_region)
            | set(strict_by_region)
            | set(relaxed_by_region)
            | set(neutral_by_region)
        )
        for region_id in region_ids:
            predicted = predicted_by_region.get(region_id, [])
            strict_truth = strict_by_region.get(region_id, [])
            relaxed_truth = relaxed_by_region.get(region_id, [])
            neutral = neutral_by_region.get(region_id, [])
            exact_match = match_boundaries_with_ignored(
                predicted, strict_truth, neutral + relaxed_truth
            )
            strict_exact_matches.append(exact_match)
            fingerprint = record.get("provenance", {}).get(
                "structure_fingerprint", record["source_sha256"]
            )
            structure_matches.setdefault(fingerprint, []).append(exact_match)
            strict_tolerant_matches.append(
                match_boundaries_with_ignored(
                    predicted,
                    strict_truth,
                    neutral + relaxed_truth,
                    tolerance=tolerance,
                )
            )
            relaxed_exact_matches.append(
                match_boundaries_with_ignored(predicted, relaxed_truth, neutral)
            )
            relaxed_tolerant_matches.append(
                match_boundaries_with_ignored(
                    predicted, relaxed_truth, neutral, tolerance=tolerance
                )
            )
        positives = [s for label, s in truth_items if label == BoundaryLabel.PREFERRED.value]
        negatives = [
            s
            for label, s in truth_items
            if label in {BoundaryLabel.DISCOURAGED.value, BoundaryLabel.FORBIDDEN.value}
        ]
        for positive in positives:
            for negative in negatives:
                pairwise_total += 1
                pairwise_correct += int(positive > negative)
    selected_samples = sum(
        1 for line in lines if split is None or json.loads(line)["split"] == split
    )
    strict_exact = aggregate_matches(strict_exact_matches)
    strict_tolerant = aggregate_matches(strict_tolerant_matches)
    relaxed_exact = aggregate_matches(relaxed_exact_matches)
    relaxed_tolerant = aggregate_matches(relaxed_tolerant_matches)
    per_structure = [aggregate_matches(items) for items in structure_matches.values()]
    structure_macro = {
        name: sum(getattr(item, name) for item in per_structure) / len(per_structure)
        if per_structure
        else 0.0
        for name in ("precision", "recall", "f1")
    }
    return {
        "split": split or "all",
        "samples": selected_samples,
        "labeled_boundaries": labeled,
        "preferred_recall": preferred_recommended / preferred if preferred else 0.0,
        "discouraged_recommendation_rate": (
            discouraged_recommended / discouraged if discouraged else 0.0
        ),
        "forbidden_recommendation_rate": forbidden_recommended / forbidden if forbidden else 0.0,
        "recommendations_per_sample": (
            recommendations / selected_samples if selected_samples else 0.0
        ),
        "recommendations_per_100_statements": (
            100.0 * recommendations / statement_count if statement_count else 0.0
        ),
        "overcut_ratio": recommendations / strict_truth_count if strict_truth_count else 0.0,
        "excess_cut_rate": (
            max(0, recommendations - strict_truth_count) / max(1, strict_truth_count)
        ),
        "strict_exact": strict_exact.to_dict(),
        "strict_tolerant": strict_tolerant.to_dict(),
        "strict_exact_structure_macro": structure_macro,
        "unique_structures": len(structure_matches),
        "relaxed_exact": relaxed_exact.to_dict(),
        "relaxed_tolerant": relaxed_tolerant.to_dict(),
        "tolerance_statements": tolerance,
        "pairwise_accuracy": pairwise_correct / pairwise_total if pairwise_total else 0.0,
    }


def _generate(family: str, rng: random.Random) -> GeneratedSample:
    return {
        "linear_pipeline": _linear_pipeline,
        "loop_with_finalize": _loop_with_finalize,
        "workspace_external": _workspace_external,
        "mixed_local_function": _mixed_local_function,
        "nested_branch_pipeline": _nested_branch_pipeline,
        "multi_output_shared_config": _multi_output_shared_config,
        "false_structural_peak": _false_structural_peak,
        "function_handle_project": _function_handle_project,
        "adversarial_twin_peaks": _adversarial_twin_peaks,
        "adversarial_large_interface": _adversarial_large_interface,
        "composed_pipeline": _composed_pipeline,
        "branch_merge_finalize": _branch_merge_finalize,
        "loop_carried_branch": _loop_carried_branch,
        "conditional_postprocess": _conditional_postprocess,
        "nested_state_machine": _nested_state_machine,
        "mixed_project_control": _mixed_project_control,
        "heldout_branch_loop": _heldout_branch_loop,
    }[family](rng)


def _linear_pipeline(rng: random.Random) -> GeneratedSample:
    n = rng.choice((128, 256, 512, 1024))
    lines = [
        f"sampleCount = {n};",
        "raw = randn(1, sampleCount);",
        "offset = mean(raw);",
        "centered = raw - offset;",
        "scale = std(centered);",
        "normalized = centered / scale;",
        "spectrum = abs(fft(normalized));",
        "limit = median(spectrum);",
        "mask = spectrum > limit;",
        "selected = spectrum(mask);",
        "summary = [mean(selected), std(selected)];",
        "disp(summary);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                6, BoundaryLabel.PREFERRED, "known phase transition", "normalize", "select"
            ),
            BoundaryTruth(4, BoundaryLabel.DISCOURAGED, "normalization phase is incomplete"),
            BoundaryTruth(
                11, BoundaryLabel.DISCOURAGED, "terminal output belongs to summary phase"
            ),
        ],
        ["script", "sequential", "single_output"],
        [
            SegmentTruth("normalize", 1, 6),
            SegmentTruth("select", 7, 11),
            SegmentTruth("output", 12, 12, extraction_safe=False),
        ],
    )


def _loop_with_finalize(rng: random.Random) -> GeneratedSample:
    decay = rng.choice((0.75, 0.8, 0.9, 0.95))
    lines = [
        "input = randn(1, 400);",
        "state = zeros(size(input));",
        "for index = 2:length(input)",
        f"    state(index) = {decay} * state(index - 1) + input(index);",
        "end",
        "tail = state(20:end);",
        "energy = sum(abs(tail).^2);",
        "normalizedEnergy = energy / length(tail);",
        "fprintf('energy=%g\\n', normalizedEnergy);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                5,
                BoundaryLabel.PREFERRED,
                "complete loop ends before finalization",
                "filter",
                "finalize",
            ),
            BoundaryTruth(7, BoundaryLabel.DISCOURAGED, "finalization dependency remains live"),
        ],
        ["script", "loop", "hard_negative", "terminal_output"],
        [SegmentTruth("filter", 1, 5), SegmentTruth("finalize", 6, 9)],
    )


def _workspace_external(rng: random.Random) -> GeneratedSample:
    gain = rng.choice((2, 4, 8))
    lines = [
        "load input.mat",
        f"gain = {gain};",
        "scaled = raw * gain;",
        "run calibrate.m",
        "corrected = scaled - calibrationOffset;",
        "metric = mean(abs(corrected));",
        "save output.mat corrected metric",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(3, BoundaryLabel.FORBIDDEN, "run mutates the shared workspace"),
            BoundaryTruth(
                4, BoundaryLabel.FORBIDDEN, "unknown variables injected by external script"
            ),
            BoundaryTruth(6, BoundaryLabel.DISCOURAGED, "save belongs to the output phase"),
        ],
        ["script", "external_file", "workspace", "forbidden_boundary"],
        [SegmentTruth("workspace_pipeline", 1, 7, extraction_safe=False)],
    )


def _mixed_local_function(rng: random.Random) -> GeneratedSample:
    width = rng.choice((16, 32, 64))
    lines = [
        "data = randn(1, 256);",
        f"windowWidth = {width};",
        "prepared = prepareData(data);",
        "blocks = floor(length(prepared) / windowWidth);",
        "scores = zeros(1, blocks);",
        "for block = 1:blocks",
        "    first = (block - 1) * windowWidth + 1;",
        "    last = block * windowWidth;",
        "    scores(block) = mean(abs(prepared(first:last)));",
        "end",
        "result = max(scores);",
        "disp(result);",
        "",
        "function output = prepareData(input)",
        "offset = mean(input);",
        "centered = input - offset;",
        "output = centered / std(centered);",
        "end",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                3,
                BoundaryLabel.PREFERRED,
                "existing helper completes preparation",
                "prepare",
                "aggregate",
            ),
            BoundaryTruth(
                10,
                BoundaryLabel.ACCEPTABLE,
                "complete aggregation loop ends",
                "aggregate",
                "summary",
            ),
            BoundaryTruth(11, BoundaryLabel.DISCOURAGED, "display belongs to summary phase"),
        ],
        ["mixed_script_function", "local_function", "loop", "known_module_origin"],
        [
            SegmentTruth("prepare", 1, 3),
            SegmentTruth("aggregate", 4, 10),
            SegmentTruth("summary", 11, 12),
            SegmentTruth("prepare_helper", 15, 17, region_id="function:prepareData"),
        ],
    )


def _nested_branch_pipeline(rng: random.Random) -> GeneratedSample:
    threshold = rng.choice((0.0, 0.1, 0.25, 0.5))
    lines = [
        "samples = randn(1, 300);",
        f"threshold = {threshold};",
        "filtered = zeros(size(samples));",
        "if mean(samples) > threshold",
        "    for index = 1:length(samples)",
        "        if samples(index) > threshold",
        "            filtered(index) = samples(index);",
        "        else",
        "            filtered(index) = 0;",
        "        end",
        "    end",
        "else",
        "    filtered = abs(samples);",
        "end",
        "active = filtered(filtered > 0);",
        "count = length(active);",
        "meanValue = mean(active);",
        "report = [count, meanValue];",
        "disp(report);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                14,
                BoundaryLabel.PREFERRED,
                "complete nested decision ends before aggregation",
                "filter",
                "aggregate",
            ),
            BoundaryTruth(16, BoundaryLabel.DISCOURAGED, "aggregation is incomplete"),
            BoundaryTruth(18, BoundaryLabel.DISCOURAGED, "terminal output belongs to report"),
        ],
        ["nested_control", "if", "for", "hard_negative"],
        [
            SegmentTruth("filter", 1, 14),
            SegmentTruth("aggregate", 15, 19),
        ],
    )


def _multi_output_shared_config(rng: random.Random) -> GeneratedSample:
    scale = rng.choice((0.5, 1.0, 2.0, 4.0))
    lines = [
        f"globalScale = {scale};",
        "input = randn(1, 512);",
        "[center, spread] = robustStats(input);",
        "normalized = (input - center) / spread;",
        "scaled = normalized * globalScale;",
        "positive = scaled(scaled >= 0);",
        "negative = scaled(scaled < 0);",
        "positiveEnergy = sum(positive.^2) * globalScale;",
        "negativeEnergy = sum(negative.^2) * globalScale;",
        "ratio = positiveEnergy / max(negativeEnergy, eps);",
        "result = [ratio, center, spread];",
        "disp(result);",
        "",
        "function [center, spread] = robustStats(values)",
        "center = median(values);",
        "spread = median(abs(values - center));",
        "end",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                5,
                BoundaryLabel.PREFERRED,
                "normalized representation feeds classification",
                "normalize",
                "classify",
            ),
            BoundaryTruth(
                7,
                BoundaryLabel.DISCOURAGED,
                "shared configuration and both partitions remain live",
            ),
            BoundaryTruth(10, BoundaryLabel.ACCEPTABLE, "energy computation ends before report"),
        ],
        ["multi_output", "shared_config", "local_function", "long_lived_symbol"],
        [
            SegmentTruth("normalize", 1, 5),
            SegmentTruth("classify", 6, 10),
            SegmentTruth("report", 11, 12),
        ],
    )


def _false_structural_peak(rng: random.Random) -> GeneratedSample:
    limit = rng.choice((16, 32, 48, 64))
    lines = [
        f"limit = {limit};",
        "values = randn(1, 200);",
        "total = 0;",
        "count = 0;",
        "for index = 1:length(values)",
        "    if values(index) > 0",
        "        total = total + values(index);",
        "        count = count + 1;",
        "    end",
        "end",
        "average = total / max(count, 1);",
        "variance = sum((values - average).^2) / length(values);",
        "standardized = (values - average) / sqrt(variance);",
        "firstWindow = standardized(1:limit);",
        "signature = fft(firstWindow);",
        "result = abs(signature);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                10,
                BoundaryLabel.DISCOURAGED,
                "loop completion is a false peak because reduction finalization follows",
            ),
            BoundaryTruth(
                13,
                BoundaryLabel.PREFERRED,
                "statistical normalization ends before window analysis",
                "statistics",
                "window_analysis",
            ),
        ],
        ["false_structural_peak", "loop", "reduction", "hard_negative"],
        [
            SegmentTruth("statistics", 1, 13),
            SegmentTruth("window_analysis", 14, 16),
        ],
    )


def _function_handle_project(rng: random.Random) -> GeneratedSample:
    mode = rng.choice(("fft", "abs", "sqrt", "conj"))
    helper = """function [transformed, metric] = applyTransform(values, transform)\ntransformed = transform(values);\nmetric = mean(abs(transformed));\nend\n"""
    lines = [
        "data = randn(1, 128);",
        f"transform = @{mode};",
        "[transformed, metric] = applyTransform(data, transform);",
        "centered = transformed - mean(transformed);",
        "energy = sum(abs(centered).^2);",
        "normalizedEnergy = energy / length(centered);",
        "result = [metric, normalizedEnergy];",
        "disp(result);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                3,
                BoundaryLabel.PREFERRED,
                "external transform module completes before metric normalization",
                "transform",
                "normalize_metric",
            ),
            BoundaryTruth(5, BoundaryLabel.DISCOURAGED, "energy normalization is incomplete"),
            BoundaryTruth(7, BoundaryLabel.DISCOURAGED, "display belongs to report"),
        ],
        ["multi_file", "function_handle", "indirect_call", "multi_output"],
        [
            SegmentTruth("transform", 1, 3, extraction_safe=False),
            SegmentTruth("normalize_metric", 4, 8),
        ],
        {"applyTransform.m": helper},
    )


def _adversarial_twin_peaks(rng: random.Random) -> GeneratedSample:
    decay = rng.choice((0.7, 0.8, 0.9))
    lines = [
        "values = randn(1, 256);",
        "state = zeros(size(values));",
        "for index = 2:length(values)",
        f"    state(index) = {decay} * state(index - 1) + values(index);",
        "end",
        "stateMean = mean(state);",
        "stateStd = std(state);",
        "normalized = (state - stateMean) / stateStd;",
        "spectrum = abs(fft(normalized));",
        "for bin = 2:length(spectrum)",
        "    spectrum(bin) = max(spectrum(bin), spectrum(bin - 1));",
        "end",
        "peak = max(spectrum);",
        "location = find(spectrum == peak, 1);",
        "result = [peak, location];",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                5,
                BoundaryLabel.DISCOURAGED,
                "first loop has a strong structural peak but normalization is unfinished",
            ),
            BoundaryTruth(
                8,
                BoundaryLabel.PREFERRED,
                "normalization completes before spectral analysis",
                "normalize",
                "spectrum",
            ),
            BoundaryTruth(
                12,
                BoundaryLabel.ACCEPTABLE,
                "second loop completes before peak reporting",
            ),
        ],
        ["adversarial", "twin_peaks", "false_structural_peak", "two_loops"],
        [
            SegmentTruth("normalize", 1, 8),
            SegmentTruth("spectrum", 9, 12),
            SegmentTruth("report", 13, 15),
        ],
    )


def _adversarial_large_interface(rng: random.Random) -> GeneratedSample:
    factor = rng.choice((1.5, 2.0, 2.5, 3.0))
    lines = [
        "rawA = randn(1, 300);",
        "rawB = randn(1, 300);",
        "centerA = mean(rawA);",
        "centerB = mean(rawB);",
        "scaleA = std(rawA);",
        "scaleB = std(rawB);",
        "normA = (rawA - centerA) / scaleA;",
        "normB = (rawB - centerB) / scaleB;",
        f"mixFactor = {factor};",
        "sumSignal = normA + mixFactor * normB;",
        "difference = normA - normB;",
        "product = normA .* normB;",
        "combined = [sumSignal; difference; product];",
        "covariance = combined * combined' / size(combined, 2);",
        "eigenvalues = eig(covariance);",
        "score = sum(eigenvalues);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                9,
                BoundaryLabel.PREFERRED,
                "two-channel preparation ends despite a deliberately large explicit interface",
                "prepare_channels",
                "combine_channels",
            ),
            BoundaryTruth(
                12,
                BoundaryLabel.DISCOURAGED,
                "three related combination outputs belong to the same phase",
            ),
            BoundaryTruth(
                14, BoundaryLabel.ACCEPTABLE, "matrix construction ends before eigenscore"
            ),
        ],
        ["adversarial", "large_interface", "multi_input", "multi_output"],
        [
            SegmentTruth("prepare_channels", 1, 9),
            SegmentTruth("combine_channels", 10, 14),
            SegmentTruth("score", 15, 16),
        ],
    )


def _composed_pipeline(rng: random.Random) -> GeneratedSample:
    """Compose independently variable phases instead of perturbing one fixed template."""
    lines: list[str] = []
    boundaries: list[BoundaryTruth] = []
    segments: list[SegmentTruth] = []

    def phase(module_id: str, phase_lines: list[str], *, extraction_safe: bool = True) -> None:
        start = len(lines) + 1
        lines.extend(phase_lines)
        end = len(lines)
        segments.append(SegmentTruth(module_id, start, end, extraction_safe=extraction_safe))

    source_variant = rng.choice(
        (
            ["sampleCount = 512;", "raw = randn(1, sampleCount);"],
            ["sampleCount = 256;", "time = linspace(0, 1, sampleCount);", "raw = sin(8*pi*time);"],
            ["load input.mat", "raw = inputSignal(:)';"],
        )
    )
    phase("acquire", source_variant, extraction_safe=source_variant[0] != "load input.mat")
    boundaries.append(
        BoundaryTruth(len(lines), BoundaryLabel.PREFERRED, "acquisition phase is complete")
    )

    preparation_variant = rng.choice(
        (
            ["offset = mean(raw);", "prepared = raw - offset;"],
            [
                "offset = median(raw);",
                "spread = median(abs(raw - offset));",
                "prepared = (raw - offset) / max(spread, eps);",
            ],
            ["prepared = detrend(raw);", "prepared = prepared / max(abs(prepared));"],
        )
    )
    preparation_start = len(lines) + 1
    phase("prepare", preparation_variant)
    if len(preparation_variant) > 1:
        boundaries.append(
            BoundaryTruth(
                preparation_start,
                BoundaryLabel.DISCOURAGED,
                "preparation intermediate is still required",
            )
        )
    boundaries.append(
        BoundaryTruth(len(lines), BoundaryLabel.PREFERRED, "prepared representation is complete")
    )

    if rng.choice((True, False)):
        analysis_variant = [
            "spectrum = abs(fft(prepared));",
            "threshold = median(spectrum);",
            "selected = spectrum(spectrum > threshold);",
            "metric = mean(selected);",
        ]
    else:
        analysis_variant = [
            "state = zeros(size(prepared));",
            "for index = 2:length(prepared)",
            "    state(index) = 0.8 * state(index - 1) + prepared(index);",
            "end",
            "metric = mean(abs(state));",
        ]
    phase("analyze", analysis_variant)
    boundaries.append(
        BoundaryTruth(len(lines), BoundaryLabel.PREFERRED, "analysis result is finalized")
    )

    output_start = len(lines) + 1
    phase(
        "report",
        rng.choice(
            (
                ["result = [metric, max(prepared)];", "disp(result);"],
                ["result = metric;", "fprintf('metric=%g\\n', result);"],
                ["result = metric;", "save output.mat result"],
            )
        ),
        extraction_safe=False,
    )
    boundaries.append(
        BoundaryTruth(output_start, BoundaryLabel.DISCOURAGED, "terminal output belongs to report")
    )
    return GeneratedSample(
        "\n".join(lines) + "\n",
        boundaries,
        ["composed", "multi_phase", "variable_topology"],
        segments,
    )


def _branch_merge_finalize(rng: random.Random) -> GeneratedSample:
    cutoff = rng.choice((0.0, 0.1, 0.25))
    lines = [
        "raw = randn(1, 256);",
        f"cutoff = {cutoff};",
        "if mean(raw) > cutoff",
        "    prepared = detrend(raw);",
        "else",
        "    prepared = raw - median(raw);",
        "end",
        "scale = max(abs(prepared));",
        "normalized = prepared / max(scale, eps);",
        "spectrum = abs(fft(normalized));",
        "peak = max(spectrum);",
        "disp(peak);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(7, BoundaryLabel.DISCOURAGED, "branch output still needs finalization"),
            BoundaryTruth(
                9,
                BoundaryLabel.PREFERRED,
                "all branch definitions are normalized before spectral analysis",
            ),
            BoundaryTruth(11, BoundaryLabel.DISCOURAGED, "display belongs to report"),
        ],
        ["pdg", "branch_merge", "alternative_definitions", "finalization"],
        [SegmentTruth("prepare", 1, 9), SegmentTruth("analyze", 10, 12)],
    )


def _loop_carried_branch(rng: random.Random) -> GeneratedSample:
    decay = rng.choice((0.65, 0.75, 0.85, 0.95))
    lines = [
        "values = randn(1, 300);",
        "state = zeros(size(values));",
        "accepted = 0;",
        "for index = 2:length(values)",
        "    if values(index) >= 0",
        f"        state(index) = {decay} * state(index - 1) + values(index);",
        "        accepted = accepted + 1;",
        "    else",
        "        state(index) = state(index - 1);",
        "    end",
        "end",
        "tail = state(20:end);",
        "energy = sum(tail.^2);",
        "meanEnergy = energy / max(accepted, 1);",
        "feature = [meanEnergy, max(tail)];",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(11, BoundaryLabel.DISCOURAGED, "loop-carried state needs reduction"),
            BoundaryTruth(13, BoundaryLabel.DISCOURAGED, "energy normalization is incomplete"),
            BoundaryTruth(14, BoundaryLabel.PREFERRED, "loop result is fully finalized"),
        ],
        ["pdg", "loop_carried", "nested_branch", "reduction"],
        [SegmentTruth("track", 1, 14), SegmentTruth("feature", 15, 15)],
    )


def _conditional_postprocess(rng: random.Random) -> GeneratedSample:
    gain = rng.choice((1.5, 2.0, 3.0))
    lines = [
        "input = randn(1, 512);",
        "baseline = mean(input);",
        "centered = input - baseline;",
        "if std(centered) > 1",
        f"    adjusted = centered / {gain};",
        "else",
        f"    adjusted = centered * {gain};",
        "end",
        "if max(abs(adjusted)) > 2",
        "    clipped = max(min(adjusted, 2), -2);",
        "else",
        "    clipped = adjusted;",
        "end",
        "score = mean(abs(clipped));",
        "result = [score, std(clipped)];",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                3, BoundaryLabel.DISCOURAGED, "conditional adjustment is part of preparation"
            ),
            BoundaryTruth(8, BoundaryLabel.DISCOURAGED, "second conditional consumes merged value"),
            BoundaryTruth(13, BoundaryLabel.PREFERRED, "conditional preparation is complete"),
        ],
        ["pdg", "two_branch_merges", "conditional_postprocess"],
        [SegmentTruth("prepare", 1, 13), SegmentTruth("summarize", 14, 15)],
    )


def _nested_state_machine(rng: random.Random) -> GeneratedSample:
    limit = rng.choice((0.5, 0.75, 1.0))
    lines = [
        "samples = randn(1, 240);",
        "state = 0;",
        "output = zeros(size(samples));",
        f"limit = {limit};",
        "for index = 1:length(samples)",
        "    if state == 0",
        "        if samples(index) > limit",
        "            state = 1;",
        "        end",
        "    else",
        "        output(index) = samples(index);",
        "        if samples(index) < 0",
        "            state = 0;",
        "        end",
        "    end",
        "end",
        "active = output(output ~= 0);",
        "duration = length(active);",
        "magnitude = mean(abs(active));",
        "summary = [duration, magnitude];",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(16, BoundaryLabel.PREFERRED, "state-machine traversal is complete"),
            BoundaryTruth(18, BoundaryLabel.DISCOURAGED, "summary aggregation is incomplete"),
        ],
        ["pdg", "nested_control", "state_machine", "loop_carried"],
        [SegmentTruth("state_machine", 1, 16), SegmentTruth("summary", 17, 20)],
    )


def _mixed_project_control(rng: random.Random) -> GeneratedSample:
    width = rng.choice((8, 16, 32))
    helper = """function output = selectMode(values, useMedian)
if useMedian
    output = values - median(values);
else
    output = detrend(values);
end
end
"""
    lines = [
        "raw = randn(1, 256);",
        "useMedian = mean(raw) > 0;",
        "prepared = selectMode(raw, useMedian);",
        f"width = {width};",
        "blocks = floor(length(prepared) / width);",
        "scores = zeros(1, blocks);",
        "for block = 1:blocks",
        "    range = (block - 1) * width + (1:width);",
        "    scores(block) = mean(abs(prepared(range)));",
        "end",
        "best = max(scores);",
        "disp(best);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(
                3, BoundaryLabel.PREFERRED, "external branch helper finishes preparation"
            ),
            BoundaryTruth(10, BoundaryLabel.PREFERRED, "block aggregation is complete"),
            BoundaryTruth(11, BoundaryLabel.DISCOURAGED, "display belongs to report"),
        ],
        ["pdg", "multi_file", "branch_helper", "loop"],
        [
            SegmentTruth("prepare", 1, 3, extraction_safe=False),
            SegmentTruth("aggregate", 4, 10),
            SegmentTruth("report", 11, 12),
        ],
        {"selectMode.m": helper},
    )


def _heldout_branch_loop(rng: random.Random) -> GeneratedSample:
    threshold = rng.choice((0.2, 0.4, 0.6))
    lines = [
        "left = randn(1, 200);",
        "right = randn(1, 200);",
        f"threshold = {threshold};",
        "combined = zeros(size(left));",
        "for index = 1:length(left)",
        "    if abs(left(index)) > threshold",
        "        combined(index) = left(index);",
        "    else",
        "        combined(index) = right(index);",
        "    end",
        "end",
        "offset = mean(combined);",
        "spread = std(combined);",
        "normalized = (combined - offset) / max(spread, eps);",
        "positive = normalized(normalized >= 0);",
        "negative = normalized(normalized < 0);",
        "balance = length(positive) - length(negative);",
    ]
    return GeneratedSample(
        "\n".join(lines) + "\n",
        [
            BoundaryTruth(11, BoundaryLabel.DISCOURAGED, "loop merge still needs normalization"),
            BoundaryTruth(14, BoundaryLabel.PREFERRED, "normalization finishes before partition"),
            BoundaryTruth(16, BoundaryLabel.DISCOURAGED, "both partitions feed balance"),
        ],
        ["pdg", "heldout_topology", "loop_branch_merge", "partition"],
        [SegmentTruth("normalize", 1, 14), SegmentTruth("partition", 15, 17)],
    )
