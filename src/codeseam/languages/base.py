from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from codeseam.core.ir import ProgramIR


@runtime_checkable
class LanguageFrontend(Protocol):
    """Adapter boundary from language syntax to the common ProgramIR."""

    language_id: str

    def analyze_source(self, source: bytes, path: str) -> ProgramIR: ...


class ProjectContextProvider(Protocol):
    """Optional language-specific project enrichment hook."""

    language_id: str

    def enrich(self, program: ProgramIR, context: object) -> None: ...


class LanguagePlugin(Protocol):
    """Discoverable frontend plugin contract used by the registry."""

    language_id: str
    extensions: frozenset[str]

    def create_frontend(self) -> LanguageFrontend: ...

    def supports_path(self, path: Path) -> bool: ...
