# V2 Dataset & Analyzer Validation Summary

Formal training remained frozen; only the differentiable smoke check ran (loss=1.3003572225570679).

## Required answers

1. **P0 label bug:** fixed. Candidate labels come from `RenderedMatlab.candidate_labels`, projected from explicit `SemanticBoundaryTruth`; case metadata no longer labels every boundary.
2. **Candidate truth source:** mapped semantic boundary IDs plus internal no-cut candidates; ambiguous is unsupported in this synthetic corpus.
3. **Real semantic no-cut:** yes. It uses the same final `module_id` on both semantic units and the mapped boundary is excluded from `true_cuts`.
4. **Renderer fidelity:** all declared operation reads enter emitted MATLAB expressions; operation and boundary mappings are recorded in the renderer trace.
5. **Dependency:** high changes observed cross edges/reuse; requested-vs-observed audit matches all generated records.
6. **Long range:** high changes observed dependency span; benign shared-config intent remains distinct from segmentation truth.
7. **Role transition:** low/high changes the analyzer-observed left/right primary role relation.
8. **Interface:** high produces three observed cross-boundary inputs instead of one.
9. **Completion/control/module-size/vocabulary:** each changes rendered operations or surface form while truth remains explicit; all eight controlled families pass target-direction audit.
10. **Pairwise coverage:** all four cells are generated and observed for the six required pairs; requested-vs-observed records have zero mismatches.
11. **Collision recomputation:** candidate-level recomputation found 0 data bugs and 936 potential missing-observation pairs. The old collision report is superseded.
12. **Analyzer oracle:** 12 hand-authored cases now cover definitions/reads/mutations plus selected calls/roles/effects; exact-set accuracy is 93.75%, micro F1 95.38%. Data/control edges and completion truth remain incomplete, so Gate A fails.
13. **Controlled reliability:** clean and deliberate eval/assignin/unresolved-external cases pass the controlled confidence policy.
14. **GitHub real MATLAB:** remains excluded from training, calibration and model selection; it is non-blocking stress/spot-check input only until independently human-labeled.
15. **Formal training readiness:** no. Gates A, B and E remain failed.

## Previous validation context

The hand oracle contains zero UNKNOWN because selected cases parse reliably. Five real files were spot-checked without population inference. Fingerprint coverage has 0 single-factor×label holes and 0 required pair holes; semantic split leakage is 0.

READY FOR FORMAL TRAINING: NO
