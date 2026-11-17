"""Style library: recommendation, style_profile binding, preview prompts and manifest (SPEC §4, §4A).

Only previews with ``status == approved`` *and* an existing non-mock ``actual_file`` count as
"preview available". Planned entries are task descriptions, never images (T25).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data import RepoData, load_json
from .paths import UnsafePathError, safe_join

PREVIEW_LAYOUT = (
    "Same neutral warm-white studio background, centered full-body character, calm three-quarter-friendly "
    "front view, consistent framing, soft floor shadow where suitable, clean 1024x1024 square preview, "
    "no words, no logos, no watermark."
)
# ip_type -> catalog supported_subjects key
SUBJECT_KEY = {
    "anime_human": "anime_human",
    "cartoon_animal": "animal",
    "anthropomorphic_object": "anthropomorphic_object",
    "fantasy_creature": "fantasy_creature",
    "other": None,
}
# prototypes.json keys are catalog subject keys; previews/<dir>
PREVIEW_DIR = {
    "anime_human": "human",
    "animal": "animal",
    "anthropomorphic_object": "object",
    "fantasy_creature": "fantasy",
}
REQUEST_FIELDS = (
    "preview_id",
    "style_id",
    "prototype_id",
    "subject_type",
    "expected_file",
    "output_spec",
    "prompt",
    "prompt_sha256",
)
PREVIEW_TRANSITIONS = {
    "planned": {"generating", "generated", "failed"},
    "generating": {"generated", "failed", "planned"},
    "generated": {"review", "approved", "rejected", "failed", "planned"},
    "review": {"approved", "rejected", "planned"},
    "failed": {"planned", "generating", "generated"},
    "rejected": {"planned", "generating", "generated"},
    "approved": {"review", "rejected"},
}


class StyleError(ValueError):
    pass


@dataclass(frozen=True)
class StyleOption:
    style_id: str
    group_id: str
    group_name_zh: str
    display_name_zh: str
    description_zh: str
    preview_file: str | None
    preview_status: str
    score: float

    @property
    def preview_available(self) -> bool:
        return self.preview_file is not None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compile_preview_prompt(subject_en: str, style: Mapping[str, Any]) -> str:
    """``PROTOTYPE.subject_en + STYLE.prompt_fragment_en + COMMON_PREVIEW_LAYOUT + STYLE.negative``."""
    return (
        f"{subject_en}. Apply ONLY the following visual style: {style['prompt_fragment_en']}. "
        f"{PREVIEW_LAYOUT} {style['negative_prompt_en']}"
    )


class StyleLibrary:
    def __init__(self, data: RepoData | None = None) -> None:
        self.data = data or RepoData()
        cat = self.data.style_catalog
        self.groups = {g["group_id"]: g for g in cat["groups"]}
        self.styles: dict[str, dict[str, Any]] = {s["style_id"]: s for s in cat["styles"]}
        self.aliases: dict[str, str] = self.data.style_aliases.get("aliases", {})
        self.prototypes: dict[str, dict[str, Any]] = self.data.style_prototypes["prototypes"]

    # -- lookup -----------------------------------------------------------------------------
    def resolve(self, style_id: str) -> dict[str, Any]:
        sid = self.aliases.get(style_id, style_id)
        if sid not in self.styles:
            raise StyleError(f"unknown style_id {style_id!r}")
        return self.styles[sid]

    def compatibility_rules(self, style_id: str) -> dict[str, str]:
        style = self.resolve(style_id)
        enforce: dict[str, str] = {}
        for c in self.data.style_compatibility.get("constraints", []):
            if all(style.get(k) == v for k, v in c["applies_to"].items()):
                enforce.update(c["enforce"])
        return enforce

    def style_profile(self, style_id: str, *, confirmed: bool) -> dict[str, Any]:
        """Structured multi-dimensional profile for a CharacterVersion (SPEC §4)."""
        s = self.resolve(style_id)
        profile: dict[str, Any] = {
            "medium": s["medium"],
            "tradition": s["tradition"],
            "proportions": s["proportions"],
            "material": s["material"],
            "linework": s["linework"],
            "mood": ",".join(s["mood"]),
            "detail": s["detail"],
            "style_id": s["style_id"],
            "style_name_zh": s["display_name_zh"],
            "prompt_fragment_en": s["prompt_fragment_en"],
            "style_confirmed": confirmed,
        }
        rules = self.compatibility_rules(style_id)
        if rules:
            profile["enforce"] = rules
        return profile

    # -- previews ---------------------------------------------------------------------------
    def manifest_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = self.data.preview_manifest["items"]
        return items

    def preview_is_displayable(self, item: Mapping[str, Any]) -> bool:
        if item.get("status") != "approved" or not item.get("actual_file"):
            return False
        if (item.get("provider") or "").lower() == "mock":
            return False
        if item.get("license_review") not in ("cleared", "approved"):
            return False
        try:
            path = safe_join(self.data.root, str(item["actual_file"]))
        except UnsafePathError:
            return False
        return path.is_file()

    def approved_previews(self, style_id: str, subject: str | None = None) -> list[dict[str, Any]]:
        sid = self.resolve(style_id)["style_id"]
        return [
            i
            for i in self.manifest_items()
            if i["style_id"] == sid
            and (subject is None or i["subject_type"] == subject)
            and self.preview_is_displayable(i)
        ]

    # -- recommendation (SPEC §4A.5, T19/T20) -------------------------------------------------
    def candidates(self, ip_type: str) -> list[dict[str, Any]]:
        if ip_type == "digital_human":
            return []  # digital humans stay photoreal; no anime style branch (SPEC §4)
        key = SUBJECT_KEY.get(ip_type)
        return [
            s
            for s in self.styles.values()
            if s["status"] != "retired" and (key is None or key in s["supported_subjects"])
        ]

    def recommend(
        self,
        ip_type: str,
        hints: str = "",
        *,
        limit: int = 6,
        require_preview: bool = False,
        exclude: Iterable[str] = (),
    ) -> list[StyleOption]:
        if not 1 <= limit <= 48:
            raise StyleError("limit must be 1..48")
        key = SUBJECT_KEY.get(ip_type)
        excluded = {self.resolve(e)["style_id"] for e in exclude}
        hint_tokens = {t for t in re.split(r"[\s,，、;；/]+", hints.lower()) if t}
        scored: list[tuple[float, dict[str, Any], dict[str, Any] | None]] = []
        for s in self.candidates(ip_type):
            if s["style_id"] in excluded:
                continue
            previews = self.approved_previews(s["style_id"], key)
            if require_preview and not previews:
                continue
            score = 0.0
            if previews:
                score += 10
            if s["preview_prototype_preference"] == key:
                score += 1
            haystack = " ".join(
                [
                    s["display_name_zh"],
                    s["description_zh"],
                    s["medium"],
                    s["tradition"],
                    s["material"],
                    s["linework"],
                    s["proportions"],
                    s["detail"],
                    *s["mood"],
                    s["prompt_fragment_en"],
                ]
            ).lower()
            score += sum(3 for t in hint_tokens if t in haystack)
            scored.append((score, s, previews[0] if previews else None))
        scored.sort(key=lambda x: (-x[0], x[1]["style_id"]))
        # Spread across families so the user compares clearly different directions.
        picked: list[tuple[float, dict[str, Any], dict[str, Any] | None]] = []
        per_group: dict[str, int] = {}
        for cap in (1, 2, 6):
            for entry in scored:
                if len(picked) >= limit:
                    break
                g = entry[1]["group_id"]
                if entry in picked or per_group.get(g, 0) >= cap:
                    continue
                picked.append(entry)
                per_group[g] = per_group.get(g, 0) + 1
        picked.sort(key=lambda x: (-x[0], x[1]["style_id"]))
        return [
            StyleOption(
                style_id=s["style_id"],
                group_id=s["group_id"],
                group_name_zh=self.groups[s["group_id"]]["name_zh"],
                display_name_zh=s["display_name_zh"],
                description_zh=s["description_zh"],
                preview_file=p["actual_file"] if p else None,
                preview_status="approved" if p else "unavailable",
                score=score,
            )
            for score, s, p in picked
        ]


# -- preview manifest: planning and state updates (M1A / M2A) --------------------------------


def planned_preview_items(data: RepoData) -> list[dict[str, Any]]:
    """Recompute the 138 planned preview requests from catalog + prototypes (core subjects only)."""
    lib = StyleLibrary(data)
    items = []
    for sid in sorted(lib.styles):
        s = lib.styles[sid]
        for subject in ("animal", "anime_human", "anthropomorphic_object"):
            if subject not in s["supported_subjects"]:
                continue
            proto = lib.prototypes[subject]
            pid = f"{sid}-{proto['id']}"
            prompt = compile_preview_prompt(proto["subject_en"], s)
            items.append(
                {
                    "preview_id": pid,
                    "style_id": sid,
                    "prototype_id": proto["id"],
                    "subject_type": subject,
                    "expected_file": f"styles/previews/{PREVIEW_DIR[subject]}/{pid}.png",
                    "output_spec": {
                        "width_px": 1024,
                        "height_px": 1024,
                        "aspect_ratio": "1:1",
                        "format": "PNG",
                        "background": "warm_white",
                        "text_overlay": False,
                    },
                    "prompt": prompt,
                    "prompt_sha256": sha256_text(prompt),
                }
            )
    return items


class PreviewManifest:
    """Atomic read-modify-write of ``styles/preview_manifest.json`` with status transitions."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.doc: dict[str, Any] = load_json(self.path)
        self._by_id = {i["preview_id"]: i for i in self.doc["items"]}

    def item(self, preview_id: str) -> dict[str, Any]:
        try:
            return self._by_id[preview_id]
        except KeyError:
            raise StyleError(f"unknown preview_id {preview_id!r}") from None

    def items(self, *, status: str | None = None) -> list[dict[str, Any]]:
        return [i for i in self.doc["items"] if status is None or i["status"] == status]

    def first_per_style(self) -> list[dict[str, Any]]:
        """One preview per style for the 48-image gate, preferring the style's preferred subject."""
        chosen: dict[str, dict[str, Any]] = {}
        for i in self.doc["items"]:
            sid = i["style_id"]
            current = chosen.get(sid)
            if current is None or (i["status"] == "approved" and current["status"] != "approved"):
                chosen[sid] = i
        return [chosen[k] for k in sorted(chosen)]

    def transition(self, preview_id: str, status: str, **fields: Any) -> dict[str, Any]:
        item = self.item(preview_id)
        if status != item["status"] and status not in PREVIEW_TRANSITIONS.get(item["status"], set()):
            raise StyleError(f"{preview_id}: cannot go from {item['status']} to {status}")
        if status == "approved":
            provider = fields.get("provider", item.get("provider"))
            if (provider or "").lower() == "mock":
                raise StyleError("mock previews can never be approved (ADR-011)")
            if fields.get("license_review", item.get("license_review")) not in ("cleared", "approved"):
                raise StyleError("approval requires license_review cleared")
            if not fields.get("actual_file", item.get("actual_file")):
                raise StyleError("approval requires actual_file")
        if status == "planned":
            fields.setdefault("actual_file", None)
        item.update(fields)
        item["status"] = status
        return item

    def save(self) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=self.path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, self.path)
