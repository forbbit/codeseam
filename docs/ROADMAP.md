# Roadmap

CodeSeam is intentionally suggestion-only while its boundary quality is being
validated. Work is ordered by user value and evidence, not by feature count.

## Near term

- Improve custom-call/index resolution, CallSite reliability, and operation-role inference.
- Add forward/backward program slicing and measure its effect on module completeness.
- Run and review the first sealed structured training session on the finalized real-gold corpus.
- Diagnose validation errors without opening the sealed test split; open test only after freezing.
- Add compact console output and an HTML boundary report.
- Publish signed Python packages and standalone binaries.

## Later

- Preview function inputs and outputs for every recommendation.
- Add opt-in source rewriting after extraction safety is validated.
- Add an editor integration for reviewing suggested seams inline.
- Port performance-sensitive analysis to Rust without changing the language-neutral IR.
- Add another Tree-sitter frontend to validate the multi-language adapter design.

Language support is added through frontends. Language-specific syntax and semantic
rules stay outside ProgramIR, Semantic Analyzer, Structured Energy, and DP.
