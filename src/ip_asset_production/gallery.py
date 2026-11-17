"""Offline, searchable HTML style gallery (SPEC §4A.5 fallback; T21, T25, T29).

* Only ``approved`` previews with real, non-mock files are shown as images; every other style is
  rendered as a text card with an explicit "样例未生成/未审核" badge (never a placeholder image).
* Images are copied next to ``index.html`` so the folder works offline and can be zipped.
* No external scripts, fonts or network requests.
"""

from __future__ import annotations

import html
import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .paths import safe_join
from .styles import SUBJECT_KEY, StyleLibrary

SUBJECT_LABEL = {
    "anime_human": "人物",
    "animal": "动物",
    "anthropomorphic_object": "拟人物体",
    "fantasy_creature": "幻想",
}

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IP 风格画廊</title>
<style>
:root{{--bg:#faf7f2;--fg:#222;--muted:#6b6b6b;--card:#fff;--line:#e4ded4;--accent:#2f6fb3}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16161a;--fg:#eee;--muted:#a0a0a8;--card:#202026;--line:#33333b;--accent:#7fb0ff}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
header{{padding:16px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:2}}
h1{{font-size:20px;margin:0 0 8px}}.bar{{display:flex;flex-wrap:wrap;gap:8px}}
input,select{{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}}
input[type=search]{{flex:1 1 220px}}main{{padding:16px;display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}}
.card img{{width:100%;aspect-ratio:1;object-fit:cover;background:#eee}}
.missing{{aspect-ratio:1;display:flex;align-items:center;justify-content:center;text-align:center;padding:16px;color:var(--muted);border-bottom:1px dashed var(--line)}}
.body{{padding:10px 12px;display:flex;flex-direction:column;gap:4px;flex:1}}.id{{font-family:ui-monospace,monospace;color:var(--muted);font-size:12px}}
.badge{{display:inline-block;font-size:12px;padding:1px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}}
.ok{{color:#1d7a3e;border-color:#1d7a3e}}button{{margin-top:auto;font:inherit;padding:6px;border-radius:6px;border:1px solid var(--accent);background:none;color:var(--accent);cursor:pointer}}
.count{{color:var(--muted);font-size:13px;margin-top:6px}}
</style></head><body>
<header><h1>IP 风格画廊 <span class="badge">{shown} / {total} 个风格有已审核样例</span></h1>
<div class="bar"><input type="search" id="q" placeholder="搜索名称、描述、材质、STYLE-编号">
<select id="group"><option value="">全部家族</option>{group_options}</select>
<select id="subject"><option value="">全部主体</option>{subject_options}</select>
<select id="avail"><option value="">全部</option><option value="approved">只看有样例</option></select></div>
<div class="count" id="count"></div></header>
<main id="grid">{cards}</main>
<script>
const q=document.getElementById('q'),g=document.getElementById('group'),s=document.getElementById('subject'),a=document.getElementById('avail');
function apply(){{let n=0;for(const c of document.querySelectorAll('.card')){{
const t=c.dataset.search,ok=(!q.value||t.includes(q.value.toLowerCase()))&&(!g.value||c.dataset.group===g.value)
&&(!s.value||c.dataset.subjects.split(' ').includes(s.value))&&(!a.value||c.dataset.status===a.value);
c.hidden=!ok;if(ok)n++;}}document.getElementById('count').textContent='显示 '+n+' 个风格';}}
for(const el of [q,g,s,a])el.addEventListener('input',apply);apply();
for(const b of document.querySelectorAll('button[data-style]'))b.addEventListener('click',()=>{{
const v='选择风格 '+b.dataset.style;navigator.clipboard&&navigator.clipboard.writeText(v);b.textContent='已复制：'+v;}});
</script></body></html>
"""


@dataclass(frozen=True)
class GalleryResult:
    index_html: Path
    styles_total: int
    styles_with_preview: int
    images_copied: int


def build_gallery(
    out_dir: Path,
    styles: StyleLibrary | None = None,
    *,
    ip_type: str | None = None,
    style_ids: Iterable[str] | None = None,
) -> GalleryResult:
    """Write ``out_dir/index.html`` (+ ``out_dir/img/``). Filter by ip_type or explicit ids."""
    lib = styles or StyleLibrary()
    out_dir = Path(out_dir)
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    if style_ids is not None:
        selected = [lib.resolve(s) for s in style_ids]
    elif ip_type is not None:
        selected = lib.candidates(ip_type)
    else:
        selected = list(lib.styles.values())
    subject = SUBJECT_KEY.get(ip_type) if ip_type else None

    cards, copied, shown = [], 0, 0
    for s in sorted(selected, key=lambda x: x["style_id"]):
        previews = lib.approved_previews(s["style_id"], subject)
        group = lib.groups[s["group_id"]]["name_zh"]
        subjects = " ".join(s["supported_subjects"])
        search = " ".join(
            [s["style_id"], s["display_name_zh"], s["description_zh"], s["material"], s["medium"], *s["mood"], group]
        ).lower()
        if previews:
            shown += 1
            p = previews[0]
            src = safe_join(lib.data.root, str(p["actual_file"]))
            name = f"{p['preview_id']}.png"
            shutil.copyfile(src, img_dir / name)
            copied += 1
            visual = (
                f'<img loading="lazy" src="img/{html.escape(name)}" '
                f'alt="{html.escape(s["display_name_zh"])} 风格样例（{html.escape(p["prototype_id"])}）">'
            )
            badge = (
                f'<span class="badge ok">已审核样例 · {html.escape(p.get("model") or p.get("provider") or "")}</span>'
            )
            status = "approved"
        else:
            visual = '<div class="missing">样例未生成 / 未审核<br>仅提供文字说明</div>'
            badge = '<span class="badge">无可展示样例</span>'
            status = "missing"
        cards.append(
            f'<article class="card" data-group="{s["group_id"]}" data-subjects="{html.escape(subjects)}" '
            f'data-status="{status}" data-search="{html.escape(search)}">{visual}<div class="body">'
            f'<div class="id">{s["style_id"]} · {html.escape(group)}</div>'
            f"<strong>{html.escape(s['display_name_zh'])}</strong>"
            f"<div>{html.escape(s['description_zh'])}</div>{badge}"
            f'<button data-style="{s["style_id"]}">选择 {s["style_id"]}</button></div></article>'
        )
    groups = sorted({s["group_id"] for s in selected})
    page = PAGE.format(
        shown=shown,
        total=len(selected),
        group_options="".join(
            f'<option value="{g}">{g} {html.escape(lib.groups[g]["name_zh"])}</option>' for g in groups
        ),
        subject_options="".join(f'<option value="{k}">{v}</option>' for k, v in SUBJECT_LABEL.items()),
        cards="\n".join(cards),
    )
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    (out_dir / "gallery.json").write_text(
        json.dumps({"styles_total": len(selected), "styles_with_preview": shown}, ensure_ascii=False), encoding="utf-8"
    )
    return GalleryResult(index, len(selected), shown, copied)
