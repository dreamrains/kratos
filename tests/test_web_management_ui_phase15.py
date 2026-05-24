from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_management_ui_exposes_closed_loop_actions():
    html = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")

    assert "提升为知识" in html
    assert "编辑记忆" in html
    assert "重新索引" in html
    assert "全局搜索" in html
    assert "promoteMemory" in js
    assert "updateMemory" in js
    assert "indexEvidence" in js
    assert "globalManagementSearch" in js


def test_management_ui_keeps_chinese_utf8_text():
    html = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")

    assert "返回应用" in html
    assert "知识库" in html
    assert "记忆" in html
    assert "添加技能" in html
    assert "MCP 服务器" in js or "MCP 服务器" in html
