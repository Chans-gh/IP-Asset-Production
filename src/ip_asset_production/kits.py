"""Ready-to-use application kits (SPEC §6, §9.2 ``build_application_kit``; T06, T07, T18).

Each kit delivers *independent real files* (never one overview standing in for N items), exact
text from the typography layer, print PDFs with trim/bleed boxes where relevant, a preview sheet
and ``kit_manifest.json`` with sha256 + QA per file. Partial success is reported, not hidden.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .character import CharacterVersion, utc_now
from .data import RepoData
from .jobs import TaskOutcome, TaskRunner, save_png
from .models import OutputSpec, ReferenceImage
from .paths import safe_join
from .postprocess import WARM_WHITE, contact_sheet, fit_to_spec
from .print_layout import PrintSpec, write_print_pdf
from .prompting import PromptCompiler
from .qa import Check, check_image_file, check_print_pdf, check_text, finalize
from .typography import FontChoice, TextRecord, draw_text, find_font


class KitError(RuntimeError):
    pass


@dataclass
class KitContext:
    character: CharacterVersion
    compiler: PromptCompiler
    runner: TaskRunner
    out_dir: Path
    approved: bool
    font: FontChoice | None = None
    batch_id: str = "kit"
    # Extra references sent with every kit item (e.g. the approved canonical image as identity ref).
    # They pass the same egress check as any reference: private_local never leaves the machine.
    references: tuple[ReferenceImage, ...] = ()

    def __post_init__(self) -> None:
        if self.character.approval_status != "approved":
            raise KitError("kits require an approved character version (G3)")
        if not self.approved:
            raise KitError("kit generation requires the approved plan (G4)")

    @property
    def is_mock(self) -> bool:
        return self.runner.provider.is_mock

    def need_font(self) -> FontChoice:
        if self.font is None:
            self.font = find_font()
        return self.font


@dataclass
class KitResult:
    kit_id: str
    manifest_path: Path
    manifest: dict[str, Any]
    outcomes: list[TaskOutcome] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return bool(self.manifest["partial"])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _tint(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(c + (255 - c) * amount) for c in rgb)  # type: ignore[return-value]


def _kit_spec(data: RepoData, kit_id: str) -> dict[str, Any]:
    spec: dict[str, Any] = data.kit_specs["kits"][kit_id]
    return spec


def _generate(
    ctx: KitContext,
    kit_id: str,
    item_id: str,
    item_text: str,
    spec: OutputSpec,
    variables: Mapping[str, Any],
    *,
    safe_margin: float | None = None,
    fit_mode: str = "contain",
) -> TaskOutcome:
    cv = ctx.character
    task_id = f"{cv.character_id}-{cv.version}-{kit_id}-{item_id}"
    req, _ = ctx.compiler.to_request(
        cv,
        kit_id,
        task_id,
        approved=ctx.approved,
        output_spec=spec,
        variables=variables,
        kit_item=item_text,
        references=tuple(cv.reference_manifest) + tuple(ctx.references),
    )
    pixel_art = (cv.style_profile.get("enforce") or {}).get("rendering") == "nearest_neighbor_no_antialias"
    return ctx.runner.run(req, safe_margin=safe_margin, fit_mode=fit_mode, pixel_art=pixel_art)  # type: ignore[arg-type]


def _task_file(ctx: KitContext, outcome: TaskOutcome) -> Path:
    return safe_join(ctx.runner.task_dir(outcome.task_id), outcome.files[0].path)


def _write_manifest(ctx: KitContext, kit_id: str, kit_dir: Path, body: dict[str, Any]) -> KitResult:
    cv = ctx.character
    manifest = {
        "kit_id": kit_id,
        "character_id": cv.character_id,
        "character_version": cv.version,
        "style_id": cv.style_id,
        "provider": ctx.runner.provider.name,
        "is_mock": ctx.is_mock,
        "created_at": utc_now(),
        "note_zh": "通用默认规格；渠道/印厂规范优先。RGB 文件，未声明 CMYK/ICC 合规。"
        if not ctx.is_mock
        else "MOCK 演示产物，不是真实交付。",
        **body,
    }
    path = kit_dir / "kit_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return KitResult(kit_id, path, manifest)


# ---------------------------------------------------------------------------------------- APP-01


def build_emoji_kit(
    ctx: KitContext,
    *,
    count: int | None = None,
    meanings: Sequence[str] | None = None,
    text_map: Mapping[int, str] | None = None,
) -> KitResult:
    data = ctx.compiler.registry.data
    ks = _kit_spec(data, "APP-01")
    count = count or ks["default_count"]
    if count not in ks["allowed_counts"]:
        raise KitError(f"emoji count must be one of {ks['allowed_counts']}")
    zh = list(meanings or ks["meanings_zh"][:count])
    if len(zh) != count:
        raise KitError(f"need exactly {count} meanings, got {len(zh)}")
    en = ks["meanings_en"][:count] if meanings is None else zh
    kit_dir = ctx.out_dir / "APP-01"
    master_dir, small_dir = kit_dir / "png_1024", kit_dir / "png_512"
    spec = OutputSpec(
        width_px=ks["master_px"],
        height_px=ks["master_px"],
        format="PNG",
        alpha_required=True,
        safe_margin_pct=ks["safe_margin_pct"],
    )
    variables = {
        "emoji_count": count,
        "emoji_meanings": "、".join(zh),
        "exact_text_map": "无（如需文字由排版层另行叠加）" if not text_map else "由排版层叠加",
    }
    items, outcomes, sheet_tiles = [], [], []
    for i, meaning in enumerate(zh, start=1):
        oc = _generate(
            ctx,
            "APP-01",
            f"{i:02d}",
            f"第 {i}/{count} 个表情，语义「{meaning}」（{en[i - 1]}），单个角色，透明背景",
            spec,
            variables,
            safe_margin=ks["safe_margin_pct"],
        )
        outcomes.append(oc)
        entry: dict[str, Any] = {"index": i, "meaning_zh": meaning, "status": oc.status.value, "errors": oc.errors}
        if oc.delivered:
            src = _task_file(ctx, oc)
            img = Image.open(src).convert("RGBA")
            if text_map and i in text_map:
                font = ctx.need_font()
                rec = draw_text(
                    img,
                    text_map[i],
                    (80, 840, 944, 990),
                    font=font,
                    color=(34, 34, 34, 255),
                    align="center",
                    max_lines=1,
                )
                entry["text"] = rec.text
            master = master_dir / f"{i:02d}.png"
            save_png(img, master, mock=ctx.is_mock)
            small = small_dir / f"{i:02d}.png"
            save_png(img.resize((512, 512), Image.Resampling.LANCZOS), small, mock=ctx.is_mock)
            checks = check_image_file(master, spec, expect_real=not ctx.is_mock, safe_margin_pct=ks["safe_margin_pct"])
            checks += [
                Check(f"export_512_{c.id}", c.status, c.detail)
                for c in check_image_file(
                    small,
                    OutputSpec(width_px=512, height_px=512, format="PNG", alpha_required=True),
                    expect_real=not ctx.is_mock,
                )
            ]
            qa = finalize(checks, allow_unreviewed_soft=ctx.runner.allow_unreviewed_soft)
            entry.update(
                files={
                    "png_1024": master.relative_to(kit_dir).as_posix(),
                    "png_512": small.relative_to(kit_dir).as_posix(),
                },
                sha256={"png_1024": _sha(master), "png_512": _sha(small)},
                quality_result=qa.to_json(),
            )
            sheet_tiles.append(img)
        items.append(entry)
    delivered = [e for e in items if "files" in e]
    body: dict[str, Any] = {"requested_count": count, "delivered_count": len(delivered), "items": items}
    if sheet_tiles:
        cols = ks["sheet_columns"]
        rows = -(-len(sheet_tiles) // cols)
        sheet = contact_sheet(sheet_tiles, columns=cols, cell=(1024, 1024), size=(cols * 1024, rows * 1024))
        sheet_path = kit_dir / "preview_sheet.png"
        save_png(sheet, sheet_path, mock=ctx.is_mock)
        body["preview_sheet"] = {
            "file": "preview_sheet.png",
            "sha256": _sha(sheet_path),
            "size": list(sheet.size),
            "note_zh": "总览仅供预览，不代替单个文件",
        }
    body["count_exact"] = len(delivered) == count
    body["partial"] = len(delivered) != count
    result = _write_manifest(ctx, "APP-01", kit_dir, body)
    result.outcomes = outcomes
    return result


# --------------------------------------------------------------------------------- print signs


def _sign_layout(
    illustration: Image.Image | None,
    texts: Sequence[tuple[str, float]],
    ps: PrintSpec,
    *,
    font: FontChoice,
    accent: tuple[int, int, int],
    illustration_ratio: float,
    side: str,
) -> tuple[Image.Image, list[TextRecord], tuple[int, int, int, int]]:
    """Compose one print sign: tinted full-bleed background, accent band, text area, illustration area."""
    w, h = ps.canvas_px
    canvas = Image.new("RGB", (w, h), _tint(accent, 0.9))
    draw = ImageDraw.Draw(canvas)
    sx0, sy0, sx1, sy1 = ps.safe_box_px
    gap = ps.mm_to_px(4)
    if side == "right":
        ill_box = (round(sx1 - (sx1 - sx0) * illustration_ratio), sy0, sx1, sy1)
        text_box = (sx0, sy0, ill_box[0] - gap, sy1)
        draw.rectangle((0, 0, ps.mm_to_px(ps.bleed_mm + 3), h), fill=accent)
    else:  # top
        ill_box = (sx0, sy0, sx1, round(sy0 + (sy1 - sy0) * illustration_ratio))
        text_box = (sx0, ill_box[3] + gap, sx1, sy1)
        draw.rectangle((0, h - ps.mm_to_px(ps.bleed_mm + 3), w, h), fill=accent)
    records: list[TextRecord] = []
    tx0, ty0, tx1, ty1 = text_box
    total = sum(f for _, f in texts)
    y = ty0
    for i, (text, frac) in enumerate(texts):
        bh = round((ty1 - ty0) * frac / total)
        color = (34, 34, 34) if i == 0 else (90, 90, 90)
        records.append(
            draw_text(
                canvas,
                text,
                (tx0, y, tx1, y + bh),
                font=font,
                color=color,
                align="left" if side == "right" else "center",
                max_lines=2,
            )
        )
        y += bh
    if illustration is not None:
        ill = illustration.convert("RGBA")
        bw, bh2 = ill_box[2] - ill_box[0], ill_box[3] - ill_box[1]
        ill.thumbnail((bw, bh2), Image.Resampling.LANCZOS)
        canvas.paste(ill, (ill_box[0] + (bw - ill.width) // 2, ill_box[1] + (bh2 - ill.height) // 2), ill)
    return canvas, records, ill_box


def _inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _build_signs(
    ctx: KitContext,
    kit_id: str,
    items: Sequence[Mapping[str, Any]],
    texts_for: Any,
    ps: PrintSpec,
    *,
    illustration_ratio: float,
    side: str,
    variables: Mapping[str, Any],
) -> KitResult:
    font = ctx.need_font()
    kit_dir = ctx.out_dir / kit_id
    sx0, sy0, sx1, sy1 = ps.safe_box_px
    entries, outcomes, previews = [], [], []
    for it in items:
        texts = texts_for(it)
        if side == "right":
            ill_w, ill_h = round((sx1 - sx0) * illustration_ratio), sy1 - sy0
        else:
            ill_w, ill_h = sx1 - sx0, round((sy1 - sy0) * illustration_ratio)
        ill_spec = OutputSpec(width_px=ill_w, height_px=ill_h, format="PNG", alpha_required=True, safe_margin_pct=0.03)
        oc = _generate(
            ctx,
            kit_id,
            it["item_id"],
            f"{texts[0][0]}：{it.get('pose_en', '')}；只画角色插画，不画文字",
            ill_spec,
            variables,
            safe_margin=0.03,
        )
        outcomes.append(oc)
        entry: dict[str, Any] = {
            "item_id": it["item_id"],
            "text": [t for t, _ in texts],
            "status": oc.status.value,
            "errors": oc.errors,
        }
        if oc.delivered:
            ill = Image.open(_task_file(ctx, oc))
            accent = _hex(it.get("accent", "#2F6FB3"))
            canvas, records, ill_box = _sign_layout(
                ill, texts, ps, font=font, accent=accent, illustration_ratio=illustration_ratio, side=side
            )
            png = kit_dir / f"{it['item_id']}.png"
            pdf = kit_dir / f"{it['item_id']}.pdf"
            save_png(canvas, png, mock=ctx.is_mock)
            write_print_pdf(canvas, ps, pdf, title=f"{kit_id} {it['item_id']}")
            w, h = ps.canvas_px
            checks = check_image_file(
                png,
                OutputSpec(width_px=w, height_px=h, format="PNG", alpha_required=False),
                expect_real=not ctx.is_mock,
            )
            checks += check_print_pdf(pdf, ps)
            checks.append(check_text(records, [t for t, _ in texts]))
            safe_ok = all(_inside(r.box, ps.safe_box_px) for r in records) and _inside(ill_box, ps.safe_box_px)
            checks.append(
                Check(
                    "safe_margin", "pass" if safe_ok else "fail", f"text+illustration inside safe box {ps.safe_box_px}"
                )
            )
            qa = finalize(checks, allow_unreviewed_soft=ctx.runner.allow_unreviewed_soft)
            entry.update(
                files={"png": png.name, "pdf": pdf.name},
                sha256={"png": _sha(png), "pdf": _sha(pdf)},
                print={
                    "trim_mm": list(ps.trim_mm),
                    "bleed_mm": ps.bleed_mm,
                    "ppi": ps.ppi,
                    "safe_mm": ps.safe_mm,
                    "canvas_px": list(ps.canvas_px),
                },
                text_layout=[{"text": r.text, "font_size_px": r.font_size, "box": list(r.box)} for r in records],
                quality_result=qa.to_json(),
            )
            previews.append(canvas)
        entries.append(entry)
    delivered = [e for e in entries if "files" in e]
    body: dict[str, Any] = {
        "requested_count": len(items),
        "delivered_count": len(delivered),
        "items": entries,
        "font": {"family": font.family, "license_note": font.license_note},
        "count_exact": len(delivered) == len(items),
        "partial": len(delivered) != len(items),
    }
    if previews:
        cw, ch = previews[0].width // 2, previews[0].height // 2
        cols = 2 if len(previews) > 1 else 1
        sheet = contact_sheet(previews, columns=cols, cell=(cw, ch), gap=24)
        save_png(sheet, kit_dir / "preview_sheet.png", mock=ctx.is_mock)
        body["preview_sheet"] = {"file": "preview_sheet.png", "sha256": _sha(kit_dir / "preview_sheet.png")}
    result = _write_manifest(ctx, kit_id, kit_dir, body)
    result.outcomes = outcomes
    return result


def build_door_sign_kit(
    ctx: KitContext, *, room_name: str | None = None, states: Sequence[Mapping[str, Any]] | None = None
) -> KitResult:
    ks = _kit_spec(ctx.compiler.registry.data, "APP-02")
    room = room_name or ks["default_room_name"]
    items = list(states or ks["states"])
    if len(items) < 4 and states is None:
        raise KitError("door sign kit needs at least 4 states")
    ps = PrintSpec(tuple(ks["trim_mm"]), ks["bleed_mm"], ks["ppi"], ks["safe_mm"])  # type: ignore[arg-type]
    variables = {"room_name": room, "sign_states": "、".join(s["text_zh"] for s in items)}
    return _build_signs(
        ctx,
        "APP-02",
        [{**s, "item_id": s["state_id"]} for s in items],
        lambda it: [(it["text_zh"], 0.62), (room, 0.38)],
        ps,
        illustration_ratio=ks["illustration_ratio"],
        side=ks["illustration_side"],
        variables=variables,
    )


# ---------------------------------------------------------------------------- generic APP-03..10


def _screen_items(
    ctx: KitContext,
    kit_id: str,
    items: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Any],
    *,
    headline: str | None = None,
) -> KitResult:
    kit_dir = ctx.out_dir / kit_id
    entries, outcomes = [], []
    for it in items:
        spec = OutputSpec(
            width_px=it["width_px"], height_px=it["height_px"], format="PNG", alpha_required=bool(it.get("alpha"))
        )
        oc = _generate(
            ctx,
            kit_id,
            it["item_id"],
            it.get("pose_en", it["item_id"]),
            spec,
            variables,
            fit_mode="cover" if not it.get("alpha") else "contain",
        )
        outcomes.append(oc)
        entry: dict[str, Any] = {"item_id": it["item_id"], "status": oc.status.value, "errors": oc.errors}
        if oc.delivered:
            img = Image.open(_task_file(ctx, oc)).convert("RGBA" if it.get("alpha") else "RGB")
            text = it.get("text_zh")
            records: list[TextRecord] = []
            if text == "{{headline}}":
                text = headline
            if text:
                font = ctx.need_font()
                w, h = img.size
                box = (round(w * 0.06), round(h * 0.04), round(w * 0.94), round(h * 0.18))
                records.append(draw_text(img, text, box, font=font, color=(34, 34, 34), align="center", max_lines=1))
            out = kit_dir / f"{it['item_id']}.png"
            save_png(img, out, mock=ctx.is_mock)
            checks = check_image_file(out, spec, expect_real=not ctx.is_mock)
            if text:
                checks.append(check_text(records, [text]))
            qa = finalize(checks, allow_unreviewed_soft=ctx.runner.allow_unreviewed_soft)
            entry.update(
                files={"png": out.name},
                sha256={"png": _sha(out)},
                size=[spec.width_px, spec.height_px],
                quality_result=qa.to_json(),
            )
        entries.append(entry)
    delivered = [e for e in entries if "files" in e]
    body = {
        "requested_count": len(items),
        "delivered_count": len(delivered),
        "items": entries,
        "count_exact": len(delivered) == len(items),
        "partial": len(delivered) != len(items),
    }
    result = _write_manifest(ctx, kit_id, kit_dir, body)
    result.outcomes = outcomes
    return result


def build_sticker_kit(ctx: KitContext, *, count: int | None = None) -> KitResult:
    ks = _kit_spec(ctx.compiler.registry.data, "APP-08")
    n = count or ks["default_count"]
    poses = (ks["poses_en"] * 4)[:n]
    ps = PrintSpec(tuple(ks["trim_mm"]), ks["bleed_mm"], ks["ppi"], 2.0)  # type: ignore[arg-type]
    kit_dir = ctx.out_dir / "APP-08"
    master_spec = OutputSpec(
        width_px=ks["master_px"], height_px=ks["master_px"], format="PNG", alpha_required=True, safe_margin_pct=0.06
    )
    variables = {"sticker_variants": n, "print_size_mm": f"{ks['trim_mm'][0]}×{ks['trim_mm'][1]}"}
    entries, outcomes = [], []
    for i, pose in enumerate(poses, start=1):
        oc = _generate(
            ctx, "APP-08", f"{i:02d}", f"贴纸 {i}/{n}：{pose}，外轮廓留白", master_spec, variables, safe_margin=0.06
        )
        outcomes.append(oc)
        entry: dict[str, Any] = {"index": i, "pose_en": pose, "status": oc.status.value, "errors": oc.errors}
        if oc.delivered:
            img = Image.open(_task_file(ctx, oc)).convert("RGBA")
            master = kit_dir / f"sticker_{i:02d}.png"
            save_png(img, master, mock=ctx.is_mock)
            w, h = ps.canvas_px
            sheet = Image.new("RGB", (w, h), (255, 255, 255))
            art = img.copy()
            sx0, sy0, sx1, sy1 = ps.safe_box_px
            art.thumbnail((sx1 - sx0, sy1 - sy0), Image.Resampling.LANCZOS)
            sheet.paste(art, (sx0 + (sx1 - sx0 - art.width) // 2, sy0 + (sy1 - sy0 - art.height) // 2), art)
            pdf = kit_dir / f"sticker_{i:02d}.pdf"
            write_print_pdf(sheet, ps, pdf, title=f"APP-08 sticker {i}")
            checks = check_image_file(
                master, master_spec, expect_real=not ctx.is_mock, safe_margin_pct=0.06
            ) + check_print_pdf(pdf, ps)
            qa = finalize(checks, allow_unreviewed_soft=ctx.runner.allow_unreviewed_soft)
            entry.update(
                files={"png_master": master.name, "pdf": pdf.name},
                sha256={"png_master": _sha(master), "pdf": _sha(pdf)},
                cut_line_note_zh=f"建议沿角色外轮廓外扩 {ks['cut_offset_mm']} mm 制作刀模（刀模路径需印厂确认）",
                quality_result=qa.to_json(),
            )
        entries.append(entry)
    delivered = [e for e in entries if "files" in e]
    body = {
        "requested_count": n,
        "delivered_count": len(delivered),
        "items": entries,
        "count_exact": len(delivered) == n,
        "partial": len(delivered) != n,
    }
    result = _write_manifest(ctx, "APP-08", kit_dir, body)
    result.outcomes = outcomes
    return result


def build_application_kit(ctx: KitContext, kit_id: str, variables: Mapping[str, Any] | None = None) -> KitResult:
    """SPEC §9.2 dispatcher for APP-01..APP-10."""
    v = dict(variables or {})
    data = ctx.compiler.registry.data
    if kit_id == "APP-01":
        return build_emoji_kit(ctx, count=v.get("count"), meanings=v.get("meanings"), text_map=v.get("text_map"))
    if kit_id == "APP-02":
        return build_door_sign_kit(ctx, room_name=v.get("room_name"), states=v.get("states"))
    if kit_id in ("APP-03", "APP-09"):
        ks = _kit_spec(data, kit_id)
        ps = PrintSpec(tuple(ks["trim_mm"]), ks["bleed_mm"], ks["ppi"], ks["safe_mm"])  # type: ignore[arg-type]
        items = v.get("items") or ks["items"]
        if kit_id == "APP-03":
            pv = {
                "sign_locations": "、".join(i["text_zh"] for i in items),
                "physical_size_mm": f"{ks['trim_mm'][0]}×{ks['trim_mm'][1]}",
            }
        else:
            pv = {"notice_texts": "、".join(i["text_zh"] for i in items)}
        return _build_signs(
            ctx,
            kit_id,
            items,
            lambda it: [(it["text_zh"], 1.0)],
            ps,
            illustration_ratio=ks["illustration_ratio"],
            side=ks["illustration_side"],
            variables=pv,
        )
    if kit_id == "APP-08":
        return build_sticker_kit(ctx, count=v.get("count"))
    if kit_id in ("APP-04", "APP-06", "APP-07", "APP-10"):
        ks = _kit_spec(data, kit_id)
        items = [dict(i, pose_en=i.get("pose_en", ks.get("pose_en", ""))) for i in ks["items"]]
        pv: dict[str, Any] = {}
        if kit_id == "APP-06":
            for key in ("holiday", "headline"):
                if not v.get(key):
                    raise KitError(f"APP-06 needs variable {key!r}")
            pv = {"holiday": v["holiday"], "headline": v["headline"], "subtext": v.get("subtext", "（由排版层添加）")}
            items = [dict(i, text_zh="{{headline}}") for i in items]
        if kit_id == "APP-10":
            if not v.get("ip_profile"):
                raise KitError("APP-10 needs the approved 'ip_profile' text (no invented persona)")
            pv = {"ip_profile": v["ip_profile"]}
        return _screen_items(ctx, kit_id, items, pv, headline=v.get("headline"))
    if kit_id == "APP-05":
        ks = _kit_spec(data, kit_id)
        items = [
            dict(i, width_px=ks["sticker_px"], height_px=ks["sticker_px"], alpha=True, text_zh=None)
            for i in ks["items"]
        ]
        return _screen_items(ctx, kit_id, items, {})
    raise KitError(f"unknown kit {kit_id!r}")


def export_kit(result: KitResult, destination: Path) -> dict[str, Any]:
    """SPEC §9.2 ``export_batch``: zip the kit folder and return an export manifest with hashes."""
    import zipfile

    kit_dir = result.manifest_path.parent
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in kit_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(kit_dir).as_posix())
    return {
        "kit_id": result.kit_id,
        "archive": str(destination),
        "archive_sha256": _sha(destination),
        "files": {p.relative_to(kit_dir).as_posix(): _sha(p) for p in files},
    }


_ = (WARM_WHITE, fit_to_spec)  # re-exported helpers kept for kit authors
