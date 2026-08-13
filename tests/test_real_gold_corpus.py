from __future__ import annotations

import json
from pathlib import Path

from codeseam.training.corpus import load_structured_examples


def test_real_gold_manifest_has_only_final_project_isolated_records() -> None:
    corpus = Path(__file__).parents[1] / "corpus" / "real-curation"
    records = [json.loads(line) for line in (corpus / "manifest.jsonl").read_text().splitlines()]
    assert len(records) == 118
    assert {record["sample_id"] for record in records}.isdisjoint({"M0110", "M0111"})
    final_statuses = {"user_adjudicated", "expert_accepted"}
    assert all(
        record["provenance"]["annotation_status"] in final_statuses for record in records
    )
    assert {record["provenance"]["annotation_confidence"] for record in records} == {
        "high"
    }
    project_splits: dict[str, str] = {}
    for record in records:
        project = record["provenance"]["project"]
        assert project_splits.setdefault(project, record["split"]) == record["split"]


def test_structured_loader_ignores_unannotated_helper_regions() -> None:
    corpus = Path(__file__).parents[1] / "corpus" / "real-curation"
    manifest = [json.loads(line) for line in (corpus / "manifest.jsonl").read_text().splitlines()]
    expected = {
        split: sum(
            len({segment["region_id"] for segment in record["segments"]})
            for record in manifest
            if record["split"] == split
        )
        for split in ("train", "validation", "test")
    }
    for split, count in expected.items():
        assert len(load_structured_examples(corpus, split)) == count


def test_structured_loader_uses_statement_indices_not_ambiguous_lines(tmp_path) -> None:
    source = b"x = 1; y = 2;\nz = x + y;\n"
    (tmp_path / "sample.m").write_bytes(source)
    import hashlib

    record = {
        "sample_id": "same-line",
        "split": "train",
        "relative_path": "sample.m",
        "segments": [
            {"region_id": "script:top-level", "start_line": 1, "end_line": 1},
            {"region_id": "script:top-level", "start_line": 1, "end_line": 2},
        ],
        "boundaries": [
            {
                "region_id": "script:top-level",
                "boundary": 1,
                "after_line": 1,
                "label": "preferred_cut",
            },
            {
                "region_id": "script:top-level",
                "boundary": 2,
                "after_line": 1,
                "label": "discouraged_cut",
            },
        ],
        "provenance": {
            "source_kind": "curated_real_gold",
            "annotation_status": "user_adjudicated",
            "annotation_confidence": "high",
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "revision": "pinned",
        },
    }
    (tmp_path / "manifest.jsonl").write_text(json.dumps(record) + "\n")
    examples = load_structured_examples(tmp_path, "train")
    assert examples[0].true_cuts == (1,)
