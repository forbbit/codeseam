# V2 formal training freeze

```text
formal_training_enabled = false
```

GitHub real-project MATLAB is explicitly excluded from primary training,
calibration, model selection, and labels. Its current role is non-blocking
parser/analyzer stress testing and selected detection spot checks. Any future
external validation or optional fine-tuning requires independent human labels;
self-training from CodeSeam's own predictions is prohibited.

The differentiable V2 path may currently be exercised only by tiny smoke,
finite-difference, Soft/Hard parity, and numerical-stability tests. Increasing
epochs, tuning optimizer settings, fitting cut penalties, or interpreting F1 as
model quality is out of scope until Training Readiness Gates A–H all pass.

This freeze does not disable the legacy V1 commands. It prevents accidental
promotion of architecture-prototype artifacts into formally trained models.
