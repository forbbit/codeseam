from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def match_boundaries(
    predicted: list[int], truth: list[int], *, tolerance: int = 0
) -> MatchMetrics:
    """One-to-one ordered boundary matching in statement-index coordinates."""
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    remaining = set(truth)
    matched = 0
    for candidate in sorted(predicted):
        possible = [target for target in remaining if abs(candidate - target) <= tolerance]
        if not possible:
            continue
        target = min(possible, key=lambda item: (abs(candidate - item), item))
        remaining.remove(target)
        matched += 1
    false_positive = len(predicted) - matched
    false_negative = len(truth) - matched
    precision = matched / len(predicted) if predicted else (1.0 if not truth else 0.0)
    recall = matched / len(truth) if truth else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return MatchMetrics(matched, false_positive, false_negative, precision, recall, f1)


def match_boundaries_with_ignored(
    predicted: list[int], truth: list[int], ignored: list[int], *, tolerance: int = 0
) -> MatchMetrics:
    """Match positives one-to-one, then remove predictions landing on ignored labels."""
    remaining_truth = set(truth)
    unmatched_predictions = []
    matched = 0
    for candidate in sorted(predicted):
        possible = [target for target in remaining_truth if abs(candidate - target) <= tolerance]
        if possible:
            target = min(possible, key=lambda item: (abs(candidate - item), item))
            remaining_truth.remove(target)
            matched += 1
        else:
            unmatched_predictions.append(candidate)
    false_positive = sum(
        not any(abs(candidate - target) <= tolerance for target in ignored)
        for candidate in unmatched_predictions
    )
    false_negative = len(remaining_truth)
    predicted_count = matched + false_positive
    precision = matched / predicted_count if predicted_count else (1.0 if not truth else 0.0)
    recall = matched / len(truth) if truth else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return MatchMetrics(matched, false_positive, false_negative, precision, recall, f1)


def aggregate_matches(items: list[MatchMetrics]) -> MatchMetrics:
    true_positive = sum(item.true_positive for item in items)
    false_positive = sum(item.false_positive for item in items)
    false_negative = sum(item.false_negative for item in items)
    predicted = true_positive + false_positive
    truth = true_positive + false_negative
    precision = true_positive / predicted if predicted else (1.0 if not truth else 0.0)
    recall = true_positive / truth if truth else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return MatchMetrics(true_positive, false_positive, false_negative, precision, recall, f1)
