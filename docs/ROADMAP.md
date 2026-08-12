# Roadmap

CodeSeam is intentionally suggestion-only while its boundary quality is being
validated. Work is ordered by user value and evidence, not by feature count.

## Near term

- Build an independently reviewed MATLAB benchmark from pinned open-source projects.
- Improve selector precision on nearby high-scoring candidates and mixed script/function files.
- Add compact console output and an HTML boundary report.
- Publish signed Python packages and standalone binaries.

## Later

- Preview function inputs and outputs for every recommendation.
- Add opt-in source rewriting after extraction safety is validated.
- Add an editor integration for reviewing suggested seams inline.
- Port performance-sensitive analysis to Rust without changing the language-neutral IR.
- Add another Tree-sitter frontend to validate the multi-language adapter design.

Language support is added through frontends. Language-specific syntax and semantic
rules stay outside the scoring and selection core.
