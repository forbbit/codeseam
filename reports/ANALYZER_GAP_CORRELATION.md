# Analyzer Gap–Error Correlation Audit

Scope: 82 training files and 18 validation files. The sealed 18-file test split was
not loaded. The audit used executable code only.

Because the current 20-feature schema is incompatible with the older 12/15-feature
artifacts, this audit fitted a temporary class-balanced linear boundary probe on the
training split. Its threshold was selected on training only. The probe is diagnostic:
it measures whether boundary errors correlate with Analyzer coverage, not the quality
of Structured Energy or Hard-DP segmentation.

## Coverage

| Analyzer condition | Train boundaries | Validation boundaries | Validation Gold cuts |
|---|---:|---:|---:|
| parse reliability below 1 | 0 (0.0%) | 0 (0.0%) | 0 |
| call resolution below 0.75 | 3,259 (78.4%) | 561 (77.8%) | 72/85 |
| role reliability below 0.9 | 4,111 (98.9%) | 691 (95.8%) | 83/85 |
| call-site reliability below 0.75 | 3,802 (91.5%) | 626 (86.8%) | 81/85 |
| dynamic workspace risk | 49 (1.2%) | 0 (0.0%) | 0 |
| external dependency | 244 (5.9%) | 66 (9.2%) | 12/85 |
| indirect call | 314 (7.6%) | 82 (11.4%) | 9/85 |
| region containing unsupported switch/try CFG | 0 | 0 | 0 |

The validation corpus therefore cannot measure the value of switch/try lowering,
exception flow, or dynamic-workspace recovery. These gaps exist architecturally but
are not responsible for the present validation errors.

## Diagnostic probe

The probe obtained validation precision 0.299, recall 0.376, and F1 0.333. This is
not a formal model score. Adding the Analyzer reliability channels to the 20 feature
values raised validation F1 from 0.320 to 0.333, a small absolute gain of 0.013.

Low call resolution correlated primarily with false positives: the false-positive
rate was 13.7% where call resolution was low and 5.4% in its complement. Low
call-site reliability showed a similar 13.4% versus 2.2% split. This supports the
claim that unresolved call/index structure contributes to overcutting.

The evidence for false negatives is different. Low-call-resolution Gold cuts had a
59.7% miss rate, while the smaller resolved complement had a 76.9% miss rate. Unknown
roles were almost universal, leaving only two high-role-reliability Gold cuts and no
statistically useful clean comparison. Analyzer gaps therefore do not by themselves
explain the current undercutting problem.

## Conclusion

1. Improve custom-call/index resolution and call-site extraction first; these gaps
   cover most real boundaries and are associated with substantially more false
   positives.
2. Improve operation-role inference together with call semantics. Its present 95.8%
   validation coverage is too broad to be discriminative and suppresses useful role
   evidence almost everywhere.
3. Do not prioritize switch, try/catch, exceptional flow, or dynamic workspace for
   the current 118-file benchmark: the validation set contains no affected region.
   Add explicit reviewed coverage before claiming gains from those implementations.
4. Program slicing remains a plausible missing feature for module completeness and
   undercutting, but this audit cannot test it because no implemented slice signal
   exists to ablate. It should be implemented next and evaluated by controlled
   feature ablation.

The table above retains the decision-relevant counts; per-boundary diagnostic scratch
data was intentionally discarded after the audit.
