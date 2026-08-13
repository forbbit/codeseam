from __future__ import annotations

import argparse
import json
from pathlib import Path

from codeseam.core.scoring_artifact import load_selection_config
from codeseam.evaluation.real_gold_audit import write_real_gold_audit
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
    corpus = subparsers.add_parser("corpus", help="audit or train the finalized gold corpus")
    corpus_subparsers = corpus.add_subparsers(dest="corpus_command", required=True)
    audit_real = corpus_subparsers.add_parser(
        "audit-real-gold", help="audit finalized real-code training truth without training"
    )
    audit_real.add_argument("output", type=Path)
    audit_real.add_argument("--json", type=Path, required=True, dest="json_path")
    formal_train = corpus_subparsers.add_parser(
        "train-formal", help="run sealed real-gold training with validation early stopping"
    )
    formal_train.add_argument("output", type=Path)
    formal_train.add_argument("--artifact", type=Path, required=True)
    formal_train.add_argument("--epochs", type=int, default=50)
    formal_train.add_argument("--batch-size", type=int, default=8)
    formal_train.add_argument("--learning-rate", type=float, default=0.01)
    formal_train.add_argument("--seed", type=int, default=1729)
    formal_train.add_argument("--patience", type=int, default=10)
    formal_train.add_argument("--minimum-epochs", type=int, default=15)
    formal_train.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    formal_train.add_argument("--temperature", type=float, default=1.0)
    formal_train.add_argument("--boundary-aux-weight", type=float, default=0.5)
    formal_train.add_argument("--final-boundary-aux-weight", type=float, default=0.5)
    formal_train.add_argument("--final-learning-rate-ratio", type=float, default=1.0)
    formal_train.add_argument("--schedule-epochs", type=int, default=50)
    sealed_test = corpus_subparsers.add_parser(
        "open-sealed-test", help="evaluate a frozen formal model on test exactly once"
    )
    sealed_test.add_argument("output", type=Path)
    sealed_test.add_argument("--artifact", type=Path, required=True)
    sealed_test.add_argument("--report", type=Path, required=True)
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
    parser.add_argument("--structured-model", type=Path)


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
        if args.corpus_command == "audit-real-gold":
            report = write_real_gold_audit(args.output, args.json_path)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["passed"] else 1
        if args.corpus_command == "train-formal":
            from codeseam.training.config import TrainingConfig
            from codeseam.training.protocol import train_formal

            def print_epoch(event: dict[str, object]) -> None:
                marker = " *best*" if event["improved"] else ""
                print(
                    f"epoch {event['epoch']:>3}/{event['epochs']} | "
                    f"updates {event['optimizer_updates']:>4} | "
                    f"lr {event['learning_rate']:.5f} | "
                    f"aux_w {event['boundary_auxiliary_weight']:.3f} | "
                    f"train_nll/n {event['train_normalized_structured_nll']:.4f} | "
                    f"val_nll/n {event['validation_normalized_structured_nll']:.4f} | "
                    f"val_f1 {event['validation_f1_exact']:.3f} | "
                    f"val_f1@1 {event['validation_f1_tolerance_1']:.3f} | "
                    f"cuts {event['validation_predicted_cuts']}/"
                    f"{event['validation_truth_cuts']} | "
                    f"stale {event['stale_epochs']}/"
                    f"{event['early_stopping_patience']}{marker}",
                    flush=True,
                )

            result = train_formal(
                args.output,
                args.artifact,
                config=TrainingConfig(
                    epochs=args.epochs,
                    batch_size=args.batch_size,
                    learning_rate=args.learning_rate,
                    random_seed=args.seed,
                    early_stopping_patience=args.patience,
                    minimum_epochs=args.minimum_epochs,
                    device=args.device,
                    soft_dp_temperature=args.temperature,
                    boundary_auxiliary_weight=args.boundary_aux_weight,
                    final_boundary_auxiliary_weight=args.final_boundary_aux_weight,
                    final_learning_rate_ratio=args.final_learning_rate_ratio,
                    schedule_epochs=args.schedule_epochs,
                ),
                progress=print_epoch,
            )
            print(json.dumps(result["selection"], indent=2, sort_keys=True))
            print(f"Wrote frozen formal model: {args.artifact}")
            print("Test split remains sealed and was not loaded.")
            return 0
        if args.corpus_command == "open-sealed-test":
            from codeseam.training.protocol import evaluate_sealed_test

            result = evaluate_sealed_test(args.output, args.artifact, args.report)
            print(json.dumps(result["test_metrics"], indent=2, sort_keys=True))
            print(f"Wrote sealed test report: {args.report}")
            return 0
    try:
        scoring_config = (
            load_selection_config(args.selection_policy) if args.selection_policy else None
        )
        project_index = (
            MatlabProjectIndex.from_json(args.project_index) if args.project_index else None
        )
        if args.structured_model:
            from codeseam.core.structured_analyzer import analyze_program_structured
            from codeseam.core.structured_energy import StructuredScorer
            from codeseam.languages.matlab import MatlabFrontend
            from codeseam.training.protocol import load_formal_artifact

            model = StructuredScorer()
            load_formal_artifact(args.structured_model, model)
            program = MatlabFrontend().analyze_source(args.file.read_bytes(), str(args.file))
            result = analyze_program_structured(program, model).result
        else:
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
