from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from codeseam.core.ir import Risk


@dataclass(frozen=True, slots=True)
class MatlabFileSymbol:
    path: str
    kind: str
    primary_name: str
    local_functions: tuple[str, ...]
    calls: tuple[str, ...]
    resolved_project_calls: tuple[str, ...]
    unresolved_calls: tuple[str, ...]
    diagnostics: tuple[str, ...]


@dataclass(slots=True)
class MatlabProjectIndex:
    root: str
    files: list[MatlabFileSymbol]
    providers: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")

    @classmethod
    def from_json(cls, path: Path) -> MatlabProjectIndex:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            root=payload["root"],
            files=[MatlabFileSymbol(**item) for item in payload["files"]],
            providers=payload["providers"],
        )


def scan_matlab_project(root: Path) -> MatlabProjectIndex:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"project root is not a directory: {root}")
    parsed = []
    providers: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.m")):
        relative = path.relative_to(root).as_posix()
        completed = subprocess.run(
            [sys.executable, "-m", "codeseam.languages.matlab.project_worker", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            parsed.append(
                (
                    relative,
                    "unparsed",
                    path.stem,
                    (),
                    [],
                    (f"isolated frontend failure (exit {completed.returncode})",),
                )
            )
            providers.setdefault(path.stem, []).append(relative)
            continue
        payload = json.loads(completed.stdout)
        functions = tuple(payload["functions"])
        has_script = payload["has_script"]
        primary_name = functions[0] if functions and not has_script else path.stem
        kind = "mixed" if has_script and functions else ("script" if has_script else "function")
        # Only the file-level entry point is visible project-wide. Local functions
        # are resolved separately inside their owning file.
        providers.setdefault(path.stem, []).append(relative)
        calls = payload["calls"]
        parsed.append((relative, kind, primary_name, functions, calls, tuple(payload["diagnostics"])))
    files = []
    for relative, kind, primary_name, functions, calls, diagnostics in parsed:
        local_visible = set(functions)
        resolved = tuple(call for call in calls if call in providers or call in local_visible)
        unresolved = tuple(call for call in calls if call not in providers)
        files.append(
            MatlabFileSymbol(
                relative,
                kind,
                primary_name,
                functions,
                tuple(calls),
                resolved,
                unresolved,
                diagnostics,
            )
        )
    return MatlabProjectIndex(str(root), files, dict(sorted(providers.items())))


def apply_project_context(program, index: MatlabProjectIndex) -> None:
    try:
        relative = program.path.resolve().relative_to(Path(index.root)).as_posix()
    except ValueError:
        relative = program.path.name
    file_symbol = next((item for item in index.files if item.path == relative), None)
    visible = set(index.providers)
    if file_symbol:
        visible.update(file_symbol.local_functions)
    for region in program.regions:
        for statement in region.statements:
            statement.call_resolution_available = True
            project_calls = statement.unresolved_calls & visible
            statement.resolved_calls |= project_calls
            statement.unresolved_calls -= project_calls
            if not statement.unresolved_calls:
                statement.risks.discard(Risk.AMBIGUOUS_CALL_OR_INDEX)
