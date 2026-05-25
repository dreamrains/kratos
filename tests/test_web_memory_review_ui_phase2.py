import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _method_body(js: str, name: str) -> str:
    match = re.search(rf"async {name}\([^)]*\) {{(?P<body>.*?)\n        }},", js, re.S)
    assert match, f"{name} method not found"
    return match.group("body")


def test_memory_review_ui_exposes_reason_sources_and_extract_action():
    html = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")

    assert "\u63d0\u53d6\u5f53\u524d\u4f1a\u8bdd\u8bb0\u5fc6" in html
    assert "\u63d0\u53d6\u539f\u56e0" in html
    assert "\u6765\u6e90\u8bc1\u636e" in html
    assert "\u9700\u8981\u5ba1\u6838" in html
    assert 'value="preference"' in html
    assert 'value="correction"' in html
    assert 'value="data_insight"' not in html
    assert "extractMemoryCandidates" in js
    assert "loadMemorySources" in js


def test_memory_review_ui_tracks_sources_and_review_payload_fields():
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    payload = js[js.index("_memoryReviewPayload") : js.index("async saveMemoryCandidate")]

    assert "memorySources: null" in js
    assert "reason: form.reason || ''" in payload
    assert "source_evidence_ids: this._memorySourceEvidenceIds(form)" in payload
    assert "needs_review: !!form.needs_review" in payload
    assert "review_note: form.review_note || ''" in payload
    assert "dedup_key: form.dedup_key || ''" in payload


def test_memory_extraction_rejects_unsaved_pending_session():
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    body = _method_body(js, "extractMemoryCandidates")

    assert "this.currentSessionId !== '_pending_'" in body
    assert "/api/management/memory/extract" in body


def test_memory_sources_resets_stale_state_and_handles_fetch_failures():
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    body = _method_body(js, "loadMemorySources")

    assert "this.managementCenter.memorySources = { memory_id: item.id, sources: [] }" in body
    assert "if (!res.ok)" in body
    assert "catch (e)" in body
    assert "\u6765\u6e90\u8bc1\u636e\u52a0\u8f7d\u5931\u8d25" in body
