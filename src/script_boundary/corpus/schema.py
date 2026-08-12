from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BoundaryLabel(StrEnum):
    PREFERRED = "preferred_cut"
    ACCEPTABLE = "acceptable_cut"
    NEUTRAL = "neutral"
    DISCOURAGED = "discouraged_cut"
    FORBIDDEN = "forbidden_cut"


@dataclass(frozen=True, slots=True)
class BoundaryTruth:
    after_line: int
    label: BoundaryLabel
    reason: str
    left_module: str | None = None
    right_module: str | None = None
    region_id: str = "script:top-level"
    boundary: int | None = None


@dataclass(frozen=True, slots=True)
class SegmentTruth:
    module_id: str
    start_line: int
    end_line: int
    region_id: str = "script:top-level"
    extraction_safe: bool = True


@dataclass(frozen=True, slots=True)
class AuxiliaryFile:
    relative_path: str
    source_sha256: str


@dataclass(slots=True)
class CorpusRecord:
    schema_version: str
    sample_id: str
    family: str
    split: str
    seed: int
    relative_path: str
    source_sha256: str
    boundaries: list[BoundaryTruth]
    segments: list[SegmentTruth] = field(default_factory=list)
    auxiliary_files: list[AuxiliaryFile] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def normalize(value: Any) -> Any:
            if isinstance(value, StrEnum):
                return value.value
            if isinstance(value, list):
                return [normalize(item) for item in value]
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            return value

        return normalize(asdict(self))
