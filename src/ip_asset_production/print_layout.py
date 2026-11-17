"""Print geometry, door-sign style layouts and print-ready PDFs (SPEC §8.2; T07).

PDF pages carry explicit ``TrimBox`` (finished size) and ``BleedBox`` (trim + bleed); the
``MediaBox`` adds a slug with crop marks outside the bleed. The artwork is embedded as a
lossless 8-bit RGB image at the stated ppi. This is an RGB proof-grade file: a printer's CMYK /
ICC requirements are *not* claimed (SPEC §8.2) and must be applied per print shop.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .units import print_pixels

PT_PER_MM = 72 / 25.4


@dataclass(frozen=True)
class PrintSpec:
    trim_mm: tuple[float, float]
    bleed_mm: float = 3.0
    ppi: int = 300
    safe_mm: float = 8.0

    @property
    def canvas_px(self) -> tuple[int, int]:
        """Full bleed canvas: ``round((mm + 2*bleed)/25.4*ppi)`` per side."""
        w, h = self.trim_mm
        return print_pixels(w, self.bleed_mm, self.ppi), print_pixels(h, self.bleed_mm, self.ppi)

    def mm_to_px(self, mm: float) -> int:
        return round(mm / 25.4 * self.ppi)

    @property
    def trim_box_px(self) -> tuple[int, int, int, int]:
        b = self.mm_to_px(self.bleed_mm)
        w, h = self.canvas_px
        return b, b, w - b, h - b

    @property
    def safe_box_px(self) -> tuple[int, int, int, int]:
        s = self.mm_to_px(self.bleed_mm + self.safe_mm)
        w, h = self.canvas_px
        return s, s, w - s, h - s


def write_print_pdf(img: Image.Image, spec: PrintSpec, path: Path, *, slug_mm: float = 6.0, title: str = "") -> Path:
    """Write ``img`` (exactly ``spec.canvas_px``) as a single-page PDF with trim/bleed boxes and crop marks."""
    if img.size != spec.canvas_px:
        raise ValueError(f"artwork is {img.size}, print canvas must be {spec.canvas_px}")
    rgb = img.convert("RGB")
    tw, th = spec.trim_mm
    b = spec.bleed_mm
    media_w, media_h = (tw + 2 * (b + slug_mm)) * PT_PER_MM, (th + 2 * (b + slug_mm)) * PT_PER_MM
    ox = oy = slug_mm * PT_PER_MM  # bleed box origin
    bleed = (ox, oy, ox + (tw + 2 * b) * PT_PER_MM, oy + (th + 2 * b) * PT_PER_MM)
    trim = (ox + b * PT_PER_MM, oy + b * PT_PER_MM, bleed[2] - b * PT_PER_MM, bleed[3] - b * PT_PER_MM)

    def box(v: tuple[float, float, float, float]) -> str:
        return "[" + " ".join(f"{x:.3f}" for x in v) + "]"

    ops = [f"q {bleed[2] - bleed[0]:.3f} 0 0 {bleed[3] - bleed[1]:.3f} {bleed[0]:.3f} {bleed[1]:.3f} cm /Im0 Do Q"]
    if slug_mm > 0:
        gap, length = b * PT_PER_MM + 1 * PT_PER_MM, max(1.0, slug_mm - 1.5) * PT_PER_MM
        ops.append("0 0 0 RG 0.25 w")
        for x in (trim[0], trim[2]):
            for y, sgn in ((trim[1], -1), (trim[3], 1)):
                ops.append(f"{x:.3f} {y + sgn * gap:.3f} m {x:.3f} {y + sgn * (gap + length):.3f} l S")
        for y in (trim[1], trim[3]):
            for x, sgn in ((trim[0], -1), (trim[2], 1)):
                ops.append(f"{x + sgn * gap:.3f} {y:.3f} m {x + sgn * (gap + length):.3f} {y:.3f} l S")
    content = "\n".join(ops).encode("ascii")
    pixels = zlib.compress(rgb.tobytes(), 9)
    w_px, h_px = rgb.size
    safe_title = re.sub(r"[^A-Za-z0-9 _.-]", "_", title)[:120]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {media_w:.3f} {media_h:.3f}] "
            f"/BleedBox {box(bleed)} /TrimBox {box(trim)} "
            f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>"
        ).encode("ascii"),
        (
            f"<< /Type /XObject /Subtype /Image /Width {w_px} /Height {h_px} /ColorSpace /DeviceRGB "
            f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(pixels)} >>\nstream\n"
        ).encode("ascii")
        + pixels
        + b"\nendstream",
        f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream",
        f"<< /Title ({safe_title}) /Producer (ip-asset-production) >>".encode("ascii"),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
        "ascii"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pdf.tmp")
    tmp.write_bytes(bytes(out))
    tmp.replace(path)
    return path


BOX_RE = re.compile(rb"/(MediaBox|BleedBox|TrimBox) \[([-0-9. ]+)\]")
IMG_RE = re.compile(rb"/Subtype /Image /Width (\d+) /Height (\d+)")


@dataclass(frozen=True)
class PdfFacts:
    trim_mm: tuple[float, float]
    bleed_mm: float
    media_mm: tuple[float, float]
    image_px: tuple[int, int]
    effective_ppi: float


def inspect_print_pdf(path: Path) -> PdfFacts:
    """Read back page boxes and image size from a PDF we wrote (measured, not assumed)."""
    data = Path(path).read_bytes()
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-32:]:
        raise ValueError("not a complete PDF file")
    boxes = {}
    for name, vals in BOX_RE.findall(data):
        nums = [float(v) for v in vals.split()]
        boxes[name.decode()] = (nums[2] - nums[0], nums[3] - nums[1])
    if not {"MediaBox", "BleedBox", "TrimBox"} <= boxes.keys():
        raise ValueError("PDF lacks MediaBox/BleedBox/TrimBox")
    m = IMG_RE.search(data)
    if not m:
        raise ValueError("PDF has no image XObject")
    trim = (boxes["TrimBox"][0] / PT_PER_MM, boxes["TrimBox"][1] / PT_PER_MM)
    bleed_w = boxes["BleedBox"][0] / PT_PER_MM
    img_px = (int(m.group(1)), int(m.group(2)))
    return PdfFacts(
        trim_mm=(round(trim[0], 2), round(trim[1], 2)),
        bleed_mm=round((bleed_w - trim[0]) / 2, 2),
        media_mm=(round(boxes["MediaBox"][0] / PT_PER_MM, 2), round(boxes["MediaBox"][1] / PT_PER_MM, 2)),
        image_px=img_px,
        effective_ppi=round(img_px[0] / ((bleed_w) / 25.4), 1),
    )
