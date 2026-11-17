"""M2A: generate, review and publish the style preview images (SPEC §4A.4-4A.8; T23, T25-T27).

Flow per manifest item: planned -> (provider) -> generated (file copied into
``styles/previews/<subject>/``, metadata stripped, hashes recorded) -> review -> approved/rejected.
Mock providers are refused here: placeholder images must never enter the public preview folder.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .character import utc_now
from .jobs import TaskOutcome, TaskRunner, save_png
from .models import GenerationRequest, OutputSpec, TaskStatus
from .paths import safe_join
from .providers.base import ImageProvider
from .styles import PreviewManifest, StyleError

PREVIEW_SPEC = OutputSpec(width_px=1024, height_px=1024, format="PNG", alpha_required=False)


@dataclass(frozen=True)
class PreviewRun:
    preview_id: str
    status: str
    outcome: TaskOutcome


def preview_request(item: dict[str, Any], provider: ImageProvider) -> GenerationRequest:
    prompt = item["prompt"]
    if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != item["prompt_sha256"]:
        raise StyleError(f"{item['preview_id']}: prompt does not match prompt_sha256")
    return GenerationRequest(
        task_id=item["preview_id"],
        template_id="STYLE_PREVIEW",
        character_id=item["prototype_id"].lower().replace("_", "-"),
        character_version="proto-v1",
        compiled_prompt=prompt,
        output_spec=PREVIEW_SPEC,
        approval_status="approved",  # the 138-item plan is the approved M2A task list
        provider_preference=provider.name,
    )


def generate_previews(
    manifest: PreviewManifest,
    runner: TaskRunner,
    repo_root: Path,
    preview_ids: list[str],
    *,
    pixel_art_styles: frozenset[str] = frozenset(),
) -> list[PreviewRun]:
    if runner.provider.is_mock:
        raise StyleError("refusing to write mock images into styles/previews (ADR-011)")
    runs = []
    for pid in preview_ids:
        item = manifest.item(pid)
        if item["status"] == "approved":
            continue
        req = preview_request(item, runner.provider)
        outcome = runner.run(req, fit_mode="cover", pixel_art=item["style_id"] in pixel_art_styles)
        if outcome.delivered:
            src = safe_join(runner.task_dir(pid), outcome.files[0].path)
            dest = safe_join(repo_root, item["expected_file"])
            img = Image.open(src)
            img.load()
            save_png(img.convert("RGB"), dest, mock=False)  # re-encode: no provider metadata
            sha = hashlib.sha256(dest.read_bytes()).hexdigest()
            manifest.transition(
                pid,
                "generated",
                actual_file=item["expected_file"],
                provider=runner.provider.name,
                model=outcome.model,
                created_at=utc_now(),
                review_status="pending_review",
                file_sha256=sha,
                native_size=list(outcome.native_size) if outcome.native_size else None,
                postprocess_steps=outcome.steps,
                upscaled=outcome.extras.get("upscaled"),
                attempts=outcome.attempts,
                errors=outcome.errors,
            )
        else:
            manifest.transition(
                pid, "failed", errors=outcome.errors, attempts=outcome.attempts, provider=runner.provider.name
            )
        manifest.save()
        runs.append(PreviewRun(pid, manifest.item(pid)["status"], outcome))
    return runs


def review_preview(
    manifest: PreviewManifest,
    repo_root: Path,
    preview_id: str,
    *,
    approved: bool,
    reviewer: str,
    notes: str,
    soft_checks: dict[str, str] | None = None,
    license_review: str = "cleared",
) -> dict[str, Any]:
    """Record the §4A.6 review. Approval re-verifies the file on disk (1024² PNG, hash)."""
    item = manifest.item(preview_id)
    if item["status"] not in ("generated", "review", "approved", "rejected"):
        raise StyleError(f"{preview_id} is {item['status']}; generate it first")
    record = {"reviewer": reviewer, "notes": notes, "at": utc_now(), "soft_checks": soft_checks or {}}
    if not approved:
        return manifest.transition(preview_id, "rejected", review_status="rejected", review=record)
    path = safe_join(repo_root, item["actual_file"])
    with Image.open(path) as im:
        ok = im.format == "PNG" and im.size == (1024, 1024)
    if not ok:
        raise StyleError(f"{preview_id}: file is not a 1024x1024 PNG")
    if hashlib.sha256(path.read_bytes()).hexdigest() != item.get("file_sha256"):
        raise StyleError(f"{preview_id}: file changed since generation")
    return manifest.transition(
        preview_id, "approved", review_status="approved", review=record, license_review=license_review
    )


def outcome_status(run: PreviewRun) -> str:
    return "ok" if run.outcome.status in (TaskStatus.PASSED, TaskStatus.NEEDS_REVIEW) else "failed"
