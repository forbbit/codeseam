from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codeseam.languages.base import LanguageFrontend


@dataclass(frozen=True, slots=True)
class FrontendPlugin:
    language_id: str
    extensions: frozenset[str]
    factory: Callable[[], LanguageFrontend]

    def __post_init__(self) -> None:
        if not self.language_id or self.language_id.lower() != self.language_id:
            raise ValueError("language_id must be a non-empty lowercase identifier")
        if any(not item.startswith(".") or item.lower() != item for item in self.extensions):
            raise ValueError("extensions must be lowercase and start with '.'")

    def create_frontend(self) -> LanguageFrontend:
        frontend = self.factory()
        if frontend.language_id != self.language_id:
            raise ValueError("frontend language_id does not match its plugin")
        return frontend

    def supports_path(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions


class LanguageRegistry:
    """Small explicit registry; future packages register without touching core."""

    def __init__(self) -> None:
        self._plugins: dict[str, FrontendPlugin] = {}
        self._extensions: dict[str, str] = {}

    def register(self, plugin: FrontendPlugin) -> None:
        if plugin.language_id in self._plugins:
            raise ValueError(f"language already registered: {plugin.language_id}")
        conflicts = plugin.extensions & self._extensions.keys()
        if conflicts:
            raise ValueError(f"extensions already registered: {', '.join(sorted(conflicts))}")
        self._plugins[plugin.language_id] = plugin
        self._extensions.update({item: plugin.language_id for item in plugin.extensions})

    def frontend_for(self, path: Path, *, language_id: str | None = None) -> LanguageFrontend:
        selected = language_id or self._extensions.get(path.suffix.lower())
        if selected is None or selected not in self._plugins:
            supported = ", ".join(sorted(self._extensions)) or "none"
            raise ValueError(f"unsupported source language for {path}; extensions: {supported}")
        plugin = self._plugins[selected]
        if language_id is None and not plugin.supports_path(path):
            raise ValueError(f"frontend {selected} does not support {path.suffix}")
        return plugin.create_frontend()

    @property
    def language_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._plugins))


def default_registry() -> LanguageRegistry:
    # Lazy import keeps parser dependencies outside the shared registry module.
    from codeseam.languages.matlab import MatlabFrontend

    registry = LanguageRegistry()
    registry.register(FrontendPlugin("matlab", frozenset({".m"}), MatlabFrontend))
    return registry


DEFAULT_LANGUAGE_REGISTRY = default_registry()
