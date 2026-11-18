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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700&family=Noto+Sans+SC:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#f4f1ec;--paper:#fbfaf7;--ink:#1b1a18;--soft:#55514b;--muted:#8a847b;--line:#dcd6cc;--accent:#9c3d26;--tile:#ebe6de}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121110;--paper:#1a1917;--ink:#efebe4;--soft:#bdb6ab;--muted:#8a847b;--line:#2e2b27;--accent:#e08a6c;--tile:#23211e}}
:root[data-theme="dark"]{--bg:#121110;--paper:#1a1917;--ink:#efebe4;--soft:#bdb6ab;--muted:#8a847b;--line:#2e2b27;--accent:#e08a6c;--tile:#23211e}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:400 16px/1.75 "Noto Sans SC",-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
.serif{font-family:"Noto Serif SC","Songti SC",serif;font-weight:700}
.wrap{max-width:1240px;margin:0 auto;padding:0 24px}
a{color:inherit}
/* top bar */
.bar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.bar .wrap{display:flex;align-items:center;justify-content:space-between;height:56px;gap:16px}
.brand{font-size:15px;letter-spacing:.08em;text-decoration:none}
.bar nav{display:flex;gap:22px;font-size:14px;overflow-x:auto;white-space:nowrap}
.bar nav a{text-decoration:none;color:var(--soft)}
.bar nav a:hover{color:var(--accent)}
/* hero */
.hero{padding:88px 0 56px}
.eyebrow{font-size:13px;letter-spacing:.24em;color:var(--accent);margin:0 0 18px}
.hero h1{font-size:clamp(36px,6.4vw,76px);line-height:1.12;margin:0;letter-spacing:.01em;max-width:14em}
.hero p{color:var(--soft);font-size:clamp(16px,1.6vw,18px);max-width:40em;margin:28px 0 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:24px;margin-top:56px}
.card{display:grid;grid-template-columns:150px 1fr;gap:20px;align-items:end;text-decoration:none;background:var(--paper);border:1px solid var(--line);padding:16px;transition:border-color .2s}
.card:hover{border-color:var(--accent)}
.card img{width:150px;height:200px;object-fit:cover;display:block;background:var(--tile)}
.card small{color:var(--muted);font-size:12px;letter-spacing:.16em}
.card h2{font-size:24px;margin:6px 0 8px;line-height:1.3}
.card p{margin:0;color:var(--soft);font-size:14px}
/* case */
.case{border-top:1px solid var(--ink);padding:72px 0 24px}
.intro{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:56px;align-items:start}
.intro figure{margin:0;position:sticky;top:80px}
.intro img{width:100%;height:auto;display:block;background:var(--tile)}
.intro figcaption{font-size:12px;color:var(--muted);margin-top:10px;letter-spacing:.06em}
.case-no{font-size:13px;letter-spacing:.24em;color:var(--accent);margin:0}
.intro h2{font-size:clamp(32px,4.4vw,56px);line-height:1.15;margin:14px 0 24px}
.intro .sum{color:var(--soft);margin:0 0 32px;max-width:36em}
.stats{display:flex;gap:40px;border-top:1px solid var(--line);padding-top:20px;margin-bottom:36px}
.stats b{display:block;font:700 34px/1 "Noto Serif SC",serif}
.stats span{font-size:12px;color:var(--muted);letter-spacing:.1em}
.toc{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.toc li{border-bottom:1px solid var(--line)}
.toc a{display:flex;justify-content:space-between;gap:16px;padding:12px 0;text-decoration:none;font-size:15px}
.toc a:hover{color:var(--accent)}
.toc em{font-style:normal;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
/* group */
.group{padding:80px 0 0}
.ghead{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:56px;align-items:end;margin-bottom:28px}
.ghead h3{font-size:clamp(24px,2.8vw,34px);margin:0;line-height:1.25}
.ghead h3 span{display:block;font:500 13px/1 "Noto Sans SC",sans-serif;color:var(--accent);letter-spacing:.2em;margin-bottom:12px}
.ghead p{margin:0;color:var(--soft);font-size:15px;max-width:36em}
.tools{display:flex;gap:0;margin-top:14px;border:1px solid var(--line);width:max-content}
.tools button{font:inherit;font-size:13px;padding:6px 14px;border:0;background:transparent;color:var(--soft);cursor:pointer}
.tools button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
.g{display:grid;gap:16px;align-items:start}
.g figure{margin:0}
.g button.zoom{all:unset;display:block;cursor:zoom-in;width:100%}
.g img{display:block;width:100%;height:auto;background:var(--tile)}
.g .alpha img{background:var(--tile)}
.g figcaption{font-size:13px;color:var(--muted);padding-top:8px}
.g-feature{grid-template-columns:minmax(0,1fr)}
.g-sheet{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.g-sheet figure:first-child{grid-column:1/-1}
.g-sheet .clean{display:none}
.g-sheet.show-clean .clean{display:block}.g-sheet.show-clean .labeled{display:none}
.g-stickers{grid-template-columns:repeat(8,minmax(0,1fr));gap:8px;background:var(--paper);border:1px solid var(--line);padding:16px}
.g-stickers figcaption{text-align:center;font-size:12px}
.g-mosaic{display:flex;flex-direction:column;gap:16px}
.g-mosaic .row{display:flex;gap:16px;align-items:flex-start}
.g-mosaic figure{min-width:0}
footer{border-top:1px solid var(--line);margin-top:120px;padding:28px 0 56px;color:var(--muted);font-size:13px}
/* lightbox */
dialog{border:0;padding:0;background:transparent;max-width:100vw;max-height:100vh;width:100vw;height:100vh}
dialog::backdrop{background:rgba(10,9,8,.92)}
dialog .lb{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px 64px 24px}
dialog img{max-width:100%;max-height:calc(100vh - 120px);object-fit:contain}
dialog p{color:#cfc9bf;font-size:14px;margin:14px 0 0}
dialog .x,dialog .nav{position:absolute;background:none;border:0;color:#eee;font-size:28px;cursor:pointer;padding:12px}
dialog .x{top:8px;right:12px}dialog .prev{left:8px;top:50%}dialog .next{right:8px;top:50%}
@media (max-width:900px){
 .intro,.ghead{grid-template-columns:1fr;gap:24px}
 .intro figure{position:static;max-width:420px}
 .g-stickers{grid-template-columns:repeat(4,minmax(0,1fr))}
}
@media (max-width:560px){
 .wrap{padding:0 16px}
 .hero{padding:56px 0 40px}
 .bar nav{display:none}
 .card{grid-template-columns:96px 1fr}.card img{width:96px;height:128px}
 .g-sheet{grid-template-columns:1fr}
 .g-mosaic .row{flex-wrap:wrap}.g-mosaic .row figure{flex-basis:100%!important}
 .stats{gap:24px}
 dialog .lb{padding:48px 8px 16px}
}
</style>
</head>
<body>
"""

LIGHTBOX = """<dialog id="lb"><div class="lb"><button class="x" aria-label="关闭">×</button>
<button class="nav prev" aria-label="上一张">‹</button><img alt=""><p></p><button class="nav next" aria-label="下一张">›</button></div></dialog>
<script>
(function(){var d=document.getElementById('lb'),im=d.querySelector('img'),cap=d.querySelector('p'),list=[],i=0;
function show(){var b=list[i];im.src=b.dataset.full;cap.textContent=b.dataset.cap+'  ·  '+(i+1)+' / '+list.length}
document.addEventListener('click',function(e){var b=e.target.closest('button.zoom');if(b){e.preventDefault();
 list=[].slice.call(b.closest('.g').querySelectorAll('button.zoom')).filter(function(x){return x.offsetParent});i=list.indexOf(b);show();d.showModal();return}
 var t=e.target.closest('.tools button');if(t){var g=document.getElementById(t.dataset.for);g.classList.toggle('show-clean',t.dataset.v==='clean');
 t.parentNode.querySelectorAll('button').forEach(function(x){x.setAttribute('aria-pressed',x===t)})}});
d.querySelector('.x').onclick=function(){d.close()};
d.querySelector('.prev').onclick=function(){i=(i+list.length-1)%list.length;show()};
d.querySelector('.next').onclick=function(){i=(i+1)%list.length;show()};
d.addEventListener('click',function(e){if(e.target.classList.contains('lb'))d.close()});
document.addEventListener('keydown',function(e){if(!d.open)return;if(e.key==='ArrowLeft')d.querySelector('.prev').click();if(e.key==='ArrowRight')d.querySelector('.next').click()});
})();
</script>"""


def _shape(a: dict) -> str:
    w, h = a["size"]
    r = w / h
    if r > 1.6:
        return "land"
    if r > 1.15:
        return "wide"
    if r < 0.85:
        return "port"
    return "sq"


def _layout(g: dict) -> str:
    n = len(g["assets"])
    if any("标注版" in a["caption"] for a in g["assets"]):
        return "sheet"
    if n >= 8:
        return "stickers"
    if n == 1:
        return "feature"
    return "mosaic"


def render_html() -> None:
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((SITE / "cases").glob("*/case.json"))]
    order = list(CASES)
    cases.sort(key=lambda c: order.index(c["case_id"]) if c["case_id"] in order else 99)
    e = html.escape

    def src(c: dict, a: dict) -> str:
        return f"cases/{e(c['case_id'])}/{e(a['file'])}"

    out = [
        PAGE_HEAD,
        '<header class="bar"><div class="wrap"><a class="brand serif" href="#">IP 资产生产 · 案例</a><nav>',
    ]
    out += [f'<a href="#{e(c["case_id"])}">{e(c["title"].split(" · ")[0])}</a>' for c in cases]
    out.append('</nav></div></header><main class="wrap"><section class="hero">')
    out.append('<p class="eyebrow">IP ASSET PRODUCTION · CASES</p>')
    out.append('<h1 class="serif">从一张定妆图，到整套可用的角色资产。</h1>')
    out.append(
        "<p>这里的每张图都来自真实的生图调用和程序后处理，没有手工修图。一个角色先定妆，"
        '再出设定图，最后按用途做成表情包、贴片、海报、介绍页等成品包。</p><div class="cards">'
    )
    for ci, c in enumerate(cases, 1):
        cover = c["groups"][0]["assets"][0]
        name, _, kind = c["title"].partition(" · ")
        n = sum(len(g["assets"]) for g in c["groups"])
        out.append(
            f'<a class="card" href="#{e(c["case_id"])}"><img src="{src(c, cover)}" alt="{e(name)}">'
            f'<div><small>CASE {ci:02d} · {e(kind)}</small><h2 class="serif">{e(name)}</h2>'
            f"<p>{len(c['groups'])} 组 · {n} 张资产</p></div></a>"
        )
    out.append("</div></section>")

    for ci, c in enumerate(cases, 1):
        cid = e(c["case_id"])
        groups = [g for g in c["groups"] if g["assets"]]
        cover = groups[0]["assets"][0]
        name, _, kind = c["title"].partition(" · ")
        n = sum(len(g["assets"]) for g in groups)
        out.append(f'<section class="case" id="{cid}"><div class="intro">')
        out.append(
            f'<figure><img src="{src(c, cover)}" alt="{e(cover["caption"])}" loading="lazy">'
            f"<figcaption>{e(cover['caption'])} · 全部资产的身份基准</figcaption></figure><div>"
        )
        out.append(f'<p class="case-no">CASE {ci:02d} · {e(kind)}</p><h2 class="serif">{e(name)}</h2>')
        out.append(f'<p class="sum">{e(c["summary"])}</p>')
        out.append(
            f'<div class="stats"><div><b>{len(groups)}</b><span>资产组</span></div>'
            f'<div><b>{n}</b><span>张成品</span></div></div><ol class="toc">'
        )
        for gi, g in enumerate(groups, 1):
            out.append(
                f'<li><a href="#{cid}-g{gi}"><span>{gi:02d}　{e(g["title"])}</span><em>{len(g["assets"])} 张</em></a></li>'
            )
        out.append("</ol></div></div>")
        for gi, g in enumerate(groups, 1):
            if gi == 1:
                continue  # 定妆图已在开头展示
            lay = _layout(g)
            gid = f"{cid}-g{gi}"
            out.append(
                f'<div class="group" id="{gid}"><div class="ghead"><h3 class="serif"><span>{gi:02d}</span>{e(g["title"])}</h3><div>'
            )
            if g["note"]:
                out.append(f"<p>{e(g['note'])}</p>")
            if lay == "sheet":
                out.append(
                    f'<div class="tools"><button data-for="{gid}-grid" data-v="labeled" aria-pressed="true">标注版</button>'
                    f'<button data-for="{gid}-grid" data-v="clean" aria-pressed="false">干净版</button></div>'
                )
            out.append("</div></div>")
            extra = f" n{len(g['assets'])}" if lay == "mosaic" else ""
            out.append(f'<div class="g g-{lay}{extra}" id="{gid}-grid">')
            per = 2 if len(g["assets"]) == 4 else 3
            for ai, a in enumerate(g["assets"]):
                if lay == "mosaic" and ai % per == 0:
                    out.append(("</div>" if ai else "") + '<div class="row">')
                cls = [_shape(a)]
                if a["file"].endswith(".png"):
                    cls.append("alpha")
                if lay == "sheet":
                    cls.append("labeled" if "标注版" in a["caption"] else "clean")
                cap = (
                    a["caption"].replace("（标注版）", "").replace("（干净版）", "") if lay == "sheet" else a["caption"]
                )
                w, h = a["size"]
                s = src(c, a)
                flex = f' style="flex:{w / h:.3f} 1 0"' if lay == "mosaic" else ""
                out.append(
                    f'<figure class="{" ".join(cls)}"{flex}><button class="zoom" data-full="{s}" data-cap="{e(cap)}">'
                    f'<img src="{s}" width="{w}" height="{h}" loading="lazy" alt="{e(cap)}"></button>'
                    f"<figcaption>{e(cap)}</figcaption></figure>"
                )
            out.append("</div></div></div>" if lay == "mosaic" else "</div></div>")
        out.append("</section>")
    out.append(
        '</main><footer><div class="wrap">图片为网页尺寸的压缩版。案例中的角色由需求方授权生成；原始参考照片不公开。</div></footer>'
    )
    out.append(LIGHTBOX + "</body></html>\n")
    (SITE / "index.html").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", action="store_true", help="only re-render index.html")
    args = ap.parse_args()
    if not args.html:
        build_cases()
    render_html()
    print("site built:", SITE / "index.html")
