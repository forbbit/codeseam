# V2 formal training freeze

```text
formal_training_enabled = false
```

The differentiable V2 path may currently be exercised only by tiny smoke,
finite-difference, Soft/Hard parity, and numerical-stability tests. Increasing
epochs, tuning optimizer settings, fitting cut penalties, or interpreting F1 as
model quality is out of scope until Training Readiness Gates A–H all pass.

This freeze does not disable the legacy V1 commands. It prevents accidental
promotion of architecture-prototype artifacts into formally trained models.
