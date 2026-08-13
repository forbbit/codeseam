import json
from pathlib import Path

import pytest

from codeseam.core.ir import ProgramIR
from codeseam.languages.registry import FrontendPlugin, LanguageRegistry
from codeseam.service import analyze_file
from codeseam.training.corpus import load_structured_examples


class StubFrontend:
    language_id = "python"

    def analyze_source(self, source: bytes, path: str) -> ProgramIR:
        return ProgramIR("python", Path(path), "stub", [])


def test_registry_supports_future_language_plugins_without_core_changes(tmp_path) -> None:
    registry = LanguageRegistry()
    registry.register(FrontendPlugin("python", frozenset({".py"}), StubFrontend))
    path = tmp_path / "example.py"
    path.write_text("value = 1\n", encoding="utf-8")
    result = analyze_file(path, registry=registry)
    assert result.program.language == "python"
    assert not result.boundaries


def test_default_registry_preserves_matlab_behavior(tmp_path) -> None:
    path = tmp_path / "example.m"
    path.write_text("x = 1;\ny = x + 1;\n", encoding="utf-8")
    result = analyze_file(path)
    assert result.program.language == "matlab"
    assert len(result.boundaries) == 1


def test_real_github_record_is_rejected_before_training(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    record = {
        "sample_id": "external",
        "split": "train",
        "relative_path": "missing.m",
        "boundaries": [],
        "provenance": {"source_kind": "github_real", "language": "matlab"},
    }
    (corpus / "manifest.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden for training"):
        load_structured_examples(corpus, "train")


def test_untrusted_manifest_is_not_implicitly_treated_as_training_truth(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    record = {
        "sample_id": "unknown",
        "split": "train",
        "relative_path": "missing.m",
        "boundaries": [],
        "provenance": {},
    }
    (corpus / "manifest.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="trusted source_kind"):
        load_structured_examples(corpus, "train")
