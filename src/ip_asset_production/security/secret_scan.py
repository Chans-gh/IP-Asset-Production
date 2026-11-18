"""Pre-publish privacy and secret scanner (SPEC §11, T16, T23).

Scans every file that *could* be committed (tracked + untracked-but-not-ignored, or only
staged files with ``--staged``) and fails on:

* forbidden paths: env files, keys, workspace/upload/cache dirs, the user's AIKate archive;
* media files (images, PDFs, PSDs, ...) outside the allowlisted public directories;
* style preview images not traceable to an entry in ``styles/preview_manifest.json``;
* HTML/Markdown with embedded ``data:image`` payloads (the original archive format);
* credential-looking strings and private keys;
* e-mail addresses outside documentation/example domains;
* unexpectedly large files.

There is deliberately no inline "allow" marker: fix the file or the allowlist in code review.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_FILE_BYTES = 5 * 1024 * 1024

FORBIDDEN_PATH_GLOBS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "*.sqlite",
    "*.db",
    "AIKate_*",
    "*角色资产生成清单完整版*",
]
FORBIDDEN_PATH_ALLOW = {".env.example"}
FORBIDDEN_DIR_PARTS = {"workspace", "uploads", "private", "secrets", "outputs", "cache", "logs"}

MEDIA_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".psd",
    ".ai",
    ".pdf",
    ".mp4",
    ".mov",
    ".webm",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
}
# Public media may only live here. Style previews additionally need manifest traceability.
MEDIA_ALLOWED_PREFIXES = ("styles/previews/", "tests/fixtures/synthetic/", "site/cases/")
PREVIEW_PREFIX = "styles/previews/"
# Pages case images (ADR-019): each file must be listed in its case.json — generated assets only, never source photos.
CASE_PREFIX = "site/cases/"

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("sk- style API key", re.compile(r"\bsk-(?:[A-Za-z0-9_-]{2,}-)?[A-Za-z0-9]{24,}\b")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{24,}=*")),
    (
        "hard-coded credential assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|password|passwd)\b"
            r"\s*[:=]\s*['\"][^'\"\s{}<>]{12,}['\"]"
        ),
    ),
]
EMBEDDED_IMAGE = re.compile(r"data:image/[a-z0-9.+-]+;base64,", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")
EMAIL_ALLOWED_DOMAINS = {"example.com", "example.org", "example.net", "example.invalid", "localhost"}
EMAIL_ALLOWED_ADDRESSES = {"noreply@anthropic.com"}


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    detail: str
    line: int | None = None

    def __str__(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"{loc}: {self.rule}: {self.detail}"


def candidate_files(root: Path, *, staged_only: bool = False) -> list[str]:
    """Repo-relative POSIX paths that are tracked or would be added by ``git add -A``."""
    if staged_only:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    else:
        cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    try:
        out = subprocess.run(cmd, cwd=root, check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError):
        if staged_only:
            raise
        # Not a git checkout: scan everything except VCS/venv internals.
        skip = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        return sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and not skip & set(p.relative_to(root).parts)
        )
    return sorted({p for p in out.decode("utf-8").split("\0") if p})


def _manifest_preview_files(root: Path) -> set[str]:
    manifest = root / "styles" / "preview_manifest.json"
    if not manifest.is_file():
        return set()
    items = json.loads(manifest.read_text(encoding="utf-8")).get("items", [])
    return {str(i["actual_file"]) for i in items if i.get("actual_file")}


def _case_files(root: Path) -> set[str]:
    out: set[str] = set()
    for case in sorted((root / "site" / "cases").glob("*/case.json")):
        data = json.loads(case.read_text(encoding="utf-8"))
        base = case.parent.relative_to(root).as_posix()
        for group in data.get("groups", []):
            for a in group.get("assets", []):
                out.update(f"{base}/{a[k]}" for k in ("file", "thumb") if a.get(k))
    return out


def _path_findings(rel: str, traced_previews: set[str]) -> list[Finding]:
    findings = []
    pure = PurePosixPath(rel)
    name = pure.name
    if name not in FORBIDDEN_PATH_ALLOW and any(fnmatch.fnmatch(name, g) for g in FORBIDDEN_PATH_GLOBS):
        findings.append(Finding(rel, "forbidden-file", "secret/private file type must never be committed"))
    if hit := FORBIDDEN_DIR_PARTS & set(pure.parts[:-1]):
        findings.append(Finding(rel, "forbidden-dir", f"files under {sorted(hit)} are private workspace data"))
    if pure.suffix.lower() in MEDIA_SUFFIXES:
        if not rel.startswith(MEDIA_ALLOWED_PREFIXES):
            findings.append(
                Finding(rel, "media-outside-allowlist", f"media files are only allowed under {MEDIA_ALLOWED_PREFIXES}")
            )
        elif rel.startswith((PREVIEW_PREFIX, CASE_PREFIX)) and rel not in traced_previews:
            findings.append(
                Finding(
                    rel,
                    "untraced-preview",
                    "preview/case image is not referenced by preview_manifest.json or site/cases/*/case.json",
                )
            )
    return findings


def _content_findings(rel: str, text: str) -> list[Finding]:
    findings = []
    suffix = PurePosixPath(rel).suffix.lower()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(rel, "secret", rule, lineno))
        if suffix in {".html", ".htm", ".md", ".json", ".jsonl", ".txt"} and EMBEDDED_IMAGE.search(line):
            findings.append(
                Finding(rel, "embedded-image", "base64 data:image payload (possible private image)", lineno)
            )
        for m in EMAIL.finditer(line):
            addr, domain = m.group(0), m.group(1).lower()
            if addr.lower() in EMAIL_ALLOWED_ADDRESSES or domain in EMAIL_ALLOWED_DOMAINS:
                continue
            if domain.endswith((".example", ".invalid", ".test")):
                continue
            findings.append(Finding(rel, "email-address", "personal contact data must not be published", lineno))
    return findings


def scan(root: Path, files: list[str] | None = None, *, staged_only: bool = False) -> list[Finding]:
    root = root.resolve()
    rels = files if files is not None else candidate_files(root, staged_only=staged_only)
    traced = _manifest_preview_files(root) | _case_files(root)
    findings: list[Finding] = []
    for rel in rels:
        findings += _path_findings(rel, traced)
        path = root / rel
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            findings.append(Finding(rel, "large-file", f"{size} bytes > {MAX_FILE_BYTES}; review before publishing"))
        if path.suffix.lower() in MEDIA_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding(rel, "binary-file", "unrecognised binary file; review before publishing"))
            continue
        findings += _content_findings(rel, text)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Privacy/secret scan before any public push.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--staged", action="store_true", help="scan only files staged for commit")
    args = parser.parse_args(argv)
    findings = scan(args.root, staged_only=args.staged)
    for f in findings:
        print(f, file=sys.stderr)
    if findings:
        print(f"SECRET SCAN FAILED: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print("SECRET SCAN OK: no secrets, private media or personal data found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
