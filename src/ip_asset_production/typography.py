"""Deterministic typography layer (SPEC §0.7, §7.2; T12).

Exact Chinese text, labels and numbers are drawn here — never by the image model. A CJK font
must be configured (``IPAP_FONT_PATH``) or discoverable among well-known system paths; there is
no silent fallback to a font that lacks the glyphs. Fonts are user/system assets and are never
committed (SPEC §11: no restricted fonts in the repository).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CANDIDATE_FONTS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
)


class TypographyError(RuntimeError):
    pass


@dataclass(frozen=True)
class FontChoice:
    path: str
    family: str
    license_note: str


@dataclass(frozen=True)
class TextRecord:
    """What the layout engine actually drew — QA compares ``text`` with the approved value."""

    text: str
    box: tuple[int, int, int, int]
    font_path: str
    font_size: int
    lines: tuple[str, ...]


def find_font(explicit: str | None = None) -> FontChoice:
    path = explicit or os.environ.get("IPAP_FONT_PATH")
    candidates = [path] if path else list(CANDIDATE_FONTS)
    for c in candidates:
        if c and Path(c).is_file():
            font = ImageFont.truetype(c, 32)
            family = " ".join(x for x in font.getname() if x)
            return FontChoice(c, family, "system/user font; license must allow the intended commercial use")
    if path:
        raise TypographyError(f"IPAP_FONT_PATH={path!r} does not exist")
    raise TypographyError(
        "no CJK font found; set IPAP_FONT_PATH to a licensed CJK font (e.g. Noto Sans CJK / Source Han Sans)"
    )


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=8)
def _cmap(path: str) -> frozenset[int] | None:
    try:
        from fontTools.ttLib import TTCollection, TTFont  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - fonttools is a declared dependency
        return None
    if path.lower().endswith(".ttc"):
        fonts = TTCollection(path, lazy=True).fonts
        cmap: set[int] = set()
        for f in fonts:
            cmap |= set(f.getBestCmap() or {})
        return frozenset(cmap)
    return frozenset(TTFont(path, lazy=True).getBestCmap() or {})


def missing_glyphs(font_path: str, text: str) -> list[str]:
    cmap = _cmap(font_path)
    if cmap is None:  # pragma: no cover
        return []
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cmap})


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for ch in para:
            trial = line + ch
            if font.getlength(trial) <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = ch
        lines.append(line)
    return lines


def draw_text(
    img: Image.Image,
    text: str,
    box: tuple[int, int, int, int],
    *,
    font: FontChoice,
    color: tuple[int, int, int] | tuple[int, int, int, int] = (34, 34, 34),
    max_size: int = 400,
    min_size: int = 12,
    align: str = "left",
    valign: str = "middle",
    line_spacing: float = 1.2,
    max_lines: int = 3,
) -> TextRecord:
    """Draw ``text`` as large as fits inside ``box``; raise if it cannot fit or glyphs are missing."""
    missing = missing_glyphs(font.path, text)
    if missing:
        raise TypographyError(f"font {font.family} lacks glyphs {missing}")
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    lo, hi, best = min_size, max_size, None
    while lo <= hi:
        size = (lo + hi) // 2
        f = _font(font.path, size)
        lines = _wrap(text, f, bw)
        asc, desc = f.getmetrics()
        lh = int((asc + desc) * line_spacing)
        total_h = lh * len(lines)
        widest = max(f.getlength(line) for line in lines)
        if len(lines) <= max_lines and total_h <= bh and widest <= bw:
            best = (size, lines, lh, total_h)
            lo = size + 1
        else:
            hi = size - 1
    if best is None:
        raise TypographyError(f"text {text!r} does not fit in box {box} at >= {min_size}px")
    size, lines, lh, total_h = best
    f = _font(font.path, size)
    draw = ImageDraw.Draw(img)
    y = y0 + (bh - total_h) // 2 if valign == "middle" else (y0 if valign == "top" else y1 - total_h)
    for line in lines:
        lw = f.getlength(line)
        x = x0 if align == "left" else (x0 + (bw - lw) / 2 if align == "center" else x1 - lw)
        draw.text((x, y), line, font=f, fill=color)
        y += lh
    return TextRecord(text, box, font.path, size, tuple(lines))
