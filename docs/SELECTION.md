# Recommendation selection

Boundary scoring and recommendation selection are separate stages. Every legal
statement boundary receives the same feature score as before; the selector decides
which of those scored boundaries should be shown as actionable recommendations.

The default selector applies these deterministic steps inside each executable region:

1. Retain immediate local maxima as candidates.
2. Measure each candidate's prominence against the median score in a five-boundary
   neighborhood and require prominence of at least `0.055`.
3. Require a score of at least `0.58`.
4. Reject parser-constrained boundaries and boundaries between statements written on
   the same physical source line.
5. Optimize all remaining cuts together with dynamic programming. Module quality
   is weighted by interval length, so adding modules cannot create quality reward
   merely by increasing the number of terms. Every cut also pays an explicit cost.
   The objective
   combines each cut's score/prominence surplus with the module quality of every
   interval formed by the selected cut set. Physical distance and greedy order are
   not deciding rules.
6. Charge an unweighted deficit cost when any proposed module falls below quality
   `0.60`. The coefficient is `0.20`. This prevents a one- or two-statement weak
   fragment from hiding behind length-weighted averaging; it is a module-quality
   model, not a fixed boundary-distance rule.

The JSON result preserves `local_peak_candidate`, `prominence`, and
`rejection_reasons`, so a missing recommendation is explainable without consulting
source comments. Comments, section markers, blank lines, and formatting remain absent
from both scoring and selection.

These defaults were calibrated on the generated family-held-out corpus, with the real
`RX_DPqam.m` script used only as an over-segmentation count check, not as hand-labeled
ground truth. Synthetic evaluation is useful for regression detection but is not a
substitute for independently annotated real MATLAB projects.

`corpus tune-selection` searches selector parameters using train and validation
families, optimizing precision-weighted F0.5, and writes a
versioned JSON artifact. `analyze --selection-policy FILE` loads that frozen policy.
The held-out test split is never used to choose parameters.

The current v6/v13 defaults use boundary reward `0.85` and cut penalty `0.03`. Both
feature weights and selector parameters are trained or calibrated only on train and
validation families. On the frozen v13 split, strict precision, recall, and F1 are
each `0.667`, overcut ratio is `1.0`, and structure-macro F1 is `0.600`. These figures
cover five independent synthetic test structures and remain a development diagnostic,
not a production accuracy claim.

On the separately frozen eight-file real-code weak-supervision set, the module-deficit
term reduced predictions from 41 to 32 while retaining all 14 exact matches. Exact
precision rose from `0.341` to `0.438`; ±1-statement F1 rose from `0.444` to `0.500`.
These annotations are model judgments for diagnosis and are not treated as ground truth
or mixed into training.
