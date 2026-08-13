from codeseam.evaluation.semantic_oracle import (
    OracleObservation,
    OracleStatus,
    evaluate_oracle,
)


def test_oracle_distinguishes_wrong_and_unknown():
    observations = [
        OracleObservation("reads", frozenset({"x"}), frozenset({"x"})),
        OracleObservation("reads", frozenset({"y"}), frozenset(), 1.0),
        OracleObservation("reads", frozenset({"z"}), frozenset(), 0.2),
    ]
    assert [item.status for item in observations] == [
        OracleStatus.CORRECT,
        OracleStatus.WRONG,
        OracleStatus.UNKNOWN,
    ]
    report = evaluate_oracle(observations)["overall"]
    assert report["accuracy"] == 0.5
    assert report["unknown_coverage"] == 1 / 3
