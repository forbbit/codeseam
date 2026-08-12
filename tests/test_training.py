from codeseam.corpus.generator import generate_corpus
from codeseam.corpus.training import evaluate_weight_artifact, train_weights


def test_training_is_deterministic_and_emits_nonnegative_normalized_weights(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    generate_corpus(corpus, count=40, seed=1729)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    artifact_a = train_weights(corpus, first)
    artifact_b = train_weights(corpus, second)
    assert artifact_a == artifact_b
    weights = artifact_a["weights"]
    assert all(value >= 0 for value in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 1e-12
    assert first.read_text() == second.read_text()
    assert 0.0 <= evaluate_weight_artifact(corpus, first, "test") <= 1.0
