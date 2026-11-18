"""Program-drawn labels on design sheets (ADR-017).

The model always generates a seamless, text-free grid; when a sheet is meant as reference
material (video / image generation, knowledge base) the exact labels are drawn here, so the
wording is always correct and the clean sheet stays available.
"""

from __future__ import annotations

from collections.abc import Sequence

from PIL import Image, ImageDraw

from .typography import FontChoice, _font


def annotate_sheet(
    img: Image.Image,
    *,
    columns: int,
    rows: int,
    labels: Sequence[str],
    title: str,
    font: FontChoice,
) -> Image.Image:
    """Return a copy with a title strip on top and a numbered tag in each cell's top-left corner.

    The grid itself is untouched (no gutters are added), so cells stay aligned with the clean sheet.
    """
    base = img.convert("RGB")
    w, h = base.size
    head = max(48, h // 16)
    out = Image.new("RGB", (w, h + head), (250, 248, 244))
    out.paste(base, (0, head))
    d = ImageDraw.Draw(out, "RGBA")
    d.text((head // 3, head // 2), title, font=_font(font.path, int(head * 0.5)), fill=(34, 34, 34), anchor="lm")
    cw, ch = w / columns, h / rows
    size = max(14, int(min(cw, ch) * 0.075))
    f = _font(font.path, size)
    pad = size // 3
    for i, label in enumerate(labels[: columns * rows]):
        r, c = divmod(i, columns)
        x, y = int(c * cw) + pad, int(head + r * ch) + pad
        text = f"{i + 1:02d} {label}"
        box = d.textbbox((x + pad, y + pad // 2), text, font=f)
        d.rounded_rectangle((x, y, box[2] + pad, box[3] + pad // 2), radius=pad, fill=(20, 20, 20, 170))
        d.text((x + pad, y + pad // 2), text, font=f, fill=(255, 255, 255))
    return out
