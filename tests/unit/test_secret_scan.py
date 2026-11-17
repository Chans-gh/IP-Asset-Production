"""T16/T23: the pre-publish scan blocks private media, secrets and personal data.

Sensitive-looking sample strings are assembled at runtime so this file itself stays clean.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from ip_asset_production.security.secret_scan import scan


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "README.md").write_text("# clean\ncontact: someone@example.com\n", encoding="utf-8")
    return r


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return buf.getvalue()


def rules(repo: Path, **kw: bool) -> set[tuple[str, str]]:
    return {(f.path, f.rule) for f in scan(repo, **kw)}


def test_clean_repo_passes(repo: Path) -> None:
    assert scan(repo) == []


def test_real_repository_is_clean(root: Path) -> None:
    findings = scan(root)
    assert findings == [], "\n".join(map(str, findings))


@pytest.mark.parametrize(
    "rel",
    [".env", "config/.env.local", "keys/deploy.pem", "AIKate_archive.html", "id_rsa"],
)
def test_forbidden_files(repo: Path, rel: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n", encoding="utf-8")
    assert (rel, "forbidden-file") in rules(repo)


def test_env_example_allowed(repo: Path) -> None:
    (repo / ".env.example").write_text("IMAGE_PROVIDER=mock\n", encoding="utf-8")
    assert scan(repo) == []


def test_workspace_dir_blocked_even_if_not_ignored(repo: Path) -> None:
    (repo / "workspace" / "private").mkdir(parents=True)
    (repo / "workspace" / "private" / "notes.txt").write_text("x", encoding="utf-8")
    assert ("workspace/private/notes.txt", "forbidden-dir") in rules(repo)


def test_gitignored_files_are_not_candidates(repo: Path) -> None:
    (repo / ".gitignore").write_text("workspace/\n", encoding="utf-8")
    (repo / "workspace").mkdir()
    (repo / "workspace" / "face.png").write_bytes(_png())
    assert scan(repo) == []


def test_media_outside_allowlist(repo: Path) -> None:
    (repo / "docs").mkdir()
    (repo / "docs" / "portrait.jpg").write_bytes(b"\xff\xd8\xff")
    assert ("docs/portrait.jpg", "media-outside-allowlist") in rules(repo)


def test_untraced_preview_blocked_and_traced_preview_allowed(repo: Path) -> None:
    prev = repo / "styles" / "previews" / "animal"
    prev.mkdir(parents=True)
    (prev / "STYLE-001-ANIMAL_PROTO.png").write_bytes(_png())
    assert ("styles/previews/animal/STYLE-001-ANIMAL_PROTO.png", "untraced-preview") in rules(repo)

    manifest = {"items": [{"actual_file": "styles/previews/animal/STYLE-001-ANIMAL_PROTO.png"}]}
    (repo / "styles" / "preview_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert scan(repo) == []


def test_embedded_base64_image_in_html(repo: Path) -> None:
    payload = "data:image/png;" + "base64,iVBORw0KGgo="
    (repo / "gallery.html").write_text(f'<img src="{payload}">', encoding="utf-8")
    assert ("gallery.html", "embedded-image") in rules(repo)


@pytest.mark.parametrize(
    "secret",
    [
        "-----BEGIN " + "RSA PRIVATE KEY-----",
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "ghp_" + "a1" * 18,
        "sk-" + "proj-" + "Ab3" * 10,
        "Authorization: Bearer " + "eyJhbGciOi" * 4,
        "api_key" + ' = "' + "Zx9" * 6 + '"',
    ],
)
def test_secret_patterns(repo: Path, secret: str) -> None:
    (repo / "config.py").write_text(f"X = 1\n{secret}\n", encoding="utf-8")
    found = [f for f in scan(repo) if f.path == "config.py"]
    assert found and found[0].rule == "secret" and found[0].line == 2


def test_placeholder_credentials_are_not_flagged(repo: Path) -> None:
    (repo / "doc.md").write_text('api_key = "{{IMAGE_API_KEY}}"\npassword = "<set me>"\n', encoding="utf-8")
    assert scan(repo) == []


def test_personal_email_flagged(repo: Path) -> None:
    addr = "real.person" + "@" + "gmail.com"
    (repo / "AUTHORS").write_text(addr + "\n", encoding="utf-8")
    assert ("AUTHORS", "email-address") in rules(repo)


def test_binary_file_flagged(repo: Path) -> None:
    (repo / "blob.bin").write_bytes(b"\x00\xff\xfe\x80" * 10)
    assert ("blob.bin", "binary-file") in rules(repo)


def test_staged_only_mode(repo: Path) -> None:
    (repo / ".env").write_text("x", encoding="utf-8")
    assert scan(repo, staged_only=True) == []
    _git(repo, "add", "-f", ".env")
    assert (".env", "forbidden-file") in rules(repo, staged_only=True)
