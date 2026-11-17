"""Deterministic physical-size helpers for print layouts (SPEC §8.2)."""

from __future__ import annotations

MM_PER_INCH = 25.4


def print_pixels(mm: float, bleed: float, ppi: float) -> int:
    """Pixels along one edge of a print canvas including bleed on both sides.

    SPEC §8.2 formula: ``round((mm + 2*bleed) / 25.4 * ppi)``.
    Example: APP-02 door sign 300 mm wide, 3 mm bleed, 300 ppi -> 3614 px.
    """
    if mm <= 0:
        raise ValueError("trim size must be positive")
    if bleed < 0:
        raise ValueError("bleed must be non-negative")
    if ppi <= 0:
        raise ValueError("ppi must be positive")
    return round((mm + 2 * bleed) / MM_PER_INCH * ppi)


def print_canvas_px(trim_mm: tuple[float, float], bleed_mm: float, ppi: float) -> tuple[int, int]:
    """(width_px, height_px) of a print canvas with bleed."""
    w, h = trim_mm
    return print_pixels(w, bleed_mm, ppi), print_pixels(h, bleed_mm, ppi)


def mm_to_px(mm: float, ppi: float) -> int:
    """Convert a single length (no bleed) to pixels."""
    if ppi <= 0:
        raise ValueError("ppi must be positive")
    return round(mm / MM_PER_INCH * ppi)
