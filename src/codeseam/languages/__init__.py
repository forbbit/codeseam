"""Plugin contracts and discovery for language frontends."""

from codeseam.languages.base import LanguageFrontend, LanguagePlugin, ProjectContextProvider
from codeseam.languages.registry import FrontendPlugin, LanguageRegistry

__all__ = [
    "FrontendPlugin",
    "LanguageFrontend",
    "LanguagePlugin",
    "LanguageRegistry",
    "ProjectContextProvider",
]
