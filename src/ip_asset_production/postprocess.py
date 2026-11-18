"""Image postprocessing: target-size fitting, alpha matting, contact sheets (SPEC §7.2, §8.1, T08/T09).

Every operation returns the steps it took so the manifest can tell *native* output apart from
processed output. Nothing here stretches an image: a different aspect ratio is padded
(``contain``) or cropped (``cover``) and recorded. Enlarging is recorded as interpolated
upscaling, never as native resolution.
"""

from __future__ import annotations

import io
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Literal

from PIL import Image, ImageChops, ImageFilter

from .models import OutputSpec

FitMode = Literal["contain", "cover"]
WARM_WHITE = (250, 247, 242)


class PostprocessError(ValueError):
    pass


@dataclass
class Processed:
    image: Image.Image
    steps: list[str] = field(default_factory=list)
    native_size: tuple[int, int] = (0, 0)
    upscaled: bool = False
    alpha_method: str | None = None
    checks: dict[str, object] = field(default_factory=dict)


def load_image(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        return im.copy()


def _ratio(w: int, h: int) -> float:
    return w / h


def fit_to_spec(
    img: Image.Image,
    spec: OutputSpec,
    *,
    mode: FitMode = "contain",
    pixel_art: bool = False,
    background: tuple[int, int, int] = WARM_WHITE,
) -> Processed:
    """Bring ``img`` to exactly ``spec.width_px`` x ``spec.height_px`` without distortion."""
    tw, th = spec.width_px, spec.height_px
    out = Processed(img, native_size=img.size)
    resample = Image.Resampling.NEAREST if pixel_art else Image.Resampling.LANCZOS
    w, h = img.size
    if (w, h) == (tw, th):
        out.steps.append("native size equals target")
        return out
    same_ratio = abs(_ratio(w, h) - _ratio(tw, th)) / _ratio(tw, th) < 0.01
    if same_ratio:
        scale = tw / w
        img2 = img.resize((tw, th), resample)
        out.steps.append(f"resize {w}x{h} -> {tw}x{th} ({'nearest' if pixel_art else 'lanczos'}, x{scale:.3f})")
    elif mode == "contain":
        scale = min(tw / w, th / h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        resized = img.resize((nw, nh), resample)
        has_alpha = img.mode in ("RGBA", "LA") or spec.alpha_required
        canvas = Image.new("RGBA" if has_alpha else "RGB", (tw, th), (0, 0, 0, 0) if has_alpha else background)
        canvas.paste(resized, ((tw - nw) // 2, (th - nh) // 2), resized if resized.mode == "RGBA" else None)
        img2 = canvas
        out.steps.append(f"contain {w}x{h} -> {nw}x{nh} on {tw}x{th} canvas (padded, no stretch)")
    else:
        scale = max(tw / w, th / h)
        nw, nh = max(tw, round(w * scale)), max(th, round(h * scale))
        resized = img.resize((nw, nh), resample)
        left, top = (nw - tw) // 2, (nh - th) // 2
        img2 = resized.crop((left, top, left + tw, top + th))
        out.steps.append(f"cover {w}x{h} -> {nw}x{nh} cropped to {tw}x{th}")
    if scale > 1.0:
        out.upscaled = True
        out.steps.append(f"interpolated upscale x{scale:.3f} (not native resolution)")
    out.image = img2
    return out


def border_color(img: Image.Image, band: int = 4) -> tuple[int, int, int]:
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    assert px is not None
    samples = []
    step = max(1, min(w, h) // 64)
    for x in range(0, w, step):
        for y in (*range(band), *range(h - band, h)):
            samples.append(px[x, y])
    for y in range(0, h, step):
        for x in (*range(band), *range(w - band, w)):
            samples.append(px[x, y])
    return tuple(int(median(c[i] for c in samples)) for i in range(3))  # type: ignore[return-value]


def remove_background(img: Image.Image, *, tolerance: int = 28, work_px: int = 384) -> Processed:
    """Degraded-mode alpha (T09): make the border-connected flat background transparent.

    Near-background pixels are found at full resolution with C-level ops; connectivity to the
    border is solved on a downscaled mask (flood fill), then intersected at full size. Works
    for the neutral flat backgrounds our prompts request. The result is verified by
    :func:`alpha_checks`; failures go to review and are never reported as native alpha.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    bg = border_color(rgb)
    diff = ImageChops.difference(rgb, Image.new("RGB", (w, h), bg))
    r, g, b = diff.split()
    dist = ImageChops.add(ImageChops.add(r, g), b)  # L1 distance, clipped at 255
    near_bg = dist.point(lambda v: 255 if v <= tolerance * 2 else 0)
    scale = min(1.0, work_px / max(w, h))
    sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
    small = near_bg.resize((sw, sh), Image.Resampling.NEAREST)
    sp = small.load()
    assert sp is not None
    connected = Image.new("L", (sw, sh), 0)
    cp = connected.load()
    assert cp is not None
    q: deque[tuple[int, int]] = deque()
    for x in range(sw):
        q.extend(((x, 0), (x, sh - 1)))
    for y in range(sh):
        q.extend(((0, y), (sw - 1, y)))
    while q:
        x, y = q.popleft()
        if cp[x, y] or not sp[x, y]:
            continue
        cp[x, y] = 255
        if x > 0:
            q.append((x - 1, y))
        if x < sw - 1:
            q.append((x + 1, y))
        if y > 0:
            q.append((x, y - 1))
        if y < sh - 1:
            q.append((x, y + 1))
    connected_full = connected.resize((w, h), Image.Resampling.NEAREST).filter(ImageFilter.MaxFilter(3))
    background = ImageChops.multiply(connected_full, near_bg)
    alpha = ImageChops.invert(background).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    res = Processed(out, native_size=img.size, alpha_method="border_flood_fill_postprocess")
    res.steps.append(f"background removal: border-connected flat background, bg={bg}, tolerance={tolerance}")
    res.checks = alpha_checks(out)
    return res


def alpha_checks(img: Image.Image) -> dict[str, object]:
    """Measured alpha facts: transparent border, plausible subject coverage."""
    if img.mode != "RGBA":
        return {"has_alpha": False, "ok": False}
    a = img.getchannel("A")
    w, h = a.size
    hist = a.histogram()
    total = w * h
    transparent = sum(hist[:16]) / total
    opaque = sum(hist[240:]) / total
    border = [a.getpixel((x, y)) for x in range(0, w, max(1, w // 64)) for y in (0, h - 1)]
    border += [a.getpixel((x, y)) for y in range(0, h, max(1, h // 64)) for x in (0, w - 1)]
    border_clear = sum(1 for v in border if isinstance(v, int) and v < 16) / len(border)
    bbox = a.point(lambda v: 255 if v > 16 else 0).getbbox()
    ok = border_clear > 0.95 and 0.03 < opaque < 0.95 and bbox is not None
    return {
        "has_alpha": True,
        "transparent_fraction": round(transparent, 4),
        "opaque_fraction": round(opaque, 4),
        "border_transparent_fraction": round(border_clear, 4),
        "subject_bbox": bbox,
        "ok": ok,
    }


def clean_native_alpha(img: Image.Image, *, floor: int = 32, speck_px: int = 5) -> tuple[Image.Image, list[str]]:
    """Tidy a provider-supplied alpha channel: drop near-transparent haze and isolated specks.

    Morphological opening on the binary mask removes islands thinner than ``speck_px``; a 3 px
    dilation of the kept region preserves the anti-aliased edge of the subject.
    """
    rgba = img.convert("RGBA")
    a = rgba.getchannel("A")
    mask = a.point(lambda v: 255 if v >= floor else 0)
    kept = mask.filter(ImageFilter.MinFilter(speck_px)).filter(ImageFilter.MaxFilter(speck_px))
    keep = kept.filter(ImageFilter.MaxFilter(3))
    new_a = ImageChops.multiply(a.point(lambda v: v if v >= floor else 0), keep)
    rgba.putalpha(new_a)
    return rgba, [f"native alpha cleaned (alpha<{floor} cleared, specks <{speck_px}px removed)"]


def has_real_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def ensure_alpha(img: Image.Image, *, provider_alpha_native: bool = False) -> Processed:
    """Use the provider's alpha when the returned file *measurably* has a usable one.

    ``provider_alpha_native`` (declared capability) is not required: some models return a
    transparent PNG when asked even though the provider does not guarantee it, so each output is
    measured. Converting such a file to RGB would turn the transparent area black and leave the
    semi-transparent fringe as specks, so background removal is only the fallback.
    """
    if has_real_alpha(img):
        raw = img.convert("RGBA")
        if alpha_checks(raw)["ok"]:
            cleaned, steps = clean_native_alpha(raw)
            checks = alpha_checks(cleaned)
            if checks["ok"]:
                res = Processed(cleaned, native_size=img.size, alpha_method="native", checks=checks)
                res.steps.append("native alpha measured in provider output and verified")
                res.steps.extend(steps)
                return res
        img = Image.alpha_composite(Image.new("RGBA", raw.size, (255, 255, 255, 255)), raw)
    return remove_background(img)


def subject_bbox(
    img: Image.Image, background: tuple[int, int, int] | None = None, tol: int = 24
) -> tuple[int, int, int, int] | None:
    if img.mode == "RGBA":
        return img.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
    bg = background or border_color(img)
    rgb = img.convert("RGB")
    diff = Image.new("RGB", rgb.size, bg)
    d = ImageChops.difference(rgb, diff).convert("L").point(lambda v: 255 if v > tol else 0)
    return d.getbbox()


def within_safe_margin(img: Image.Image, margin_pct: float) -> tuple[bool, str]:
    box = subject_bbox(img)
    if box is None:
        return False, "no subject detected"
    w, h = img.size
    mx, my = w * margin_pct, h * margin_pct
    left, top, right, bottom = box
    ok = left >= mx - 1 and top >= my - 1 and right <= w - mx + 1 and bottom <= h - my + 1
    return ok, f"subject bbox {box} vs margin {margin_pct:.0%}"


def keep_main_subject(img: Image.Image, *, scale: int = 4, floor: int = 32) -> Image.Image:
    """Clear alpha outside the bounding box of the largest opaque component.

    Sheet cells often carry slivers of the neighbouring cell at their edges; those would
    stretch the subject bbox and push the subject off-centre when it is fitted.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size
    sw, sh = max(1, w // scale), max(1, h // scale)
    small = rgba.getchannel("A").resize((sw, sh), Image.Resampling.BOX)
    px = small.load()
    seen = [[False] * sw for _ in range(sh)]
    best: tuple[int, tuple[int, int, int, int]] | None = None
    for y0 in range(sh):
        for x0 in range(sw):
            if seen[y0][x0] or px[x0, y0] < floor:
                continue
            seen[y0][x0] = True
            q, n = deque([(x0, y0)]), 0
            bx0, by0, bx1, by1 = x0, y0, x0, y0
            while q:
                x, y = q.popleft()
                n += 1
                bx0, by0, bx1, by1 = min(bx0, x), min(by0, y), max(bx1, x), max(by1, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < sw and 0 <= ny < sh and not seen[ny][nx] and px[nx, ny] >= floor:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            if best is None or n > best[0]:
                best = (n, (bx0, by0, bx1, by1))
    if best is None:
        return rgba
    bx0, by0, bx1, by1 = best[1]
    box = (max(0, (bx0 - 1) * scale), max(0, (by0 - 1) * scale), min(w, (bx1 + 2) * scale), min(h, (by1 + 2) * scale))
    mask = Image.new("L", (w, h), 0)
    mask.paste(255, box)
    out = rgba.copy()
    out.putalpha(ImageChops.multiply(rgba.getchannel("A"), mask))
    return out


def fit_subject_with_margin(img: Image.Image, size: tuple[int, int], margin_pct: float) -> Image.Image:
    """Re-centre an RGBA subject inside a canvas leaving ``margin_pct`` on all sides."""
    rgba = img.convert("RGBA")
    box = subject_bbox(rgba)
    if box is None:
        raise PostprocessError("no subject to place")
    crop = rgba.crop(box)
    tw, th = size
    avail_w, avail_h = tw * (1 - 2 * margin_pct), th * (1 - 2 * margin_pct)
    scale = min(avail_w / crop.width, avail_h / crop.height)
    nw, nh = max(1, int(crop.width * scale)), max(1, int(crop.height * scale))
    crop = crop.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(crop, ((tw - nw) // 2, (th - nh) // 2), crop)
    return canvas


def slice_sheet(img: Image.Image, columns: int, rows: int) -> list[Image.Image]:
    """Cut a model-generated design sheet into its equal grid cells (row-major)."""
    w, h = img.size
    cells = []
    for r in range(rows):
        for c in range(columns):
            box = (round(c * w / columns), round(r * h / rows), round((c + 1) * w / columns), round((r + 1) * h / rows))
            cells.append(img.crop(box))
    return cells


def contact_sheet(
    images: Sequence[Image.Image],
    *,
    columns: int,
    cell: tuple[int, int],
    gap: int = 0,
    background: tuple[int, int, int] = WARM_WHITE,
    size: tuple[int, int] | None = None,
) -> Image.Image:
    """Compose already-validated independent images into a grid (composites come *after* QA)."""
    if not images:
        raise PostprocessError("contact sheet needs at least one image")
    rows = -(-len(images) // columns)
    cw, ch = cell
    w = size[0] if size else columns * cw + (columns + 1) * gap
    h = size[1] if size else rows * ch + (rows + 1) * gap
    sheet = Image.new("RGB", (w, h), background)
    for i, im in enumerate(images):
        r, c = divmod(i, columns)
        tile = im.copy()
        tile.thumbnail(cell, Image.Resampling.LANCZOS)
        x = gap + c * (cw + gap) + (cw - tile.width) // 2
        y = gap + r * (ch + gap) + (ch - tile.height) // 2
        sheet.paste(tile, (x, y), tile if tile.mode == "RGBA" else None)
    return sheet
