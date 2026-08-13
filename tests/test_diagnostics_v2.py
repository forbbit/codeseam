import pytest

from codeseam.evaluation.diagnostics import DiagnosticRow, ablation_scores, feature_diagnostics


def test_feature_diagnostics_and_family_ablation():
    rows = [
        DiagnosticRow({"a": 0.0, "b": 1.0}, {"a": 0.2, "b": -0.1}, {"a": 1.0}, "cut"),
        DiagnosticRow({"a": 1.0, "b": 0.0}, {"a": 0.4, "b": 0.1}, {"a": 0.5}, "no-cut"),
    ]
    report = feature_diagnostics(rows)
    assert report["pearson_correlation"]["a"]["b"] == -1.0
    assert ablation_scores(rows, {"symbol": {"a"}})["symbol"] == pytest.approx(0.3)
