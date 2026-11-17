"""Prompt library + layered PromptCompiler (SPEC §7.1, §9.2 ``compile_prompt``).

Layer order is fixed: COMMON-LOCK -> STYLE-BRANCH -> style fragment -> TASK-TEMPLATE
(-> kit item) -> CAMERA/LAYOUT (variables) -> COMMON-OUTPUT -> QA constraints.
``CORE-SYSTEM`` (``prompts/skill-core.md``) is agent behaviour, not image content, and is never
sent to an image model.

Every ``{{variable}}`` must resolve to a value (from the character version, the output spec,
template defaults or explicit caller variables). An unresolved variable raises
:class:`PromptCompileError`; it is never forwarded to a provider (SPEC §7.1).
User-supplied values are data: they are inserted verbatim after control-character stripping and
cannot introduce new template variables.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import gcd
from typing import Any

from .catalog import Template, TemplateRegistry
from .character import CharacterVersion
from .data import RepoData
from .models import GenerationRequest, OutputSpec, ReferenceImage

VAR_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
BLOCK_RE = re.compile(
    r"^(?:## PROMPT: (?P<a>[A-Z][A-Z0-9_-]*)[^\n]*|### (?P<b>[A-Z][A-Z0-9_-]+)[^\n]*)\n+```text\n(?P<body>.*?)\n```",
    re.M | re.S,
)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PROMPT_FILES = (
    "prompts/common-and-legacy.md",
    "prompts/new-assets.md",
    "prompts/application-kits.md",
    "prompts/quality-and-repair.md",
)
PROMPT_VERSION = "1.0.0"

# Upper-case variables in new-assets / application-kits mean the same as COMMON-LOCK's.
ALIASES = {
    "ip_id": "character_id",
    "palette": "palette_and_material",
    "width": "width_px",
    "height": "height_px",
    "color_space": "color_mode",
    "alpha_mode": "alpha_required",
    "render_style": "style_profile",
    "reference_images_with_roles": "reference_manifest",
    "default_outfit_or_surface": "palette_and_material",
}

GLOBAL_DEFAULTS: dict[str, str] = {
    "background": "简洁中性浅色背景",
    "lighting": "柔和均匀的棚拍光",
    "camera": "正面平视，主体完整入镜",
    "allowed_changes": "仅限本任务指定的姿态、表情、镜头或道具",
    "output_variant": "clean",
    "color_mode": "sRGB",
    "exact_text": "无（文字由排版层叠加）",
    "annotations": "无（标注由排版层叠加）",
    "reference_manifest": "无参考图，以批准定妆图与身份档案为准",
    "character_brief": "按身份锚点设计的原创角色",
}
TEMPLATE_DEFAULTS: dict[str, dict[str, str]] = {
    "BASE_VIEW": {"views": "正面、左侧面、背面、四分之三正面", "contact_sheet_grid": "2×2"},
    "BASE_DETAIL": {"feature_regions": "面部/头部识别特征与标志性附属结构"},
    "BASE_EXPRESSION": {
        "emotion_list": "开心、难过、生气、惊讶、害羞、思考、困倦、得意、委屈",
        "emotion_intensity": "中等",
    },
    "BASE_POSE": {"pose_list": "站立、坐姿、行走、挥手、指向、欢呼", "focus_region": "全身"},
    "BASE_STRUCTURE": {"requested_parts": "角色实际拥有的四肢末端与附属结构"},
    "BASE_OUTFIT": {"outfit_or_accessory": "默认日常造型"},
    "BASE_PROFILE": {"approved_profile_fields": "名称、性格标签、标志动作（文字由排版层添加；未确认字段留空）"},
    "NEW-01": {"color_regions": "主体色、辅助色、点缀色、材质色"},
    "NEW-03": {"limb_count": "按档案批准的数量", "key_appendages": "按档案批准的附属结构"},
    "NEW-04": {"surface_type": "角色已批准的表面材质"},
    "NEW-05": {"prop_list": "角色设定中的标志性道具"},
    "NEW-06": {"personality": "友好、活泼", "target_use_case": "社交内容", "signature_action_count": "6"},
    "NEW-07": {"phoneme_set": "a、o、e、i、u、m/b/p"},
    "NEW-08": {"interaction_set": "展示、指向、持握、使用"},
    "NEW-10": {"contact_cases": "坐椅、扶桌、站立、跨台阶"},
    "NEW-11": {"camera_set": "俯视30°、仰视30°、高机位三分之四、低机位三分之四"},
    "NEW-14": {"product_form": "搪胶公仔"},
    "APP-03": {"language": "中文", "arrow_direction": "无"},
    "APP-06": {"brand_colors": "角色主色", "campaign": "节日问候", "subtext": "（由排版层添加）"},
}
STYLE_BRANCH_BY_IP = {
    "digital_human": "DIGITAL_HUMAN",
    "anime_human": "ANIME_HUMAN",
    "cartoon_animal": "CARTOON_ANIMAL",
    "anthropomorphic_object": "ANTHROPOMORPHIC_OBJECT",
    "fantasy_creature": "FANTASY_OR_CUSTOM",
    "other": "FANTASY_OR_CUSTOM",
}
QA_CONSTRAINTS = (
    "质量约束：生成后将程序化校验像素、格式、透明通道与安全区，并做身份与结构一致性审查；"
    "画面中不要出现任何文字、水印或 Logo。"
)


class PromptCompileError(ValueError):
    """Missing template, variable or unsafe value; nothing was sent anywhere."""


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    negative_prompt: str | None
    template_id: str
    prompt_version: str
    layers: tuple[str, ...]
    variables: dict[str, str] = field(default_factory=dict)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class PromptLibrary:
    def __init__(self, data: RepoData | None = None) -> None:
        self.data = data or RepoData()
        self.blocks: dict[str, str] = {}
        for rel in PROMPT_FILES:
            for m in BLOCK_RE.finditer(self.data.text(rel)):
                key = m["a"] or m["b"]
                # The first definition wins (common-and-legacy defines COMMON-LOCK/OUTPUT).
                self.blocks.setdefault(key, m["body"].strip())
        branch = self.blocks.get("STYLE-BRANCH", "")
        self.branches = {m.group(1): m.group(2).strip() for m in re.finditer(r"^([A-Z_]+)：(.+)$", branch, re.M)}
        for required in ("COMMON-LOCK", "COMMON-OUTPUT", "STYLE-BRANCH", "CANONICAL"):
            if required not in self.blocks:
                raise PromptCompileError(f"prompt library is missing {required}")

    def get(self, prompt_id: str) -> str:
        try:
            return self.blocks[prompt_id]
        except KeyError:
            raise PromptCompileError(f"no prompt block {prompt_id!r}") from None


def aspect_ratio(width: int, height: int) -> str:
    g = gcd(width, height)
    return f"{width // g}:{height // g}"


def _clean(value: Any) -> str:
    if isinstance(value, bool):
        text = "是" if value else "否"
    elif isinstance(value, list | tuple):
        text = "、".join(_clean(v) for v in value)
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    text = CONTROL_RE.sub(" ", text).strip()
    if VAR_RE.search(text):
        raise PromptCompileError("variable values must not contain {{...}} template syntax")
    if len(text) > 4000:
        raise PromptCompileError("variable value too long (max 4000 chars)")
    return text


def _style_text(cv: CharacterVersion) -> str:
    sp = cv.style_profile
    parts = [
        f"{k}={sp[k]}"
        for k in ("medium", "tradition", "proportions", "material", "linework", "mood", "detail")
        if sp.get(k)
    ]
    if sp.get("style_name_zh"):
        parts.insert(0, f"{cv.style_id or ''} {sp['style_name_zh']}".strip())
    return "；".join(parts)


def _references_text(refs: tuple[ReferenceImage, ...]) -> str:
    if not refs:
        return GLOBAL_DEFAULTS["reference_manifest"]
    # Only roles and ids go into the prompt — never URIs/paths of private images.
    return "；".join(f"{r.ref_id}={r.role}" + (f"(优先级{r.priority})" if r.priority is not None else "") for r in refs)


class PromptCompiler:
    def __init__(self, registry: TemplateRegistry | None = None, library: PromptLibrary | None = None) -> None:
        self.registry = registry or TemplateRegistry()
        self.library = library or PromptLibrary(self.registry.data)

    def character_variables(self, cv: CharacterVersion) -> dict[str, str]:
        palette = "、".join(f"{k}:{v}" for k, v in cv.palette.items()) or "按定妆图"
        return {
            "character_id": cv.character_id,
            "character_version": cv.version,
            "ip_type": cv.ip_type,
            "body_topology": cv.body_topology,
            "style_profile": _style_text(cv),
            "identity_anchors": "、".join(cv.identity_anchors),
            "palette_and_material": palette,
            "allowed_changes": "、".join(cv.allowed_variations) or GLOBAL_DEFAULTS["allowed_changes"],
            "reference_manifest": _references_text(cv.reference_manifest),
        }

    def output_variables(self, template: Template, spec: OutputSpec, variant: str) -> dict[str, str]:
        safe = spec.safe_margin_pct if spec.safe_margin_pct is not None else 0.08
        return {
            "asset_template_id": template.template_id,
            "output_variant": variant,
            "width_px": str(spec.width_px),
            "height_px": str(spec.height_px),
            "single_width": str(spec.width_px),
            "single_height": str(spec.height_px),
            "aspect_ratio": aspect_ratio(spec.width_px, spec.height_px),
            "format": spec.format,
            "color_mode": spec.color_mode or "sRGB",
            "alpha_required": "是（真实 alpha 通道）" if spec.alpha_required else "否",
            "safe_margin": f"{round(safe * 100)}%",
        }

    def render(self, block: str, values: Mapping[str, str]) -> str:
        def sub(m: re.Match[str]) -> str:
            raw = m.group(1).strip()
            key = raw.lower()
            key = ALIASES.get(key, key)
            if key not in values:
                raise PromptCompileError(f"unresolved template variable {{{{{raw}}}}}")
            return values[key]

        return VAR_RE.sub(sub, block)

    def compile(
        self,
        cv: CharacterVersion,
        template_id: str,
        *,
        variables: Mapping[str, Any] | None = None,
        output_spec: OutputSpec | None = None,
        variant: str | None = None,
        kit_item: str | None = None,
        adaptation: str | None = None,
    ) -> RenderedPrompt:
        template = self.registry.get(template_id)
        if template_id != "CANONICAL" and cv.approval_status != "approved":
            raise PromptCompileError("asset prompts require an approved character version (G3)")
        spec = output_spec or OutputSpec.model_validate(dict(template.primary_output))
        variant = variant or (template.variants[0] if template.variants else "clean")
        values: dict[str, str] = dict(GLOBAL_DEFAULTS)
        values.update(TEMPLATE_DEFAULTS.get(template_id, {}))
        values.update(self.character_variables(cv))
        values.update(self.output_variables(template, spec, variant))
        for k, v in (variables or {}).items():
            values[ALIASES.get(k.lower(), k.lower())] = _clean(v)

        layers = ["COMMON-LOCK", "STYLE-BRANCH"]
        parts = [self.render(self.library.get("COMMON-LOCK"), values)]
        branch_key = STYLE_BRANCH_BY_IP[cv.ip_type]
        parts.append(f"风格分支 {branch_key}：{self.library.branches[branch_key]}")
        fragment = cv.style_profile.get("prompt_fragment_en")
        if fragment and not cv.is_digital_human:
            layers.append("STYLE-PRESET")
            parts.append(f"已确认的视觉风格（{cv.style_id}）：{fragment}")
            enforce = cv.style_profile.get("enforce") or {}
            if enforce.get("rendering") == "nearest_neighbor_no_antialias":
                parts.append("像素风格：保持清晰像素网格与硬边，不做抗锯齿。")
            if enforce.get("rendering") == "static_still_only":
                parts.append("这是静态画面，不是动画帧序列。")
        layers.append(f"TASK:{template.prompt_id}")
        parts.append(self.render(self.library.get(template.prompt_id), values))
        if adaptation:
            layers.append("ADAPT")
            parts.append(f"结构适配：{_clean(adaptation)}，按角色自身结构表达，不添加不存在的部位。")
        if kit_item:
            layers.append("KIT-ITEM")
            parts.append(f"本次请求只生成该系列中的一张独立图：{_clean(kit_item)}。")
        layers += ["COMMON-OUTPUT", "QA"]
        parts.append(self.render(self.library.get("COMMON-OUTPUT"), values))
        parts.append(QA_CONSTRAINTS)
        text = "\n".join(parts)
        leftover = VAR_RE.findall(text)
        if leftover:  # pragma: no cover - render() raises first
            raise PromptCompileError(f"unresolved variables {leftover}")
        negative: str | None = None
        if cv.style_id and not cv.is_digital_human:
            styles = self.registry.data.style_catalog["styles"]
            negative = next((s["negative_prompt_en"] for s in styles if s["style_id"] == cv.style_id), None)
        return RenderedPrompt(text, negative, template_id, PROMPT_VERSION, tuple(layers), values)

    def to_request(
        self,
        cv: CharacterVersion,
        template_id: str,
        task_id: str,
        *,
        approved: bool,
        output_spec: OutputSpec | None = None,
        references: tuple[ReferenceImage, ...] | None = None,
        provider_preference: str | None = None,
        **compile_kwargs: Any,
    ) -> tuple[GenerationRequest, RenderedPrompt]:
        """SPEC §9.2 ``compile_prompt(...) -> GenerationRequest``."""
        template = self.registry.get(template_id)
        spec = output_spec or OutputSpec.model_validate(dict(template.primary_output))
        rendered = self.compile(cv, template_id, output_spec=spec, **compile_kwargs)
        refs = cv.reference_manifest if references is None else references
        req = GenerationRequest(
            task_id=task_id,
            template_id=template_id,
            character_id=cv.character_id,
            character_version=cv.version,
            compiled_prompt=rendered.text,
            output_spec=spec,
            approval_status="approved" if approved else "pending",
            provider_preference=provider_preference,
            references=tuple(refs),
            variable_values={
                "prompt_sha256": rendered.sha256,
                "prompt_version": rendered.prompt_version,
                "negative_prompt": rendered.negative_prompt,
                "layers": list(rendered.layers),
            },
        )
        return req, rendered
