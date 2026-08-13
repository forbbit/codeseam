from __future__ import annotations

from dataclasses import dataclass

from codeseam.core.ir import ExecutableRegion


@dataclass(frozen=True, slots=True)
class StructuredExample:
    region: ExecutableRegion
    true_cuts: tuple[int, ...]
    sample_id: str
    project: str = "unknown"
    split: str = "unknown"
