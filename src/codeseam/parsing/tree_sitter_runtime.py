from __future__ import annotations

from tree_sitter import Language, Parser, Tree


class TreeSitterRuntime:
    """Small parser wrapper; grammar-specific interpretation lives in frontends."""

    def __init__(self, language_capsule: object) -> None:
        self._parser = Parser(Language(language_capsule))

    def parse(self, source: bytes) -> Tree:
        return self._parser.parse(source)
