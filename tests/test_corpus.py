import json

from codeseam.corpus.generator import (
    FAMILIES,
    FAMILY_SPLITS,
    audit_corpus,
    evaluate_corpus,
    generate_corpus,
)


def test_generated_corpus_is_reproducible_and_auditable(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    records_a = generate_corpus(first, count=len(FAMILIES), seed=41)
    records_b = generate_corpus(second, count=len(FAMILIES), seed=41)
    assert [record.to_dict() for record in records_a] == [record.to_dict() for record in records_b]
    assert (first / "manifest.jsonl").read_text() == (second / "manifest.jsonl").read_text()
    assert audit_corpus(first) == []
    assert {record.family for record in records_a} == set(FAMILIES)


def test_manifest_uses_multilevel_labels_and_traceable_metadata(tmp_path) -> None:
    records = generate_corpus(tmp_path, count=8, seed=1729)
    labels = {truth.label.value for record in records for truth in record.boundaries}
    assert {"preferred_cut", "acceptable_cut", "discouraged_cut", "forbidden_cut"} <= labels
    manifest = [json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert all(item["schema_version"] == "1.0" for item in manifest)
    assert all(item["source_sha256"] and item["seed"] for item in manifest)
    assert all(item["provenance"]["structure_fingerprint"] for item in manifest)
    splits_by_hash: dict[str, set[str]] = {}
    for item in manifest:
        splits_by_hash.setdefault(item["source_sha256"], set()).add(item["split"])
    assert all(len(splits) == 1 for splits in splits_by_hash.values())
    assert all(item["split"] == FAMILY_SPLITS[item["family"]] for item in manifest)
    families_by_split: dict[str, set[str]] = {}
    for item in manifest:
        families_by_split.setdefault(item["split"], set()).add(item["family"])
    assert not (families_by_split["train"] & families_by_split["validation"])
    assert not (families_by_split["train"] & families_by_split["test"])
    assert any(item["segments"] for item in manifest)
    assert any(item["auxiliary_files"] for item in manifest)
    assert all(
        boundary["label"] != "neutral" for item in manifest for boundary in item["boundaries"]
    )


def test_corpus_evaluation_reports_safety_and_ranking_metrics(tmp_path) -> None:
    generate_corpus(tmp_path, count=8, seed=1729)
    metrics = evaluate_corpus(tmp_path)
    assert metrics["samples"] == 8
    assert metrics["labeled_boundaries"] > 0
    assert 0.0 <= metrics["preferred_recall"] <= 1.0
    assert 0.0 <= metrics["discouraged_recommendation_rate"] <= 1.0
    assert metrics["forbidden_recommendation_rate"] == 0.0
    assert metrics["recommendations_per_sample"] >= 0.0
    assert metrics["strict_exact"]["precision"] >= 0.0
    assert metrics["strict_exact"]["recall"] >= 0.0
    assert metrics["strict_exact"]["f1"] >= 0.0
    assert metrics["strict_tolerant"]["recall"] >= metrics["strict_exact"]["recall"]
    assert metrics["unique_structures"] > 0
    assert 0.0 <= metrics["strict_exact_structure_macro"]["f1"] <= 1.0
    assert metrics["recommendations_per_100_statements"] >= 0.0
    assert 0.0 <= metrics["pairwise_accuracy"] <= 1.0
    assert evaluate_corpus(tmp_path, "test")["split"] == "test"
