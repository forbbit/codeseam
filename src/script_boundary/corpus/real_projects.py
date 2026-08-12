from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectSpec:
    project_id: str
    repository: str
    revision: str
    license_spdx: str
    license_file: str
    include_globs: tuple[str, ...] = ("**/*.m",)
    exclude_globs: tuple[str, ...] = ()
    fetch_method: str = "git"


def load_registry(path: Path) -> list[ProjectSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    specs: list[ProjectSpec] = []
    for item in data.get("projects", []):
        specs.append(
            ProjectSpec(
                project_id=item["project_id"],
                repository=item["repository"],
                revision=item["revision"],
                license_spdx=item["license_spdx"],
                license_file=item["license_file"],
                include_globs=tuple(item.get("include_globs", ["**/*.m"])),
                exclude_globs=tuple(item.get("exclude_globs", [])),
                fetch_method=item.get("fetch_method", "git"),
            )
        )
    return specs


def validate_registry(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        specs = load_registry(path)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        return [f"invalid registry: {error}"]
    seen: set[str] = set()
    for spec in specs:
        if spec.project_id in seen:
            errors.append(f"duplicate project_id: {spec.project_id}")
        seen.add(spec.project_id)
        if not spec.repository.startswith("https://"):
            errors.append(f"{spec.project_id}: repository must use https")
        if len(spec.revision) != 40 or any(
            char not in "0123456789abcdef" for char in spec.revision
        ):
            errors.append(f"{spec.project_id}: revision must be a full lowercase commit SHA")
        if not spec.license_spdx or not spec.license_file:
            errors.append(f"{spec.project_id}: license metadata is required")
        if spec.fetch_method not in {"git", "github_raw"}:
            errors.append(f"{spec.project_id}: unsupported fetch_method")
    return errors


def fetch_projects(registry: Path, output: Path) -> list[dict[str, object]]:
    errors = validate_registry(registry)
    if errors:
        raise ValueError("; ".join(errors))
    if (
        any(spec.fetch_method == "git" for spec in load_registry(registry))
        and shutil.which("git") is None
    ):
        raise ValueError("git is required to fetch real projects")
    output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for spec in load_registry(registry):
        project_dir = output / "sources" / spec.project_id
        if project_dir.exists():
            raise ValueError(f"target already exists: {project_dir}")
        if spec.fetch_method == "github_raw":
            _fetch_github_raw(spec, project_dir)
        else:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    spec.repository,
                    str(project_dir),
                ],
                check=True,
            )
            subprocess.run(
                ["git", "checkout", "--detach", spec.revision], cwd=project_dir, check=True
            )
        license_path = project_dir / spec.license_file
        if not license_path.is_file():
            raise ValueError(f"license file missing for {spec.project_id}: {spec.license_file}")
        files = _selected_files(project_dir, spec)
        file_records = []
        for path in files:
            source = path.read_bytes()
            parse = _isolated_parse(path)
            file_records.append(
                {
                    "path": str(path.relative_to(project_dir)).replace("\\", "/"),
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "parser_diagnostics": parse["diagnostics"],
                    "regions": parse["regions"],
                }
            )
        manifest.append(
            {
                "project_id": spec.project_id,
                "repository": spec.repository,
                "revision": spec.revision,
                "license_spdx": spec.license_spdx,
                "license_file": spec.license_file,
                "license_sha256": hashlib.sha256(license_path.read_bytes()).hexdigest(),
                "files": file_records,
            }
        )
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps({"projects": manifest}, indent=2) + "\n", encoding="utf-8")
    return manifest


def _selected_files(root: Path, spec: ProjectSpec) -> list[Path]:
    included = {
        path for pattern in spec.include_globs for path in root.glob(pattern) if path.is_file()
    }
    excluded = {path for pattern in spec.exclude_globs for path in root.glob(pattern)}
    return sorted(included - excluded)


def _fetch_github_raw(spec: ProjectSpec, project_dir: Path) -> None:
    prefix = "https://github.com/"
    if not spec.repository.startswith(prefix):
        raise ValueError(f"github_raw requires a GitHub repository: {spec.project_id}")
    slug = spec.repository.removeprefix(prefix).removesuffix(".git")
    api = f"https://api.github.com/repos/{slug}/git/trees/{spec.revision}?recursive=1"
    request = urllib.request.Request(api, headers={"User-Agent": "script-boundary-corpus"})
    with urllib.request.urlopen(request) as response:
        tree = json.load(response)
    paths = [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]
    if spec.license_file not in paths:
        raise ValueError(
            f"license file missing from pinned tree for {spec.project_id}: {spec.license_file}"
        )
    selected = _select_relative_paths(paths, spec)
    selected.add(spec.license_file)
    for relative in sorted(selected):
        quoted = "/".join(urllib.parse.quote(part) for part in relative.split("/"))
        url = f"https://raw.githubusercontent.com/{slug}/{spec.revision}/{quoted}"
        target = project_dir / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url) as response:
            target.write_bytes(response.read())


def _select_relative_paths(paths: list[str], spec: ProjectSpec) -> set[str]:
    candidates = {Path(path) for path in paths}
    included = {
        path for pattern in spec.include_globs for path in candidates if _matches(path, pattern)
    }
    excluded = {
        path for pattern in spec.exclude_globs for path in candidates if _matches(path, pattern)
    }
    return {path.as_posix() for path in included - excluded}


def _matches(path: Path, pattern: str) -> bool:
    # pathlib's ``**/*.m`` does not match a root-level ``file.m`` whereas normal
    # recursive glob semantics do. Accept the zero-directory interpretation too.
    return path.match(pattern) or (pattern.startswith("**/") and path.match(pattern[3:]))


def _isolated_parse(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "script_boundary.languages.matlab.project_worker", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        return {
            "diagnostics": [f"isolated frontend failure (exit {completed.returncode})"],
            "regions": 0,
        }
    payload = json.loads(completed.stdout)
    return {
        "diagnostics": payload["diagnostics"],
        "regions": len(payload["functions"]) + int(payload["has_script"]),
    }
