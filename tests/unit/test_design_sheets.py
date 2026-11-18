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
