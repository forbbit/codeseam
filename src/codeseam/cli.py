from __future__ import annotations

import argparse
import json
from pathlib import Path

from codeseam.corpus.ablation import ablation_report
from codeseam.corpus.annotations import (
    agreement,
    create_annotation_template,
    validate_annotation,
)
from codeseam.corpus.generator import audit_corpus, evaluate_corpus, generate_corpus
from codeseam.corpus.real_projects import fetch_projects, validate_registry
from codeseam.corpus.selection_tuning import load_selection_config, tune_selection
from codeseam.corpus.training import evaluate_weight_artifact, train_weights
from codeseam.languages.matlab.project import MatlabProjectIndex, scan_matlab_project
from codeseam.reporting.console import render_analysis, render_explanation
from codeseam.reporting.json_report import write_json
from codeseam.service import analyze_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codeseam")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="analyze all legal boundaries")
    _common_arguments(analyze)
    analyze.add_argument("--json", type=Path, dest="json_path")
    explain = subparsers.add_parser("explain", help="explain one source boundary")
    _common_arguments(explain)
    explain.add_argument("--after-line", type=int, required=True)
    explain.add_argument("--region", help="region id when line numbers are ambiguous")
    project = subparsers.add_parser("project-scan", help="index a MATLAB project")
    project.add_argument("root", type=Path)
    project.add_argument("--json", type=Path, dest="json_path")
    corpus = subparsers.add_parser("corpus", help="generate or audit supervised MATLAB corpus")
    corpus_subparsers = corpus.add_subparsers(dest="corpus_command", required=True)
    generate = corpus_subparsers.add_parser("generate", help="generate deterministic samples")
    generate.add_argument("output", type=Path)
    generate.add_argument("--count", type=int, default=40)
    generate.add_argument("--seed", type=int, default=1729)
    audit = corpus_subparsers.add_parser(
        "audit", help="verify manifest, hashes, parses, and labels"
    )
    audit.add_argument("output", type=Path)
    evaluate = corpus_subparsers.add_parser("evaluate", help="measure frozen-weight baseline")
    evaluate.add_argument("output", type=Path)
    evaluate.add_argument("--split", choices=("train", "validation", "test"))
    evaluate.add_argument("--tolerance", type=int, default=2)
    evaluate.add_argument("--selection-policy", type=Path)
    train = corpus_subparsers.add_parser("train", help="fit explainable non-negative weights")
    train.add_argument("output", type=Path, help="generated corpus directory")
    train.add_argument("--artifact", type=Path, required=True)
    registry = corpus_subparsers.add_parser("registry", help="validate real-project registry")
    registry.add_argument("path", type=Path)
    fetch = corpus_subparsers.add_parser("fetch-real", help="fetch pinned licensed projects")
    fetch.add_argument("registry", type=Path)
    fetch.add_argument("output", type=Path)
    annotate = corpus_subparsers.add_parser("annotate", help="create full boundary template")
    annotate.add_argument("source", type=Path)
    annotate.add_argument("output", type=Path)
    annotate.add_argument("--annotator", required=True)
    validate = corpus_subparsers.add_parser("validate-annotation")
    validate.add_argument("annotation", type=Path)
    validate.add_argument("source", type=Path)
    compare = corpus_subparsers.add_parser("agreement", help="compare two annotations")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    ablation = corpus_subparsers.add_parser("ablation", help="compare legacy and expanded features")
    ablation.add_argument("output", type=Path)
    ablation.add_argument("--split", choices=("train", "validation", "test"), default="test")
    tune_selector = corpus_subparsers.add_parser(
        "tune-selection", help="tune selector on non-test families"
    )
    tune_selector.add_argument("output", type=Path)
    tune_selector.add_argument("--artifact", type=Path, required=True)
    tune_selector.add_argument("--tolerance", type=int, default=2)
    tune_selector.add_argument("--weights", type=Path, dest="weights_artifact")
    return parser


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path)
    parser.add_argument("--window", type=int, default=4)
    parser.add_argument("--threshold", type=float, default=0.58)
    parser.add_argument("--min-prominence", type=float, default=0.055)
    parser.add_argument("--prominence-radius", type=int, default=5)
    parser.add_argument("--boundary-reward-weight", type=float, default=0.85)
    parser.add_argument("--cut-penalty", type=float, default=0.03)
    parser.add_argument("--selection-policy", type=Path)
    parser.add_argument("--project-index", type=Path)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "project-scan":
        try:
            index = scan_matlab_project(args.root)
        except (OSError, ValueError) as error:
            raise SystemExit(f"error: {error}") from error
        resolved = sum(len(item.resolved_project_calls) for item in index.files)
        print(f"MATLAB files: {len(index.files)}")
        print(f"Project symbols: {len(index.providers)}")
        print(f"Resolved project calls: {resolved}")
        if args.json_path:
            index.write_json(args.json_path)
        return 0
    if args.command == "corpus":
        if args.corpus_command == "registry":
            errors = validate_registry(args.path)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}")
                return 1
            print(f"Registry validation passed: {args.path}")
            return 0
        if args.corpus_command == "fetch-real":
            projects = fetch_projects(args.registry, args.output)
            print(f"Fetched {len(projects)} pinned projects into {args.output}")
            return 0
        if args.corpus_command == "annotate":
            document = create_annotation_template(args.source, args.output, args.annotator)
            print(f"Wrote {len(document['boundaries'])} boundaries: {args.output}")
            return 0
        if args.corpus_command == "validate-annotation":
            errors = validate_annotation(args.annotation, args.source)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}")
                return 1
            print(f"Annotation validation passed: {args.annotation}")
            return 0
        if args.corpus_command == "agreement":
            for name, value in agreement(args.left, args.right).items():
                rendered = f"{value:.3f}" if isinstance(value, float) else str(value)
                print(f"{name}: {rendered}")
            return 0
        if args.corpus_command == "ablation":
            report = ablation_report(args.output, args.split)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.corpus_command == "tune-selection":
            report = tune_selection(
                args.output,
                args.artifact,
                tolerance=args.tolerance,
                weights_artifact=args.weights_artifact,
            )
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.corpus_command == "generate":
            records = generate_corpus(args.output, count=args.count, seed=args.seed)
            counts: dict[str, int] = {}
            for record in records:
                counts[record.split] = counts.get(record.split, 0) + 1
            summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
            print(f"Generated {len(records)} samples at {args.output} ({summary})")
            return 0
        if args.corpus_command == "evaluate":
            scoring_config = (
                load_selection_config(args.selection_policy) if args.selection_policy else None
            )
            report = evaluate_corpus(
                args.output,
                args.split,
                tolerance=args.tolerance,
                scoring_config=scoring_config,
            )
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.corpus_command == "train":
            artifact = train_weights(args.output, args.artifact)
            print(f"Wrote weights: {args.artifact}")
            for name, value in artifact["metrics"].items():
                print(f"{name}: {value:.3f}" if isinstance(value, float) else f"{name}: {value}")
            if any(record.get("split") == "test" for record in _read_manifest(args.output)):
                score = evaluate_weight_artifact(args.output, args.artifact, "test")
                print(f"held_out_test_pairwise_accuracy: {score:.3f}")
            return 0
        errors = audit_corpus(args.output)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print(f"Corpus audit passed: {args.output}")
        return 0
    try:
        scoring_config = (
            load_selection_config(args.selection_policy) if args.selection_policy else None
        )
        project_index = (
            MatlabProjectIndex.from_json(args.project_index) if args.project_index else None
        )
        result = analyze_file(
            args.file,
            window=args.window,
            threshold=args.threshold,
            minimum_prominence=args.min_prominence,
            prominence_radius=args.prominence_radius,
            boundary_reward_weight=args.boundary_reward_weight,
            cut_penalty=args.cut_penalty,
            scoring_config=scoring_config,
            project_index=project_index,
        )
    except (OSError, ValueError) as error:
        raise SystemExit(f"error: {error}") from error
    if args.command == "analyze":
        print(render_analysis(result))
        if args.json_path:
            write_json(result, args.json_path)
        return 0
    matches = [
        item
        for item in result.boundaries
        if item.after_line == args.after_line
        and (args.region is None or item.region_id == args.region)
    ]
    if not matches:
        raise SystemExit("error: no legal boundary found after that line")
    if len(matches) > 1:
        regions = ", ".join(item.region_id for item in matches)
        raise SystemExit(f"error: boundary is ambiguous; choose --region from: {regions}")
    print(render_explanation(matches[0]))
    return 0


def _read_manifest(path: Path) -> list[dict]:
    import json

    return [json.loads(line) for line in (path / "manifest.jsonl").read_text().splitlines()]
