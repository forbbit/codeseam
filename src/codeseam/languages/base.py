from __future__ import annotations

from typing import Protocol

from codeseam.core.ir import ProgramIR


class LanguageFrontend(Protocol):
    language_id: str

    def analyze_source(self, source: bytes, path: str) -> ProgramIR: ...
