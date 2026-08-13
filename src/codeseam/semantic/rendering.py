from __future__ import annotations

from typing import Protocol, TypeVar

from codeseam.semantic.task_graph import SemanticTaskGraph

RenderedArtifact_co = TypeVar("RenderedArtifact_co", covariant=True)


class SemanticRenderer(Protocol[RenderedArtifact_co]):
    """Plugin contract for projecting semantic truth into a source language."""

    language_id: str

    def render(
        self, graph: SemanticTaskGraph, *, seed: int = 0, style: str = "default"
    ) -> RenderedArtifact_co: ...
