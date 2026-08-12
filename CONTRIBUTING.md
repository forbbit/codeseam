# Contributing

## Development setup

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
```

## Design rules

- Keep `core` independent of MATLAB and Tree-sitter packages.
- Put grammar node names and language semantics in a language frontend.
- Never use comments, section markers, blank lines, or formatting as boundary evidence.
- Preserve raw measurements alongside normalized features.
- Add tests for comment invariance and control/data-flow behavior when relevant.
- Do not commit generated corpora, downloaded third-party source, private annotations,
  local project indexes, or analysis reports.

## Pull requests

Keep changes focused and describe their effect on overcutting and missed boundaries.
Run tests, Ruff, and a wheel build before opening a pull request. Algorithm changes
should report train/validation selection separately from a previously untouched test
split. Do not tune against a named real script without independently reviewed labels.
