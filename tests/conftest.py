from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_DIRS = ["docs", "catalogs", "prompts", "schemas", "styles", "skill"]


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture
def repo_copy(tmp_path: Path) -> Path:
    """A disposable copy of the repository's data files for mutation tests."""
    dst = tmp_path / "repo"
    for d in DATA_DIRS:
        shutil.copytree(ROOT / d, dst / d)
    (dst / "tests").mkdir()
    shutil.copy2(ROOT / "tests" / "acceptance_cases.json", dst / "tests" / "acceptance_cases.json")
    return dst


JsonEdit = Callable[[Path, str, Callable[[Any], Any]], None]


@pytest.fixture
def edit_json() -> JsonEdit:
    def _edit(root: Path, rel: str, fn: Callable[[Any], Any]) -> None:
        path = root / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        result = fn(data)
        path.write_text(json.dumps(data if result is None else result, ensure_ascii=False, indent=2), encoding="utf-8")

    return _edit
