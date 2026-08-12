# Benchmarks

CodeSeam uses synthetic evaluation as a reproducible regression benchmark, not as
a claim of production accuracy. The generator creates scripts from 17 structural
families, including mixed scripts and local functions, branches, loops, workspace
effects, external project calls, large interfaces, and adversarial nearby peaks.
Structural fingerprints are checked to prevent equivalent programs from leaking
between dataset splits.

## Frozen v0.1 benchmark

The committed v6 boundary weights and v6/v13 selector were fitted and calibrated
without the test families. The following result is produced from seed `1729`:

| Measurement | Result |
| --- | ---: |
| Test scripts | 100 |
| Unique test structures | 5 |
| Labeled legal boundaries | 900 |
| Strict precision | 0.667 |
| Strict recall | 0.667 |
| Strict F1 | 0.667 |
| Forbidden-boundary recommendation rate | 0.000 |
| Excess-cut rate | 0.000 |
| Recommendations per script | 1.20 |

Reproduce it locally:

```bash
codeseam corpus generate corpus/generated-release --count 340 --seed 1729
codeseam corpus audit corpus/generated-release
codeseam corpus evaluate corpus/generated-release --split test \
  --selection-policy weights/selection-v6-v13.json
```

Exact and two-statement-tolerance scores happen to be identical on this frozen
test set. The structure-macro F1 is `0.600`, which exposes uneven performance
between structural families. These results should not be interpreted as MATLAB
project-level accuracy.

## Real-project protocol

The project registry pins four permissively licensed MATLAB repositories by full
commit SHA. Sources are downloaded only when explicitly requested and are never
redistributed. A credible real-world accuracy claim requires independent boundary
annotation, inter-annotator agreement, and adjudication. That work remains open;
see [real-project validation](REAL_VALIDATION.md).
