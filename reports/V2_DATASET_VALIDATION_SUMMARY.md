# V2 Dataset & Analyzer Validation Summary

Formal training remained frozen; only the differentiable smoke check ran (loss=1.3003572225570679).

## Required answers

1. **Supported subset accuracy:** 12 hand-authored cases / 69 fact units give 91.30% exact-set accuracy and 91.89% micro F1. Edge/call/role/completion oracle families remain incomplete.
2. **Most error-prone structures:** indexed/field mutation, `for` compound aggregation, and condition/body projection contain the observed FP/FN clusters.
3. **UNKNOWN:** the hand oracle has zero UNKNOWN because all selected oracle cases parse reliably. The five-file real-data spot check is too small to characterize UNKNOWN sources, so no population-level claim is made. UNKNOWN is never numeric zero.
4. **Real-data detection:** only five fixed parser-clean files were checked. They contain 34 candidate boundaries and 3 recommendations, with 0 low-parse boundaries. No population-level dependency-confidence conclusion is drawn.
5. **Covered fingerprint regions:** train-fitted typed blocks and cut/no-cut low/high quadrants for all eight families; semantic split leakage is 0.
6. **Empty regions:** 10 single-factor×label cells and 6 required pair cells remain empty.
7. **High correlations:** completion↔dependency-mass (0.988), dependency-mass↔interface-compactness (0.973), completion↔interface-compactness (0.929).
8. **Independent activation:** several factors have low/high variants, but activation and suppression evidence for every numerical feature is incomplete.
9. **Opposite labels with near-identical Raw Fingerprints:** yes—439 unexplainable pairs at radii ≤0.05.
10. **Missing semantics:** target-factor deltas for dependency, vocabulary and long-range variants, plus precise control depth and operation projection.
11. **Formal training readiness:** no. Gates A, B, D and E fail; Gate F is intentionally NOT_EVALUATED because the selected real files are detection examples, not a training population.

READY FOR FORMAL TRAINING: NO
