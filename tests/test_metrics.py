from script_boundary.corpus.metrics import (
    aggregate_matches,
    match_boundaries,
    match_boundaries_with_ignored,
)


def test_tolerance_matching_is_one_to_one() -> None:
    result = match_boundaries([4, 5, 10], [5, 11], tolerance=1)
    assert result.true_positive == 2
    assert result.false_positive == 1
    assert result.false_negative == 0


def test_aggregate_matches_uses_micro_averaging() -> None:
    result = aggregate_matches(
        [match_boundaries([2], [2]), match_boundaries([1, 7], [8], tolerance=1)]
    )
    assert result.true_positive == 2
    assert result.false_positive == 1
    assert result.false_negative == 0
    assert result.precision == 2 / 3


def test_ignored_boundaries_are_neither_positive_nor_false_positive() -> None:
    result = match_boundaries_with_ignored([2, 5, 9], [2], [5])
    assert result.true_positive == 1
    assert result.false_positive == 1
