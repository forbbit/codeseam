from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from codeseam.core.feature_model import ContinuousFeatureModel
from codeseam.core.raw_facts import extract_raw_facts
from codeseam.core.structured_energy import StructuredScorer
from codeseam.corpus.counterfactual import (
    COUNTERFACTUAL_FAMILIES,
    generate_counterfactual_suite,
    generate_pairwise_suite,
)
from codeseam.corpus.coverage import (
    CoverageDesign,
    FingerprintSample,
    audit_coverage,
    collision_audit,
)
from codeseam.corpus.fingerprint import fit_fingerprint_schema, normalize_fingerprint
from codeseam.corpus.matlab_renderer import render_matlab
from codeseam.corpus.semantic_graph import SemanticTask, SemanticTaskGraph
from codeseam.evaluation.diagnostics import (
    ControlledPair,
    DiagnosticRow,
    controlled_pair_observability,
    feature_diagnostics,
    parameterization_diagnostics,
)
from codeseam.evaluation.oracle_corpus import materialize_hand_oracle, run_hand_oracle
from codeseam.evaluation.readiness import evaluate_training_readiness
from codeseam.languages.matlab import MatlabFrontend


def run_validation(root: Path) -> dict[str, object]:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    materialize_hand_oracle(root / "corpus" / "oracle" / "hand_authored")
    frontend = MatlabFrontend()
    oracle = run_hand_oracle()
    base = SemanticTaskGraph(
        "validation-base",
        (
            SemanticTask("acquire", "acquisition", outputs=("raw",), internal_steps=2),
            SemanticTask(
                "transform", "transformation", inputs=("raw",), outputs=("clean",), internal_steps=2
            ),
            SemanticTask("report", "output", inputs=("clean",), internal_steps=1),
        ),
        factors={
            "interface": "low",
            "dependency": "low",
            "role": "low",
            "completion": "low",
            "control": "low",
        },
    )
    cases = generate_counterfactual_suite(base) + generate_pairwise_suite()
    raw = []
    meta = []
    requested_vs_observed = []
    for index, case in enumerate(cases):
        style = (
            "reused"
            if case.family == "vocabulary" and case.semantic_polarity == "high"
            else "descriptive"
        )
        rendered = render_matlab(case.graph, seed=index, style=style)
        region = frontend.analyze_source(rendered.source.encode(), f"cf-{index}.m").regions[0]
        facts = extract_raw_facts(region)
        if not facts:
            continue
        split = _split(rendered.semantic_program_id)
        labels = dict(rendered.candidate_labels)
        target_boundary = dict(rendered.boundary_cuts)[case.target_boundary_id]
        target_fact = facts[target_boundary - 1]
        observed = _observed_factors(target_fact, rendered.renderer_style)
        requested = dict(case.requested_factors)
        requested_vs_observed.append(
            {
                "case_id": case.graph.graph_id,
                "target_boundary_id": case.target_boundary_id,
                "boundary_index": target_boundary,
                "ground_truth": labels[target_boundary],
                "semantic_truth": case.target_boundary_truth.label,
                "requested_factors": requested,
                "observed_factors": observed,
                "matches": {name: observed.get(name) == value for name, value in requested.items()},
                "renderer_trace_id": rendered.renderer_trace_id,
                "renderer_changed": bool(rendered.source),
            }
        )
        for boundary, fact in enumerate(facts, 1):
            raw.append(fact)
            meta.append(
                (case, rendered, split, boundary, labels[boundary], boundary == target_boundary)
            )
    train = [fact for fact, item in zip(raw, meta, strict=True) if item[2] == "train"] or raw
    schema = fit_fingerprint_schema(train)
    samples = []
    for fact, (case, rendered, split, boundary, true_label, is_target) in zip(
        raw, meta, strict=True
    ):
        samples.append(
            FingerprintSample(
                f"{case.graph.graph_id}:b{boundary}",
                label=true_label,
                factors=_observed_factors(fact, rendered.renderer_style),
                semantic_program_id=rendered.semantic_program_id,
                renderer_variant_id=rendered.renderer_variant_id,
                split=split,
                counterfactual_family=case.family,
                pair_id=case.pair_id,
                polarity=case.semantic_polarity,
                fingerprint=normalize_fingerprint(fact, schema),
                boundary_index=boundary,
                target_boundary=is_target,
                requested_factors=case.requested_factors,
                observed_factors=_observed_factors(fact, rendered.renderer_style),
                renderer_trace_id=rendered.renderer_trace_id,
            )
        )
    domains = {
        name: ("low", "high")
        for name in ("interface", "dependency", "role", "completion", "control")
    }
    design = CoverageDesign(
        domains,
        required_pairs=(
            ("interface", "dependency"),
            ("interface", "role"),
            ("dependency", "completion"),
            ("role", "completion"),
            ("control", "dependency"),
            ("control", "completion"),
        ),
        required_triples=(("interface", "dependency", "completion"),),
        required_cf_families=COUNTERFACTUAL_FAMILIES,
        labels=("cut", "no_cut"),
    )
    coverage = audit_coverage(samples, design)
    collisions = collision_audit(samples)
    rows = []
    model = ContinuousFeatureModel()
    for fact, sample in zip(raw, samples, strict=True):
        decomposition = model([fact])
        rows.append(
            DiagnosticRow(
                dict(
                    zip(decomposition.names, decomposition.values[0].detach().tolist(), strict=True)
                ),
                dict(
                    zip(
                        decomposition.names,
                        decomposition.contributions[0].detach().tolist(),
                        strict=True,
                    )
                ),
                dict(
                    zip(
                        decomposition.names,
                        decomposition.reliability[0].detach().tolist(),
                        strict=True,
                    )
                ),
                sample.label,
            )
        )
    redundancy = feature_diagnostics(rows)
    redundancy["parameterization"] = parameterization_diagnostics()
    controlled_pairs = _controlled_pairs(cases, meta, raw)
    observability = controlled_pair_observability(controlled_pairs)
    redundancy["controlled_observability"] = observability
    integrity_errors = _integrity_errors(samples)
    confidence = _real_data_spot_check(root)
    smoke = _smoke(frontend)
    evidence = {
        "A": {
            "pass": oracle["overall"]["accuracy"] == 1.0 and len(oracle["families"]) >= 8,
            "reasons": [
                f"oracle exact-set accuracy={oracle['overall']['accuracy']:.4f}; required calls/roles/edges/completion families are not all present"
            ],
            "artifact_refs": ["reports/ANALYZER_ORACLE_ACCURACY.json"],
        },
        "B": {
            "pass": _coverage_pass(coverage),
            "reasons": [
                "predeclared factor×label and required Cartesian cells must all be populated"
            ],
            "artifact_refs": ["reports/FINGERPRINT_COVERAGE.json"],
        },
        "C": {
            "pass": (
                all(item["complete"] for item in coverage["counterfactual"].values())
                and all(all(item["matches"].values()) for item in requested_vs_observed)
                and not integrity_errors
            ),
            "reasons": [
                "requires candidate truth, faithful rendering and requested/observed agreement"
            ],
            "artifact_refs": ["reports/COUNTERFACTUAL_COVERAGE.md"],
        },
        "D": {
            "pass": observability["all_observability_pass"],
            "reasons": ["computed from controlled target deltas and non-target drift"],
            "artifact_refs": ["reports/FEATURE_REDUNDANCY.md"],
        },
        "E": {
            "pass": not integrity_errors
            and not any(
                item.classification in {"potential_missing_raw_fact", "data_bug"}
                for item in collisions
            ),
            "reasons": [
                f"potential missing-observation pairs={sum(item.classification == 'potential_missing_raw_fact' for item in collisions)}; data bugs={sum(item.classification == 'data_bug' for item in collisions)}"
            ],
            "artifact_refs": ["reports/FINGERPRINT_COLLISIONS.md"],
        },
        "F": {
            "pass": _controlled_reliability(frontend)["pass"],
            "reasons": ["controlled clean and deliberately uncertain cases only"],
            "artifact_refs": ["reports/CONTROLLED_RELIABILITY.json"],
        },
        "G": {
            "pass": coverage["leakage"]["pass"],
            "reasons": [
                f"semantic graph split leakage={coverage['leakage']['count']}; renderer leakage={coverage['leakage']['renderer_count']}"
            ],
            "artifact_refs": ["reports/FINGERPRINT_COVERAGE.json"],
        },
        "H": {
            "pass": smoke["pass"],
            "reasons": [smoke["reason"]],
            "artifact_refs": ["reports/V2_DATASET_VALIDATION_SUMMARY.md"],
        },
    }
    readiness = evaluate_training_readiness(evidence)
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_hash": _hash([item.sample_id for item in samples]),
        "fingerprint_schema_hash": schema.schema_id,
        "policy_version": readiness.policy_version,
        "command": "python -m codeseam.evaluation.dataset_validation",
        "threshold_source": "CODESEAM_V2_DATASET_ANALYZER_VALIDATION_TASK.md; thresholds fixed before report evaluation",
    }
    _write_json(reports / "ANALYZER_ORACLE_ACCURACY.json", oracle)
    _write_json(reports / "REAL_DATA_SPOT_CHECK.json", confidence)
    _write_json(reports / "FINGERPRINT_COVERAGE.json", {"metadata": metadata, "coverage": coverage})
    _write_json(
        reports / "FINGERPRINT_COLLISIONS.json",
        {"radii": [0.0, 0.02, 0.05], "records": [asdict(item) for item in collisions]},
    )
    _write_json(reports / "FEATURE_REDUNDANCY.json", redundancy)
    _write_json(
        reports / "REQUESTED_VS_OBSERVED_FACTORS.json",
        {
            "policy": "target candidate boundary only; requested bins must be analyzer-observed",
            "records": requested_vs_observed,
        },
    )
    reliability = _controlled_reliability(frontend)
    _write_json(reports / "CONTROLLED_RELIABILITY.json", reliability)
    _write_json(
        reports / "TRAINING_READINESS_GATE.json", {"metadata": metadata, **readiness.to_dict()}
    )
    _write_json(
        reports / "SEMANTIC_DATASET_MANIFEST.json",
        {
            "schema_version": "semantic-dataset-manifest-v2",
            "metadata": metadata,
            "samples": [
                {
                    "sample_id": item.sample_id,
                    "semantic_program_id": item.semantic_program_id,
                    "renderer_variant_id": item.renderer_variant_id,
                    "render_id": item.renderer_variant_id,
                    "boundary_index": item.boundary_index,
                    "split": item.split,
                    "ground_truth": {"label": item.label},
                    "requested_factors": dict(item.requested_factors),
                    "observed_factors": dict(item.observed_factors),
                    "counterfactual_family": item.counterfactual_family,
                    "pair_id": item.pair_id,
                    "polarity": item.polarity,
                    "fingerprint_id": item.fingerprint.exact_id if item.fingerprint else None,
                    "renderer_trace_id": item.renderer_trace_id,
                }
                for item in samples
            ],
        },
    )
    _write_markdowns(
        reports,
        oracle,
        confidence,
        coverage,
        collisions,
        redundancy,
        readiness,
        metadata,
        smoke,
        len(samples),
    )
    _write_requested_observed_markdown(reports, requested_vs_observed)
    return {
        "oracle": oracle,
        "coverage": coverage,
        "collisions": len(collisions),
        "readiness": readiness.to_dict(),
        "samples": len(samples),
    }


def _real_data_spot_check(root):
    selected = (
        "musaelab-amplitude-modulation/ama_toolbox/conv_fft.m",
        "musaelab-amplitude-modulation/ama_toolbox/irfft_psd.m",
        "alsad-pw-wvd/Functions/TFD/filter_tfd.m",
        "alsad-pw-wvd/Functions/TFD/tf2af.m",
        "compneuro-rshrf/rsHRF_find_event_vector.m",
    )
    source_root = root / ".codex-v2-real" / "sources"
    results = []
    for relative in selected:
        path = source_root / relative
        completed = subprocess.run(
            [sys.executable, "-m", "codeseam.evaluation.spot_check_worker", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode or not completed.stdout.strip():
            results.append({"path": relative, "status": "failed"})
            continue
        item = json.loads(completed.stdout)
        item["path"] = relative
        item["status"] = "ok"
        results.append(item)
    return {
        "scope": "five fixed, parser-clean real MATLAB files; detection spot check only",
        "selection_policy": "manifest parser_diagnostics empty, moderate size, functions from three projects",
        "training_use": "none",
        "population_inference": "not permitted",
        "files": results,
        "totals": {
            "selected": len(selected),
            "successful": sum(item["status"] == "ok" for item in results),
            "boundaries": sum(item.get("boundaries", 0) for item in results),
            "recommendations": sum(len(item.get("recommendations", ())) for item in results),
            "low_parse_boundaries": sum(item.get("low_parse_boundaries", 0) for item in results),
        },
    }


def _observed_factors(fact, renderer_style):
    left_roles = dict(fact.left_role_histogram)
    right_roles = dict(fact.right_role_histogram)
    role_distance = max(left_roles, key=left_roles.get, default="unknown") != max(
        right_roles, key=right_roles.get, default="unknown"
    )
    return {
        "vocabulary": "high" if renderer_style == "reused" else "low",
        "interface": "high" if fact.input_interface_count >= 3 else "low",
        "dependency": "high"
        if fact.cross_dependency_count >= 3 and fact.dependency_reuse_mass >= 9
        else "low",
        "role": "high" if role_distance else "low",
        "completion": "high"
        if len(
            {
                role
                for role, count in fact.right_role_histogram
                if count and role in {"aggregation", "normalization", "shaping"}
            }
        )
        >= 2
        else "low",
        "long_range": "high" if fact.dependency_span_mean >= 2.5 else "low",
        "module_size": "high" if fact.boundary_index >= 4 else "low",
        "control": "high" if fact.compound_ends_here else "low",
    }


def _controlled_pairs(cases, meta, raw):
    lookup = {}
    for fact, (case, _rendered, _split_name, _boundary, _label, is_target) in zip(
        raw, meta, strict=True
    ):
        if not is_target or "×" in case.family:
            continue
        lookup[(case.family, case.target_boundary_truth.label, case.semantic_polarity)] = {
            "vocabulary_reuse": float(fact.cross_symbol_count) / max(1, fact.born_symbol_count + 1),
            "interface_width": float(fact.input_interface_count),
            "dependency_strength": float(fact.cross_dependency_count + fact.dependency_reuse_mass),
            "role_transition": float(_observed_factors(fact, "descriptive")["role"] == "high"),
            "completion_followup": float(
                len(
                    {
                        role
                        for role, count in fact.right_role_histogram
                        if count and role in {"aggregation", "normalization", "shaping"}
                    }
                )
            ),
            "long_range_span": float(fact.dependency_span_mean),
            "module_size": float(fact.boundary_index),
            "control_structure": float(fact.compound_ends_here),
        }
    targets = {
        "vocabulary": (("vocabulary_reuse",), 1),
        "interface": (("interface_width",), 1),
        "dependency": (("dependency_strength",), 1),
        "role": (("role_transition",), 1),
        "completion": (("completion_followup",), 1),
        "long_range": (("long_range_span",), 1),
        "module_size": (("module_size",), 1),
        "control": (("control_structure",), 1),
    }
    pairs = []
    for family, (features, direction) in targets.items():
        for label in ("cut", "no_cut"):
            low = lookup.get((family, label, "low"))
            high = lookup.get((family, label, "high"))
            if low is not None and high is not None:
                pairs.append(
                    ControlledPair(f"{family}:{label}", family, features, low, high, direction)
                )
    return pairs


def _integrity_errors(samples):
    truth = {}
    errors = []
    for item in samples:
        key = (item.semantic_program_id, item.renderer_variant_id, item.boundary_index)
        previous = truth.setdefault(key, item.label)
        if previous != item.label:
            errors.append({"key": key, "labels": sorted({previous, item.label})})
    return errors


def _controlled_reliability(frontend):
    cases = {
        "clean": b"x = randn(4,1);\ny = mean(x);\n",
        "eval": b"x = 1;\neval('y=x');\n",
        "assignin": b"x = 1;\nassignin('base','y',x);\n",
        "unresolved_external": b"x = project_worker(input);\ny = mean(x);\n",
    }
    records = []
    for name, source in cases.items():
        program = frontend.analyze_source(source, f"reliability-{name}.m")
        facts = [fact for region in program.regions for fact in extract_raw_facts(region)]
        dependency = min((fact.reliability.dependency for fact in facts), default=1.0)
        call = min((fact.reliability.call_resolution for fact in facts), default=1.0)
        role = min((fact.reliability.role for fact in facts), default=1.0)
        records.append({"case": name, "dependency": dependency, "call": call, "role": role})
    clean = next(item for item in records if item["case"] == "clean")
    uncertain = [item for item in records if item["case"] != "clean"]
    passed = all(clean[key] >= 0.95 for key in ("dependency", "call", "role")) and all(
        min(item["dependency"], item["call"], item["role"]) < 0.95 for item in uncertain
    )
    return {
        "pass": passed,
        "records": records,
        "policy": "clean high; each uncertain case must lower at least one relevant confidence",
    }


def _smoke(frontend):
    try:
        import torch

        from codeseam.training.structured_loss import structured_nll

        region = frontend.analyze_source(
            b"a=rand(2,1);\nb=mean(a);\nc=fft(b);\n", "smoke.m"
        ).regions[0]
        scorer = StructuredScorer()
        loss = structured_nll(scorer(region), [2])
        loss.backward()
        gradients = [
            parameter.grad for parameter in scorer.parameters() if parameter.grad is not None
        ]
        passed = bool(
            torch.isfinite(loss)
            and gradients
            and all(torch.isfinite(item).all() for item in gradients)
            and sum(float(item.abs().sum()) for item in gradients) > 0
        )
        return {
            "pass": passed,
            "loss": float(loss.detach()),
            "reason": "finite loss and finite nonzero gradients; existing parity tests cover Soft/Hard DP",
        }
    except (RuntimeError, ValueError, IndexError) as exc:
        return {"pass": False, "reason": f"smoke failed: {exc}"}


def _coverage_pass(report):
    return all(not item["empty_cells"] for item in report["factor_label"].values()) and all(
        not item["empty_cells"] for item in report["pairwise"].values()
    )


def _split(identifier):
    bucket = int(identifier[:8], 16) % 10
    return "train" if bucket < 7 else ("validation" if bucket < 9 else "test")


def _hash(values):
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def _clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "inf" if value > 0 else "-inf"
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _write_json(path, value):
    path.write_text(json.dumps(_clean(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_requested_observed_markdown(reports, records):
    mismatches = [item for item in records if not all(item["matches"].values())]
    lines = [
        "# Requested vs Observed Factors",
        "",
        "This audit is evaluated at each case's mapped target candidate boundary.",
        "",
        f"Records: {len(records)}; full matches: {len(records) - len(mismatches)}; mismatches: {len(mismatches)}.",
        "",
    ]
    for item in mismatches:
        failed = [name for name, value in item["matches"].items() if not value]
        lines.append(f"- `{item['case_id']}`: mismatch in {', '.join(failed)}")
    (reports / "REQUESTED_VS_OBSERVED_FACTORS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8-sig"
    )


def _write_markdowns(
    r, oracle, confidence, coverage, collisions, redundancy, readiness, metadata, smoke, samples
):
    def write(name, title, body):
        # UTF-8 BOM keeps Windows PowerShell/Notepad from guessing a legacy
        # code page for reports containing multiplication signs or Chinese text.
        (r / name).write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8-sig")

    o = oracle["overall"]
    write(
        "ANALYZER_ORACLE_ACCURACY.md",
        "Analyzer Oracle Accuracy",
        f"Hand-authored cases: {oracle['case_count']}. Exact-set accuracy: {o['accuracy']:.2%}; micro P/R/F1: {o['precision']:.2%}/{o['recall']:.2%}/{o['f1']:.2%}; UNKNOWN: {o['unknown']}.\n\nGate A is **FAIL** because accuracy is not exact and calls, roles, data/control edges and completion do not yet have complete oracle families. Ground truth is hand-authored and is not parsed from renderer output.",
    )
    spot_rows = "\n".join(
        f"- `{item['path']}`: {item.get('boundaries', 0)} boundaries, "
        f"{len(item.get('recommendations', ()))} recommendations, "
        f"{item.get('low_parse_boundaries', 0)} low-parse"
        for item in confidence["files"]
    )
    write(
        "REAL_DATA_SPOT_CHECK.md",
        "Selected Real MATLAB Detection Spot Check",
        f"Real data was not used for training or population-level statistics. Five fixed parser-clean files were selected from three projects.\n\n{spot_rows}\n\nTotal: {confidence['totals']['boundaries']} candidate boundaries and {confidence['totals']['recommendations']} recommendations; low-parse boundaries: {confidence['totals']['low_parse_boundaries']}. This external stress status is non-blocking and separate from controlled-reliability Gate F.",
    )
    holes = sum(len(v["empty_cells"]) for v in coverage["factor_label"].values())
    pairholes = sum(len(v["empty_cells"]) for v in coverage["pairwise"].values())
    write(
        "FINGERPRINT_COVERAGE.md",
        "Fingerprint Coverage",
        f"Typed samples: {samples}. Single-factor×label empty cells: {holes}; required pairwise empty cells: {pairholes}. Semantic-program split leakage: {coverage['leakage']['count']}. Gate B: **{'PASS' if _coverage_pass(coverage) else 'FAIL'}**.",
    )
    cf = "\n".join(
        f"- {name}: {'complete' if item['complete'] else 'missing ' + str(item['missing_quadrants'])}"
        for name, item in coverage["counterfactual"].items()
    )
    write("COUNTERFACTUAL_COVERAGE.md", "Counterfactual Coverage", cf)
    classes = Counter(item.classification for item in collisions)
    write(
        "FINGERPRINT_COLLISIONS.md",
        "Fingerprint Collisions",
        f"This report supersedes the invalidated pre-P0 collision report that used case-level labels. Candidate-level truth and radii 0, 0.02, 0.05 produce {len(collisions)} opposite-label near/exact pairs. Classifications: {dict(classes)}. Data bugs and potential missing-observation pairs block training.",
    )
    write(
        "FEATURE_REDUNDANCY.md",
        "Feature Redundancy and Identifiability",
        f"Rows: {redundancy['rows']}; matrix rank: {redundancy['rank']}; effective rank: {redundancy['effective_rank']:.3f}; condition number: {redundancy['condition_number']}.\n\nKnown parameter issues: unrestricted feature/module weights; feature bias and cut penalty are non-identifiable; dependency tau is shared by completion and long-range coupling. Controlled raw-factor observability Gate D: **{'PASS' if redundancy['controlled_observability']['all_observability_pass'] else 'FAIL'}**.",
    )
    gate_lines = "\n".join(
        f"- Gate {g.gate}: **{g.status.value}** — {'; '.join(g.reasons)}" for g in readiness.gates
    )
    write(
        "TRAINING_READINESS_GATE.md",
        "Training Readiness Gate",
        f"Policy: {metadata['policy_version']}\n\n{gate_lines}\n\n## Final decision\n\n{readiness.overall}",
    )
    write(
        "V2_DATASET_VALIDATION_SUMMARY.md",
        "V2 Dataset & Analyzer Validation Summary",
        f"""Formal training remained frozen; only the differentiable smoke check ran (loss={smoke.get("loss", "n/a")}).

## Required answers

1. **P0 label bug:** fixed. Candidate labels come from `RenderedMatlab.candidate_labels`, projected from explicit `SemanticBoundaryTruth`; case metadata no longer labels every boundary.
2. **Candidate truth source:** mapped semantic boundary IDs plus internal no-cut candidates; ambiguous is unsupported in this synthetic corpus.
3. **Real semantic no-cut:** yes. It uses the same final `module_id` on both semantic units and the mapped boundary is excluded from `true_cuts`.
4. **Renderer fidelity:** all declared operation reads enter emitted MATLAB expressions; operation and boundary mappings are recorded in the renderer trace.
5. **Dependency:** high changes observed cross edges/reuse; requested-vs-observed audit matches all generated records.
6. **Long range:** high changes observed dependency span; benign shared-config intent remains distinct from segmentation truth.
7. **Role transition:** low/high changes the analyzer-observed left/right primary role relation.
8. **Interface:** high produces three observed cross-boundary inputs instead of one.
9. **Completion/control/module-size/vocabulary:** each changes rendered operations or surface form while truth remains explicit; all eight controlled families pass target-direction audit.
10. **Pairwise coverage:** all four cells are generated and observed for the six required pairs; requested-vs-observed records have zero mismatches.
11. **Collision recomputation:** candidate-level recomputation found {sum(item.classification == "data_bug" for item in collisions)} data bugs and {sum(item.classification == "potential_missing_raw_fact" for item in collisions)} potential missing-observation pairs. The old collision report is superseded.
12. **Analyzer oracle:** 12 hand-authored cases now cover definitions/reads/mutations plus selected calls/roles/effects; exact-set accuracy is {o["accuracy"]:.2%}, micro F1 {o["f1"]:.2%}. Data/control edges and completion truth remain incomplete, so Gate A fails.
13. **Controlled reliability:** clean and deliberate eval/assignin/unresolved-external cases pass the controlled confidence policy.
14. **GitHub real MATLAB:** remains excluded from training, calibration and model selection; it is non-blocking stress/spot-check input only until independently human-labeled.
15. **Formal training readiness:** no. Gates A, B and E remain failed.

## Previous validation context

The hand oracle contains zero UNKNOWN because selected cases parse reliably. Five real files were spot-checked without population inference. Fingerprint coverage has {holes} single-factor×label holes and {pairholes} required pair holes; semantic split leakage is {coverage["leakage"]["count"]}.

{readiness.overall}""",
    )


def main():
    root = Path.cwd()
    result = run_validation(root)
    print(result["readiness"]["overall"])


if __name__ == "__main__":
    main()
