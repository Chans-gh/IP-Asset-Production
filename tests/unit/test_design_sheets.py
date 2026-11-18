"""ADR-016: base groups are one design-sheet image per model call."""

from ip_asset_production.planner import generation_count
from ip_asset_production.prompting import PromptCompiler, sheet_layout


def test_base_groups_are_one_call():
    assert [generation_count(t) for t in ("BASE_VIEW", "BASE_EXPRESSION", "BASE_POSE")] == [1, 1, 1]


def test_sheet_layout_grid():
    assert sheet_layout("正面、侧面、背面")["sheet_grid"] == "1 行 × 3 列"
    assert sheet_layout("、".join("abcdefghijkl"))["sheet_grid"] == "3 行 × 4 列"


def test_base_templates_default_to_sheet_output():
    reg = PromptCompiler().registry
    for tid in ("BASE_VIEW", "BASE_EXPRESSION", "BASE_POSE"):
        t = reg.get(tid)
        assert t.variants == ("sheet",)
        assert (t.primary_output["width_px"], t.primary_output["height_px"]) == (2048, 1536)


def test_keep_main_subject_drops_edge_sliver():
    from PIL import Image

    from ip_asset_production.postprocess import keep_main_subject, subject_bbox

    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    img.paste((200, 100, 100, 255), (150, 100, 300, 350))
    img.paste((200, 100, 100, 255), (0, 50, 4, 380))  # neighbour-cell sliver
    assert subject_bbox(keep_main_subject(img)) == (150, 100, 300, 350)


def test_emoji_kit_counts_sheet_calls():
    from ip_asset_production.planner import generation_count

    assert generation_count("APP-01", {"emoji_count": 16}) == 2
    assert generation_count("APP-01", {"emoji_count": 24}) == 3


def test_group_templates_are_one_sheet_call():
    from ip_asset_production.planner import generation_count

    for tid in ("NEW-06", "NEW-12", "APP-03", "APP-05", "APP-09"):
        assert generation_count(tid) == 1


def test_annotate_sheet_keeps_grid_and_adds_title_strip():
    from PIL import Image

    from ip_asset_production.annotate import annotate_sheet
    import pytest

    from ip_asset_production.typography import TypographyError, find_font

    try:
        font = find_font()
    except TypographyError:
        pytest.skip("no CJK font on this runner")

    img = Image.new("RGB", (800, 600), (120, 160, 200))
    out = annotate_sheet(img, columns=4, rows=2, labels=["正面"] * 8, title="林汐 v1 · 视角", font=font)
    assert out.width == 800 and out.height > 600
    assert out.crop((0, out.height - 600, 800, out.height)).getpixel((790, 590)) == (120, 160, 200)
