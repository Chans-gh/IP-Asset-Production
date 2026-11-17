"""Repository root discovery and path-traversal-safe joins."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV_VAR = "IPAP_ROOT"
_ROOT_MARKER = Path("docs") / "SPEC.md"


class UnsafePathError(ValueError):
    """Raised when a relative path would escape its base directory."""


def repo_root(start: Path | None = None) -> Path:
    """Return the repository/data root.

    Resolution order: ``$IPAP_ROOT``; otherwise walk upward from ``start`` (or this
    file) until a directory containing ``docs/SPEC.md`` is found.
    """
    env = os.environ.get(ROOT_ENV_VAR)
    if env:
        root = Path(env).resolve()
        if not (root / _ROOT_MARKER).is_file():
            raise FileNotFoundError(f"{ROOT_ENV_VAR}={env} does not contain {_ROOT_MARKER}")
        return root
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / _ROOT_MARKER).is_file():
            return candidate
    raise FileNotFoundError(f"could not locate repository root containing {_ROOT_MARKER}")


def safe_join(base: Path, relative: str | os.PathLike[str]) -> Path:
    """Join ``relative`` onto ``base`` and refuse anything that escapes ``base``.

    Absolute paths, ``..`` escapes and symlinks pointing outside ``base`` are rejected.
    """
    rel = Path(relative)
    if rel.is_absolute():
        raise UnsafePathError(f"absolute path not allowed: {relative}")
    base_resolved = base.resolve()
    target = (base_resolved / rel).resolve()
    if not target.is_relative_to(base_resolved):
        raise UnsafePathError(f"path escapes base directory: {relative}")
    return target
