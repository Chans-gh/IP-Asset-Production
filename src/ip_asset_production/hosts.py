"""Host packaging and diagnostics for DeepSeek Harness and WorkBuddy (SPEC §10; T14, T15).

What this module can verify offline: the skill folder layout (``<name>/SKILL.md`` with
kebab-case ``name`` equal to the folder), referenced resources, a reproducible ZIP with SHA-256,
and the runtime prerequisites (Python deps, provider status, CJK font). What it can **not**
verify: that a real host instance discovers, enables and runs the skill — that is recorded only
from real host tests (M4/M5) in ``docs/HOST_TESTS.md``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import repo_root

SKILL_NAME = "ip-asset-production"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
# Files shipped inside the skill package (relative to repo root).
PACKAGE_TREES = ("prompts", "catalogs", "schemas", "src/ip_asset_production")
PACKAGE_FILES = (
    "styles/catalog.json",
    "styles/taxonomy.json",
    "styles/prototypes.json",
    "styles/compatibility.json",
    "styles/legacy_style_aliases.json",
    "styles/preview_manifest.json",
    "styles/preview_requests.jsonl",
    "docs/SPEC.md",
    "docs/STYLE_LIBRARY_AND_PREVIEWS.md",
    "LICENSE",
    "pyproject.toml",
)
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


class PackagingError(RuntimeError):
    pass


@dataclass
class SkillCheck:
    ok: bool
    name: str | None
    problems: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise PackagingError("SKILL.md must start with a --- YAML frontmatter block")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta


def check_skill_dir(skill_dir: Path) -> SkillCheck:
    problems = []
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return SkillCheck(False, None, [f"{md} missing"])
    text = md.read_text(encoding="utf-8")
    try:
        meta = parse_frontmatter(text)
    except PackagingError as exc:
        return SkillCheck(False, None, [str(exc)])
    name = meta.get("name")
    if not name or not NAME_RE.match(name):
        problems.append(f"name {name!r} must be kebab-case")
    if name != skill_dir.name:
        problems.append(f"name {name!r} must equal folder name {skill_dir.name!r}")
    desc = meta.get("description", "")
    if not 20 <= len(desc) <= 1024:
        problems.append("description must be 20..1024 characters")
    for ref in re.findall(r"`((?:prompts|catalogs|schemas|styles|docs|scripts)/[^`\s]+)`", text):
        if not (skill_dir / ref).exists():
            problems.append(f"SKILL.md references missing resource {ref}")
    return SkillCheck(not problems, name, problems)


def build_skill_folder(dest_parent: Path, root: Path | None = None, *, include_previews: bool = True) -> Path:
    """Assemble ``<dest_parent>/ip-asset-production/`` with SKILL.md at its root."""
    root = root or repo_root()
    dest = dest_parent / SKILL_NAME
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copyfile(root / "skill" / SKILL_NAME / "SKILL.md", dest / "SKILL.md")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".mypy_cache")
    for tree in PACKAGE_TREES:
        shutil.copytree(root / tree, dest / tree, ignore=ignore)
    for f in PACKAGE_FILES:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / f, dest / f)
    scripts = dest / "scripts"
    scripts.mkdir()
    (scripts / "ipap.py").write_text(
        "#!/usr/bin/env python3\n"
        '"""Skill entry: python scripts/ipap.py <command> (see SKILL.md)."""\n'
        "import os, sys\n"
        "HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
        'sys.path.insert(0, os.path.join(HERE, "src"))\n'
        'os.environ.setdefault("IPAP_ROOT", HERE)\n'
        "from ip_asset_production.cli import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )
    if include_previews:
        manifest = json.loads((root / "styles/preview_manifest.json").read_text(encoding="utf-8"))
        for item in manifest["items"]:
            if item.get("status") == "approved" and item.get("actual_file"):
                src = root / item["actual_file"]
                if src.is_file():
                    (dest / item["actual_file"]).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest / item["actual_file"])
    check = check_skill_dir(dest)
    if not check.ok:
        raise PackagingError("; ".join(check.problems))
    return dest


def zip_folder(folder: Path, zip_path: Path) -> str:
    """Deterministic ZIP (sorted entries, fixed timestamps); returns its SHA-256."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                info = zipfile.ZipInfo(f"{folder.name}/{p.relative_to(folder).as_posix()}", FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if p.suffix == ".py" and p.parent.name == "scripts" else 0o644) << 16
                zf.writestr(info, p.read_bytes())
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_path.with_suffix(zip_path.suffix + ".sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return digest


def install_deepseek(project_dir: Path, root: Path | None = None, *, location: str = ".agents/skills") -> Path:
    """Copy the skill into a project's DeepSeek Harness skills directory (``.agents/skills`` or ``.dsh/skills``).

    Copying is not enabling: the Harness configuration must enable a filesystem skill provider.
    """
    if location not in (".agents/skills", ".dsh/skills"):
        raise PackagingError("location must be .agents/skills or .dsh/skills")
    target_parent = project_dir / location
    existing = target_parent / SKILL_NAME
    if existing.exists() and not (existing / "SKILL.md").is_file():
        raise PackagingError(f"{existing} exists and is not this skill — refusing to overwrite (name conflict)")
    return build_skill_folder(target_parent, root)


def diagnose() -> dict[str, Any]:
    """Runtime prerequisites. The host itself (enabled provider, permissions) is NOT checked here."""
    from .providers.qingshui import provider_status
    from .typography import TypographyError, find_font

    deps = {m: importlib.util.find_spec(m) is not None for m in ("pydantic", "jsonschema", "PIL", "fontTools")}
    try:
        font: str | None = find_font().family
    except TypographyError:
        font = None
    status = provider_status()
    return {
        "python": sys.version.split()[0],
        "python_ok": sys.version_info >= (3, 11),
        "dependencies": deps,
        "cjk_font": font,
        "image_provider": {
            "qingshui": {"available": status.available, "reasons": list(status.reasons)},
            "mock": {"available": True, "is_mock": True},
        },
        "can_generate_real_images": status.available,
        "note_zh": "宿主是否已启用本 Skill 无法在此自检；无真实图像 Provider 时只能输出计划与 Prompt。",
    }
