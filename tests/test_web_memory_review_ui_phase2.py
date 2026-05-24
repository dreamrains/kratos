from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_memory_review_ui_exposes_reason_sources_and_extract_action():
    html = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")

    assert "提取当前会话记忆" in html
    assert "提取原因" in html
    assert "来源证据" in html
    assert "需要审核" in html
    assert "extractMemoryCandidates" in js
    assert "loadMemorySources" in js
