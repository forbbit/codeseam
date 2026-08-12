from script_boundary.corpus.generator import generate_corpus
from script_boundary.corpus.selection_tuning import load_selection_config, tune_selection
from script_boundary.corpus.training import train_weights


def test_selection_tuning_uses_validation_and_writes_artifact(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    artifact = tmp_path / "selection.json"
    weights = tmp_path / "weights.json"
    generate_corpus(corpus, count=22, seed=9)
    trained = train_weights(corpus, weights)
    result = tune_selection(corpus, artifact, weights_artifact=weights)
    assert result["tuned_on_splits"] == ["train", "validation"]
    assert result["test_split_used"] is False
    assert result["search_candidates"] > 1
    assert artifact.exists()
    assert 0.0 <= result["development"]["f1"] <= 1.0
    loaded = load_selection_config(artifact)
    assert loaded.threshold == result["config"]["threshold"]
    assert loaded.weights == trained["weights"]
