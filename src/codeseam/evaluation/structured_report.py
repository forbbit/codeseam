from __future__ import annotations

from codeseam.core.hard_dp import best_segmentation
from codeseam.core.structured_energy import StructuredScorer
from codeseam.corpus.metrics import aggregate_matches, match_boundaries
from codeseam.training.structured_loss import structured_nll
from codeseam.training.trainer import StructuredExample


def evaluate_structured(
    scorer: StructuredScorer, examples: list[StructuredExample], *, tolerance: int = 0
) -> dict[str, float | int]:
    matches = []
    losses = []
    exact = 0
    count_error = 0
    for example in examples:
        energy = scorer(example.region)
        cuts, _ = best_segmentation(energy)
        truth = list(example.true_cuts)
        matches.append(match_boundaries(cuts, truth, tolerance=tolerance))
        losses.append(float(structured_nll(energy, truth).detach()))
        exact += int(cuts == truth)
        count_error += abs(len(cuts) - len(truth))
    metric = aggregate_matches(matches)
    total = len(examples)
    return {
        "samples": total,
        "structured_nll": sum(losses) / total if total else 0.0,
        "precision": metric.precision,
        "recall": metric.recall,
        "f1": metric.f1,
        "exact_segmentation_accuracy": exact / total if total else 0.0,
        "average_cut_count_error": count_error / total if total else 0.0,
    }
