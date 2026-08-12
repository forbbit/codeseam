from codeseam.corpus.ablation import ablation_report
from codeseam.corpus.generator import generate_corpus


def test_ablation_reports_old_and_new_feature_performance_by_family(tmp_path) -> None:
    generate_corpus(tmp_path, count=20, seed=1729)
    report = ablation_report(tmp_path, "test")
    assert report["split"] == "test"
    assert 0.0 <= report["legacy_pairwise_accuracy"] <= 1.0
    assert 0.0 <= report["expanded_pairwise_accuracy"] <= 1.0
    assert report["families"]


def test_expanded_features_report_adversarial_families_without_forcing_wins(tmp_path) -> None:
    generate_corpus(tmp_path, count=20, seed=1729)
    validation = ablation_report(tmp_path, "validation")
    test = ablation_report(tmp_path, "test")
    assert "adversarial_large_interface" in validation["families"]
    twin = test["families"]["adversarial_twin_peaks"]
    assert all(0.0 <= value <= 1.0 for value in twin.values())
