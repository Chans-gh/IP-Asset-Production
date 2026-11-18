#!/usr/bin/env python3
"""Build the GitHub Pages case gallery (ADR-019).

Copies *generated* assets of each real case from the gitignored ``workspace/`` into
``site/cases/<case>/`` (web-sized: JPEG for opaque images, PNG for transparent ones), writes
``case.json`` (the secret scan only accepts case images listed there) and renders ``site/index.html``.
Source photos and anything under ``source/`` are never copied.

    python scripts/build_site.py            # rebuild from workspace/
    python scripts/build_site.py --html     # re-render index.html from existing case.json files
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT / "workspace"
SITE = ROOT / "site"
MAX_EDGE = 1600

# (group title, note, [(source path relative to workspace/<case>, caption)])
CASES: dict[str, dict] = {
    "linxi": {
        "title": "林汐 · 写实数字人",
        "summary": "由一张真人照片（需求方授权）转成独立的写实数字人形象，定妆后所有资产都以定妆图为唯一身份基准。"
        "多个子图的一组整组一次生成为无缝网格设定图，再由程序切分；海报、横幅、介绍页的文字由模型连同画面一起排版。",
        "groups": [
            (
                "定妆",
                "3 个候选中选定 c1，作为之后全部资产的身份基准。",
                [
                    ("tasks/linxi-v1-canonical-c1/linxi-v1-canonical-c1.png", "定妆图 c1"),
                ],
            ),
            (
                "基础设定图",
                "每组 1 次调用，无缝网格；带标注版由程序加标题和每格编号名称，供视频/生图参考和知识库使用。",
                [
                    ("tasks/linxi-v1-grid-views/linxi-v1-grid-views_labeled.png", "视角设定图（标注版）"),
                    ("tasks/linxi-v1-grid-expressions/linxi-v1-grid-expressions_labeled.png", "表情设定图（标注版）"),
                    ("tasks/linxi-v1-grid-poses/linxi-v1-grid-poses_labeled.png", "动作设定图（标注版）"),
                    ("tasks/linxi-v1-grid-views/linxi-v1-grid-views.png", "视角设定图（干净版）"),
                    ("tasks/linxi-v1-grid-expressions/linxi-v1-grid-expressions.png", "表情设定图（干净版）"),
                    ("tasks/linxi-v1-grid-poses/linxi-v1-grid-poses.png", "动作设定图（干净版）"),
                ],
            ),
            (
                "表情包 APP-01",
                "16 个大头贴式胸像，2 次调用（每张 8 格），程序切成独立透明贴纸。",
                [
                    (f"kits/APP-01/png_512/{i:02d}.png", m)
                    for i, m in enumerate(
                        [
                            "你好",
                            "谢谢",
                            "好的",
                            "加油",
                            "开心",
                            "爱你",
                            "哈哈",
                            "惊讶",
                            "思考中",
                            "难过",
                            "生气",
                            "晚安",
                            "辛苦了",
                            "收到",
                            "抱歉",
                            "再见",
                        ],
                        start=1,
                    )
                ],
            ),
            (
                "直播贴片 APP-05",
                "5 个状态 1 次调用，一张透明网格图切分。",
                [
                    (f"kits/APP-05/{k}.png", c)
                    for k, c in [
                        ("welcome", "欢迎"),
                        ("like", "点赞"),
                        ("follow", "关注"),
                        ("notice", "提示"),
                        ("ending", "结束"),
                    ]
                ],
            ),
            (
                "社交账号包 APP-04",
                "整幅成品各自生成；标题由模型直接设计在画面里。",
                [
                    ("kits/APP-04/avatar.png", "头像 1:1"),
                    ("kits/APP-04/banner.png", "横幅 16:9"),
                    ("kits/APP-04/vertical_cover.png", "竖版封面 9:16"),
                ],
            ),
            (
                "节日海报 APP-06",
                "新年主题三个尺寸，标题和副标题由模型排版。",
                [
                    ("kits/APP-06/square.png", "方形 1:1"),
                    ("kits/APP-06/portrait_4x5.png", "竖版 4:5"),
                    ("kits/APP-06/story_9x16.png", "快拍 9:16"),
                ],
            ),
            (
                "角色介绍页 APP-10",
                "角色名和介绍文字来自已批准的档案，由模型排成介绍页。",
                [
                    ("kits/APP-10/intro_1080p.png", "介绍页 1920×1080"),
                    ("kits/APP-10/intro_1440p.png", "介绍页 2560×1440"),
                ],
            ),
            (
                "壁纸 APP-07",
                "桌面与手机两种构图。",
                [
                    ("kits/APP-07/desktop.png", "桌面 3840×2160"),
                    ("kits/APP-07/mobile.png", "手机 2160×3840"),
                ],
            ),
        ],
    },
    "mituan": {
        "title": "米团 · 卡通吉祥物",
        "summary": "从文字描述设计的原创卡通吉祥物，定妆后做会议室门牌包；门牌文字需要逐字精确，由排版程序设置。",
        "groups": [
            ("定妆", "", [("tasks/mituan-v1-canonical/mituan-v1-canonical.png", "定妆图")]),
            (
                "会议室门牌 APP-02",
                "300×120 mm 印刷门牌，四个状态。",
                [
                    (f"kits/APP-02/{k}.png", c)
                    for k, c in [
                        ("in_meeting", "会议中"),
                        ("available", "空闲"),
                        ("do_not_disturb", "请勿打扰"),
                        ("welcome", "欢迎使用"),
                    ]
                ],
            ),
        ],
    },
}


def _export(src: Path, dst_stem: Path) -> tuple[str, list[int]]:
    im = Image.open(src)
    alpha = im.mode in ("RGBA", "LA") and im.getchannel("A").getextrema()[0] < 255
    im = im.convert("RGBA" if alpha else "RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    if alpha:
        out = dst_stem.with_suffix(".png")
        im.save(out, optimize=True)
    else:
        out = dst_stem.with_suffix(".jpg")
        im.save(out, quality=84, optimize=True, progressive=True)
    return out.name, [im.width, im.height]


def build_cases() -> None:
    for cid, case in CASES.items():
        out_dir = SITE / "cases" / cid
        for old in out_dir.glob("*"):
            if old.suffix in (".png", ".jpg"):
                old.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)
        groups = []
        for gi, (title, note, items) in enumerate(case["groups"], start=1):
            assets = []
            for ai, (rel, caption) in enumerate(items, start=1):
                if "source" in Path(rel).parts:
                    raise SystemExit(f"refusing to publish a source file: {rel}")
                src = WS / cid / rel
                if not src.is_file():
                    print(f"skip (missing): {cid}/{rel}")
                    continue
                name, size = _export(src, out_dir / f"g{gi:02d}-{ai:02d}")
                assets.append({"file": name, "caption": caption, "size": size})
            groups.append({"title": title, "note": note, "assets": assets})
        data = {"case_id": cid, "title": case["title"], "summary": case["summary"], "groups": groups}
        (out_dir / "case.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


PAGE_HEAD = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IP 资产生产案例</title>
<meta name="description" content="IP Asset Production Skill 的真实生成案例：数字人与卡通 IP 的定妆、设定图和应用成品包。">
<style>
:root{--bg:#f7f5f1;--card:#fff;--ink:#1f1f1f;--muted:#6b6660;--line:#e6e1d9;--accent:#b4472f;--chip:#efeae2}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161514;--card:#1f1e1c;--ink:#ece8e1;--muted:#a19a90;--line:#33302c;--accent:#e0876f;--chip:#2a2825}}
:root[data-theme="dark"]{--bg:#161514;--card:#1f1e1c;--ink:#ece8e1;--muted:#a19a90;--line:#33302c;--accent:#e0876f;--chip:#2a2825}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 -apple-system,"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:0 16px}
header{padding:56px 0 24px}
h1{font-size:clamp(28px,5vw,44px);line-height:1.2;margin:0 0 12px;letter-spacing:.02em}
.lead{color:var(--muted);max-width:760px;margin:0}
nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px}
nav a{background:var(--chip);color:var(--ink);text-decoration:none;padding:6px 14px;border-radius:999px;font-size:14px}
section.case{border-top:1px solid var(--line);padding:40px 0 8px}
h2{font-size:clamp(22px,3.4vw,30px);margin:0 0 8px}
.case > p{color:var(--muted);max-width:820px;margin:0 0 24px}
h3{font-size:18px;margin:32px 0 4px}
.note{color:var(--muted);font-size:14px;margin:0 0 14px}
.grid{display:grid;gap:12px;align-items:start;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
.grid.wide{grid-template-columns:repeat(auto-fill,minmax(360px,1fr))}
.grid.small{grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}
figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
figure a{display:block}
figure img{display:block;width:100%;height:auto}
figure.alpha img{background:repeating-conic-gradient(var(--chip) 0 25%,transparent 0 50%) 0 0/16px 16px}
figcaption{font-size:13px;color:var(--muted);padding:8px 10px}
footer{border-top:1px solid var(--line);margin-top:48px;padding:24px 0 48px;color:var(--muted);font-size:13px}
@media (max-width:480px){.grid.wide{grid-template-columns:1fr}}
</style>
</head>
<body>
"""


def _grid_class(assets: list[dict]) -> str:
    if len(assets) >= 8:
        return "grid small"
    if any(a["size"][0] > a["size"][1] * 1.2 for a in assets):
        return "grid wide"
    return "grid"


def render_html() -> None:
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((SITE / "cases").glob("*/case.json"))]
    order = list(CASES)
    cases.sort(key=lambda c: order.index(c["case_id"]) if c["case_id"] in order else 99)
    e = html.escape
    out = [PAGE_HEAD, '<div class="wrap"><header><h1>IP 资产生产案例</h1>']
    out.append(
        '<p class="lead">IP Asset Production Skill 的真实生成案例。每张图都来自实际的生图调用和程序后处理，'
        "没有手工修图。点击图片看大图。</p><nav>"
    )
    out += [f'<a href="#{e(c["case_id"])}">{e(c["title"])}</a>' for c in cases]
    out.append("</nav></header>")
    for c in cases:
        out.append(f'<section class="case" id="{e(c["case_id"])}"><h2>{e(c["title"])}</h2><p>{e(c["summary"])}</p>')
        for g in c["groups"]:
            if not g["assets"]:
                continue
            out.append(f"<h3>{e(g['title'])}</h3>")
            if g["note"]:
                out.append(f'<p class="note">{e(g["note"])}</p>')
            out.append(f'<div class="{_grid_class(g["assets"])}">')
            for a in g["assets"]:
                src = f"cases/{e(c['case_id'])}/{e(a['file'])}"
                w, h = a["size"]
                cls = ' class="alpha"' if a["file"].endswith(".png") else ""
                out.append(
                    f'<figure{cls}><a href="{src}" target="_blank" rel="noopener">'
                    f'<img src="{src}" width="{w}" height="{h}" loading="lazy" alt="{e(a["caption"])}"></a>'
                    f"<figcaption>{e(a['caption'])}</figcaption></figure>"
                )
            out.append("</div>")
        out.append("</section>")
    out.append(
        "<footer>图片为网页尺寸的压缩版。案例中的角色由需求方授权生成；原始参考照片不公开。</footer></div></body></html>\n"
    )
    (SITE / "index.html").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", action="store_true", help="only re-render index.html")
    args = ap.parse_args()
    if not args.html:
        build_cases()
    render_html()
    print("site built:", SITE / "index.html")
