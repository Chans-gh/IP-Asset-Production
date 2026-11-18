"""Qingshui (青水) image provider via the qingshui Skill's ``scripts/run.js`` (M2).

* External provider: prompts — and any reference image — leave the machine. Qingshui uploads
  local reference files to **publicly readable URLs**; therefore only references with
  ``permission_scope`` ``approved_external``/``demo_public`` are ever passed (T11), and the
  registry must be built with ``allow_external=True``.
* The API key is read by the qingshui scripts from ``QINGSHUI_API_KEY``; this module only checks
  that it is set. It never reads, logs or stores the value.
* Capabilities are declared conservatively (SPEC §9.1 "不得虚报能力"): no native alpha, no seed,
  no mask inpainting. Native pixel sizes are *measured* from returned files and recorded in the
  task manifest; the model only accepts aspect ratios, not pixel sizes.
* Qingshui's own log (task ids, signed download URLs) stays in the private work directory.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from ..models import GenerationRequest, ProviderCapabilities
from ..paths import repo_root
from .base import DataEgress, ProviderError, ProviderImage, ProviderResult, ProviderTimeoutError, check_request_allowed

DEFAULT_MODEL = "gpt-image-2.5-flare"
SUPPORTED_ASPECTS = ("1:1", "16:9", "9:16", "4:3", "3:4")
SECRET_RE = re.compile(r"(qs-[A-Za-z0-9_-]{6,}|https?://\S+)", re.I)
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _ratio(a: str) -> float:
    w, h = a.split(":")
    return int(w) / int(h)


def closest_aspect(width: int, height: int, allowed: Sequence[str] = SUPPORTED_ASPECTS) -> str:
    target = width / height
    return min(allowed, key=lambda a: (abs(_ratio(a) - target), a))


def find_skill_dir(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """``QINGSHUI_SKILL`` or a sibling checkout of the AI-Video-Project repository."""
    candidates: list[Path] = []
    env = explicit or os.environ.get("QINGSHUI_SKILL")
    if env:
        candidates.append(Path(env))
    try:
        parent = repo_root().parent
    except FileNotFoundError:  # pragma: no cover
        parent = Path.cwd().parent
    for name in ("ai-video-project", "AI-Video-Project", "test"):
        candidates.append(parent / name / ".claude" / "skills" / "qingshui")
    for c in candidates:
        if (c / "scripts" / "run.js").is_file():
            return c.resolve()
    return None


@dataclass(frozen=True)
class ProviderStatus:
    available: bool
    reasons: tuple[str, ...]

    def explain(self) -> str:
        if self.available:
            return "qingshui provider ready"
        return (
            "qingshui provider unavailable: " + "; ".join(self.reasons) + " — only planning/prompt export is possible"
        )


def provider_status(skill_dir: Path | None = None) -> ProviderStatus:
    reasons = []
    if not os.environ.get("QINGSHUI_API_KEY"):
        reasons.append("QINGSHUI_API_KEY is not set")
    if shutil.which("node") is None:
        reasons.append("node is not installed")
    sd = skill_dir or find_skill_dir()
    if sd is None or not (sd / "scripts" / "run.js").is_file():
        reasons.append("qingshui skill (scripts/run.js) not found; set QINGSHUI_SKILL")
    return ProviderStatus(not reasons, tuple(reasons))


def sanitize(text: str) -> str:
    return SECRET_RE.sub("[redacted]", text)


class QingshuiProvider:
    def __init__(
        self,
        work_dir: Path,
        *,
        model: str = DEFAULT_MODEL,
        skill_dir: Path | None = None,
        timeout_s: int = 900,
        runner: Runner = subprocess.run,
        check_available: bool = True,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.model = model
        self.skill_dir = skill_dir or find_skill_dir()
        self.timeout_s = timeout_s
        self.runner = runner
        self._served: dict[str, int] = {}
        if check_available:
            status = provider_status(self.skill_dir)
            if not status.available:
                raise ProviderError(status.explain())
        models_json = (self.skill_dir / "scripts" / "models.json") if self.skill_dir else None
        self._aspects: tuple[str, ...] = SUPPORTED_ASPECTS
        if models_json and models_json.is_file():
            card = json.loads(models_json.read_text(encoding="utf-8")).get("image", {}).get(model)
            if card is None:
                raise ProviderError(f"model {model!r} is not listed in qingshui models.json")
            self._aspects = tuple(card.get("aspect", SUPPORTED_ASPECTS))

    # -- ImageProvider protocol ---------------------------------------------------------------
    @property
    def name(self) -> str:
        return "qingshui"

    @property
    def data_egress(self) -> DataEgress:
        return "external"

    @property
    def is_mock(self) -> bool:
        return False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            text_to_image=True,
            image_to_image=True,
            image_edit=False,
            multi_reference=self.model.startswith("gpt-image"),
            mask_inpaint=False,
            seed=False,
            negative_prompt=True,
            alpha_native=False,
            native_sizes=(),
            async_jobs=True,
            cost_estimate=True,
            max_images=1,
            max_reference_count=None,
        )

    def aspects(self) -> tuple[str, ...]:
        return self._aspects

    def _job_id(self, request: GenerationRequest) -> str:
        digest = hashlib.sha256(request.compiled_prompt.encode("utf-8")).hexdigest()[:10]
        base = re.sub(r"[^A-Za-z0-9_-]", "_", request.task_id)[:80]
        return f"{base}-{digest}"

    def known_url(self, file: Path) -> str | None:
        """URL of an image qingshui itself returned earlier (matched by SHA-256 in our private logs).

        Such an image is already hosted by qingshui, so it is passed by URL instead of being
        uploaded again (saves the upload round-trip, which can fail independently of generation).
        """
        if not file.is_file():
            return None
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        for log in sorted(self.work_dir.glob("*/gen/log.json")):
            try:
                entries = json.loads(log.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for e in entries:
                for name, sha in (e.get("sha256") or {}).items():
                    files, urls = e.get("files") or [], e.get("urls") or []
                    if sha == digest and name in files and files.index(name) < len(urls):
                        return str(urls[files.index(name)])
        return None

    def build_job(self, request: GenerationRequest) -> dict[str, Any]:
        spec = request.output_spec
        options: dict[str, Any] = {
            "model": self.model,
            "aspectRatio": closest_aspect(spec.width_px, spec.height_px, self._aspects),
        }
        negative = request.variable_values.get("negative_prompt")
        if negative:
            options["negativePrompt"] = str(negative)
        job: dict[str, Any] = {
            "id": self._job_id(request),
            "type": "image",
            "prompt": request.compiled_prompt,
            "options": options,
        }
        refs = []
        for r in request.references:
            if r.permission_scope == "private_local":  # defence in depth; check_request_allowed raises first
                raise ProviderError(f"reference {r.ref_id} is private_local")
            is_url = r.uri.startswith(("http://", "https://"))
            refs.append(r.uri if is_url else (self.known_url(Path(r.uri)) or r.uri))
        if refs:
            job["refs"] = refs
            job["refField"] = "referenceImages"
        return job

    @staticmethod
    def _finished_files(gen: Path, job_id: str) -> list[Path]:
        log = gen / "log.json"
        if not log.is_file():
            return []
        try:
            entries = json.loads(log.read_text(encoding="utf-8"))
        except ValueError:
            return []
        done = [e for e in entries if e.get("id") == job_id and e.get("status") == "done"]
        if not done:
            return []
        files = [gen.parent / f for f in done[-1].get("files") or []]
        return [f for f in files if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]

    def _run_job(self, job_dir: Path, job_file: Path) -> None:
        assert self.skill_dir is not None
        run_js = str(self.skill_dir / "scripts" / "run.js")
        try:
            check = self.runner(
                ["node", run_js, "check", str(job_file)], cwd=job_dir, capture_output=True, text=True, timeout=60
            )
            if check.returncode != 0:
                raise ProviderError("qingshui job check failed: " + sanitize((check.stderr or check.stdout)[-400:]))
            proc = self.runner(
                ["node", run_js, str(job_file)], cwd=job_dir, capture_output=True, text=True, timeout=self.timeout_s
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeoutError(f"qingshui timed out after {exc.timeout}s") from None
        (job_dir / "run.log").write_text(sanitize((proc.stdout or "") + "\n" + (proc.stderr or "")), encoding="utf-8")
        if proc.returncode != 0:
            raise ProviderError("qingshui generation failed: " + sanitize((proc.stderr or proc.stdout or "")[-400:]))

    def generate(self, request: GenerationRequest) -> ProviderResult:
        check_request_allowed(self, request)
        if self.skill_dir is None:
            raise ProviderError("qingshui skill not found")
        job = self.build_job(request)
        # A repeat request in the same process is a retry (e.g. failed hard QA): it must be a new
        # generation, so it gets a round suffix. A fresh process resumes from finished jobs instead.
        base = job["id"]
        rounds = self._served.get(base, 0)
        self._served[base] = rounds + 1
        if rounds:
            job["id"] = f"{base}-r{rounds + 1}"
        job_dir = self.work_dir / job["id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        job_file = job_dir / "job.json"
        gen = job_dir / "gen"
        if not self._finished_files(gen, job["id"]):  # same prompt+task already generated: no new call, no new cost
            job_file.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
            self._run_job(job_dir, job_file)
        files = self._finished_files(gen, job["id"])
        if not files:
            raise ProviderError("qingshui returned no image file")
        data = files[0].read_bytes()
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            size, fmt, mode = im.size, (im.format or "PNG"), im.mode
        model = self.model
        log = gen / "log.json"
        cost = None
        if log.is_file():
            entry = next(
                (e for e in reversed(json.loads(log.read_text(encoding="utf-8"))) if e.get("id") == job["id"]), None
            )
            if entry:
                cost = entry.get("quota_cost")
                model = (entry.get("options") or {}).get("model", model)
        (job_dir / "facts.json").write_text(
            json.dumps(
                {
                    "native_size": size,
                    "format": fmt,
                    "mode": mode,
                    "quota_cost": cost,
                    "aspect": job["options"]["aspectRatio"],
                }
            ),
            encoding="utf-8",
        )
        image = ProviderImage(
            data=data, width_px=size[0], height_px=size[1], format=fmt, has_alpha=mode in ("RGBA", "LA")
        )
        return ProviderResult(
            task_id=request.task_id, provider=self.name, model=model, images=(image,), native_size=size, is_mock=False
        )
