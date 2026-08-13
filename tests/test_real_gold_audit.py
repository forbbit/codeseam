from __future__ import annotations

from pathlib import Path

from codeseam.evaluation.real_gold_audit import audit_real_gold


def test_published_real_gold_passes_full_audit() -> None:
    corpus = Path(__file__).parents[1] / "corpus" / "real-curation"
    report = audit_real_gold(corpus)
    assert report["passed"], report["errors"]
    assert report["counts"]["records"] == 118
    assert report["counts"]["modules"] == 694
    assert report["counts"]["preferred_cuts"] == 576
    assert report["splits"]["train"]["files"] == 82
    assert report["splits"]["validation"]["files"] == 18
    assert report["splits"]["test"]["files"] == 18
