import json
from pathlib import Path

from script_boundary.corpus.annotations import (
    agreement,
    create_annotation_template,
    validate_annotation,
)
from script_boundary.corpus.real_projects import _matches, validate_registry


def test_registry_requires_pinned_revision_and_license(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": "bad",
                        "repository": "http://example.invalid/repo.git",
                        "revision": "main",
                        "license_spdx": "",
                        "license_file": "",
                    }
                ]
            }
        )
    )
    errors = validate_registry(registry)
    assert len(errors) == 3


def test_registry_rejects_unknown_fetch_method(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": "bad-fetch",
                        "repository": "https://github.com/example/repo",
                        "revision": "a" * 40,
                        "license_spdx": "MIT",
                        "license_file": "LICENSE",
                        "fetch_method": "magic",
                    }
                ]
            }
        )
    )
    assert validate_registry(registry) == ["bad-fetch: unsupported fetch_method"]


def test_recursive_glob_also_matches_root_level_files() -> None:
    assert _matches(Path("demo.m"), "**/*.m")
    assert _matches(Path("examples/demo.m"), "**/*.m")


def test_annotation_covers_all_boundaries_and_measures_agreement(tmp_path) -> None:
    source = tmp_path / "sample.m"
    source.write_text("x = 1;\ny = x + 1;\nz = y + 1;\n")
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left_doc = create_annotation_template(source, left, "left")
    right_doc = create_annotation_template(source, right, "right")
    left_doc["boundaries"][0].update(label="preferred_cut", reason="phase transition")
    right_doc["boundaries"][0].update(label="acceptable_cut", reason="reasonable transition")
    left.write_text(json.dumps(left_doc))
    right.write_text(json.dumps(right_doc))
    assert validate_annotation(left, source) == []
    assert validate_annotation(right, source) == []
    metrics = agreement(left, right)
    assert metrics["exact_agreement"] == 0.5
    assert metrics["cut_vs_noncut_agreement"] == 1.0
