from pathlib import Path


def test_core_does_not_contain_matlab_or_tree_sitter_dependencies() -> None:
    core = Path(__file__).parents[1] / "src" / "codeseam" / "core"
    text = "\n".join(path.read_text(encoding="utf-8") for path in core.glob("*.py"))
    assert "tree_sitter" not in text
    assert "matlab" not in text.lower()
