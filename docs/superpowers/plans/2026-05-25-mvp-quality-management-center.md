# MVP Quality and Management Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the knowledge and memory MVP against real data-analysis workflows, then improve the management center only where validation exposes usability, traceability, or safety gaps.

**Architecture:** Treat `reference/test_doc` as a fixed real-data validation fixture set. Add focused automated tests for memory extraction quality, retrieval budget safety, and management-center review workflows before changing UI or APIs. Keep the system rule-first and auditable; do not add a vector database, persona layer, automatic skill generation, or complex governance UI in this phase.

**Tech Stack:** Python 3, pytest, openpyxl, Flask test client, Alpine.js static UI tests, Codex Browser validation, existing SQLite + Markdown knowledge storage.

---

## Scope Boundary

This phase is about MVP quality and product usability, not feature expansion.

In scope:

- Real-data scenario inventory from `reference/test_doc`.
- Automated tests using selected Excel files.
- False-positive memory extraction checks for ordinary data-analysis sessions.
- Positive candidate extraction checks for explicit remember/default/correction language.
- Confirmed-memory retrieval checks with rendered-context budget metadata.
- Management center review workflow tests and focused UI polish.
- Browser-based management center smoke validation after UI changes.

Out of scope:

- Vector retrieval.
- Persona system.
- Automatic formal knowledge creation.
- Automatic skill generation.
- Complex conflict arbitration workflow.
- Knowledge graph UI.
- Large governance dashboard.
- Full spreadsheet analytics correctness validation.

Real-data fixture policy:

- Fast tests may use:
  - `reference/test_doc/游戏B留存.xlsx`
  - `reference/test_doc/游戏A内购数据.xlsx`
  - `reference/test_doc/省钱卡订单_20260507.xlsx`
- Slower real-data tests may use:
  - `reference/test_doc/游戏互推.xlsx`
  - `reference/test_doc/省钱卡用户最近流水_20260511.xlsx`
- Tests must skip cleanly when `reference/test_doc` is absent.
- Tests must not mutate files under `reference/test_doc`.

---

## File Structure

- Create `tests/test_mvp_real_data_fixtures.py`: verifies fixture availability, workbook readability, and field expectations.
- Create `tests/test_mvp_memory_quality_real_data.py`: validates memory extraction behavior on real-data-style sessions.
- Create `tests/test_mvp_retrieval_budget_real_data.py`: validates confirmed memory retrieval and rendered prompt budget with real-data domains.
- Create `tests/test_mvp_management_center_quality.py`: validates management API/UI contract for the review workflow.
- Modify `src/data_agent/knowledge/candidates.py`: only if validation exposes false positives or weak reasons.
- Modify `src/data_agent/knowledge/retrieval.py`: only if validation exposes budget or prompt-size issues.
- Modify `src/data_agent/web/blueprints/management.py`: only if validation exposes API contract gaps.
- Modify `src/data_agent/web/templates/index.html`: only if management-center usability gaps are found.
- Modify `src/data_agent/web/static/js/app.js`: only if management-center workflow gaps are found.
- Modify `src/data_agent/web/static/css/app.css`: only if review UI clarity or consistency needs targeted polish.
- Create `docs/superpowers/specs/2026-05-25-mvp-quality-results.md`: records scenario results, accepted gaps, and next-step decisions.

---

### Task 1: Real Data Fixture Inventory

**Files:**

- Create: `tests/test_mvp_real_data_fixtures.py`
- Create: `docs/superpowers/specs/2026-05-25-mvp-quality-results.md`

- [ ] **Step 1: Write fixture inventory tests**

Create `tests/test_mvp_real_data_fixtures.py`:

```python
from pathlib import Path

import pytest
from openpyxl import load_workbook


TEST_DOC_DIR = Path("reference/test_doc")


EXPECTED_FILES = {
    "游戏B留存.xlsx": {"日期", "日活跃", "日新增", "1天后", "7天后"},
    "游戏A内购数据.xlsx": {"日期", "活跃用户", "付费人数", "内购收入", "付费率"},
    "省钱卡订单_20260507.xlsx": {"user_id", "商品名称", "支付金额", "支付时间"},
}


def _headers(path: Path) -> set[str]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
            values = {str(value).strip() for value in row if value is not None and str(value).strip()}
            if values:
                return values
    finally:
        wb.close()
    return set()


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_fast_real_data_fixtures_are_available_and_readable():
    for filename, required_headers in EXPECTED_FILES.items():
        path = TEST_DOC_DIR / filename
        assert path.exists(), f"{filename} is missing"
        headers = _headers(path)
        assert required_headers <= headers


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_large_real_data_fixture_is_present_but_not_loaded_by_fast_tests():
    path = TEST_DOC_DIR / "省钱卡用户最近流水_20260511.xlsx"

    assert path.exists()
    assert path.stat().st_size > 500_000
```

- [ ] **Step 2: Run test to verify it passes or skips cleanly**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_real_data_fixtures.py -q
```

Expected: PASS when `reference/test_doc` exists, SKIP otherwise.

- [ ] **Step 3: Create result log document**

Create `docs/superpowers/specs/2026-05-25-mvp-quality-results.md`:

```markdown
# MVP Quality Validation Results

## Fixture Set

- Fast fixtures:
  - `游戏B留存.xlsx`
  - `游戏A内购数据.xlsx`
  - `省钱卡订单_20260507.xlsx`
- Slow fixture:
  - `省钱卡用户最近流水_20260511.xlsx`

## Validation Summary

This document records validation results for the knowledge and memory MVP.

## Accepted Constraints

- Candidate extraction remains rule-first.
- Candidate memories do not enter retrieval before confirmation.
- Evidence retrieval requires an explicit evidence character budget.
- Large-file checks stay out of the default fast unit suite.
```

- [ ] **Step 4: Commit**

Run:

```bash
git add tests/test_mvp_real_data_fixtures.py docs/superpowers/specs/2026-05-25-mvp-quality-results.md
git commit -m "Add MVP real data fixture inventory"
```

---

### Task 2: Memory Extraction Quality With Real Data Sessions

**Files:**

- Create: `tests/test_mvp_memory_quality_real_data.py`
- Modify: `src/data_agent/knowledge/candidates.py` only if tests expose a real extraction-quality bug.

- [ ] **Step 1: Write memory quality tests**

Create `tests/test_mvp_memory_quality_real_data.py`:

```python
from pathlib import Path

import pytest

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.session.history import save_session


TEST_DOC_DIR = Path("reference/test_doc")


def _configure(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return cfg


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_ordinary_real_data_analysis_does_not_create_memory_candidates(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    data_file = TEST_DOC_DIR / "游戏B留存.xlsx"

    save_session(
        [
            {
                "role": "user",
                "content": f"请分析这个留存文件：{data_file.name}，重点看次日留存和7日留存趋势。",
            },
            {
                "role": "assistant",
                "content": "已读取字段：日期、日活跃、日新增、1天后、7天后，并准备做趋势分析。",
            },
        ],
        "ordinary_retention_analysis",
        extra_meta={"project_name": "game-retention-review"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert candidates == []


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_explicit_metric_memory_from_real_data_session_has_traceable_source(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)

    save_session(
        [
            {
                "role": "user",
                "content": "请记住：游戏留存分析默认先看次日留存、7日留存，再结合日新增判断投放质量。",
            }
        ],
        "remember_game_retention_flow",
        extra_meta={"project_name": "game"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert len(candidates) == 1
    assert candidates[0].reason
    assert candidates[0].source_evidence_ids
    assert candidates[0].domain == "game"


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_user_correction_from_order_data_requires_review(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)

    save_session(
        [
            {
                "role": "user",
                "content": "纠正一下：省钱卡订单分析里的支付金额应该按支付时间归属，不按创建时间归属。",
            }
        ],
        "order_metric_correction",
        extra_meta={"project_name": "savings-card-q2"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert len(candidates) == 1
    assert candidates[0].needs_review is True
    assert candidates[0].type.value == "correction"
    assert candidates[0].project_id == "savings-card-q2"
    assert candidates[0].domain == "general"
```

- [ ] **Step 2: Run test to verify behavior**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_memory_quality_real_data.py -q
```

Expected: PASS. If it fails because ordinary analysis creates noisy candidates, fix `src/data_agent/knowledge/candidates.py` by tightening marker rules, then rerun.

- [ ] **Step 3: Run related candidate suites**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_memory_quality_real_data.py tests/test_memory_candidate_extractor.py tests/test_memory_candidate_auto_extract.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add tests/test_mvp_memory_quality_real_data.py src/data_agent/knowledge/candidates.py
git commit -m "Validate memory extraction with real data sessions"
```

If `src/data_agent/knowledge/candidates.py` did not change, omit it from `git add`.

---

### Task 3: Retrieval Budget Quality With Real Data Domains

**Files:**

- Create: `tests/test_mvp_retrieval_budget_real_data.py`
- Modify: `src/data_agent/knowledge/retrieval.py` only if tests expose a real budget issue.

- [ ] **Step 1: Write real-data retrieval budget tests**

Create `tests/test_mvp_retrieval_budget_real_data.py`:

```python
from pathlib import Path

import pytest

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.retrieval import KnowledgeRetrievalService
from data_agent.session.history import save_session


TEST_DOC_DIR = Path("reference/test_doc")


def _configure(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return cfg


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_candidate_memory_stays_out_of_prompt_until_confirmed(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    save_session(
        [{"role": "user", "content": "请记住：游戏付费分析默认同时看付费率、ARPU 和 ARPPU。"}],
        "payment_memory_candidate",
        extra_meta={"project_name": "game"},
    )

    service = KnowledgeRetrievalService()
    before = service.retrieve("游戏付费分析 ARPU ARPPU", domain="game", max_total_retrieval_chars=1200)

    assert before.memory_items == []
    assert "<memory_hints" not in service.compose_prompt_context(before)

    store = MemoryStore(cfg.knowledge_dir)
    candidate = store.list(status="candidate")[0]
    store.confirm(candidate.id)

    after = service.retrieve("游戏付费分析 ARPU ARPPU", domain="game", max_total_retrieval_chars=1200)
    prompt = service.compose_prompt_context(after)

    assert after.memory_items
    assert "<memory_hints" in prompt
    assert len(prompt) <= after.metadata["total_retrieval_chars"]
    assert after.metadata["total_retrieval_chars"] <= 1200


@pytest.mark.skipif(not TEST_DOC_DIR.exists(), reason="reference/test_doc not found")
def test_evidence_requires_explicit_budget_for_real_data_session(tmp_path: Path, monkeypatch):
    cfg = _configure(tmp_path, monkeypatch)
    save_session(
        [
            {"role": "user", "content": "分析省钱卡订单_20260507.xlsx 的支付金额。"},
            {"role": "assistant", "content": "订单文件包含支付金额、支付时间和创建时间字段。"},
        ],
        "savings_card_evidence_budget",
        extra_meta={"project_name": "savings-card-q2"},
    )

    service = KnowledgeRetrievalService(sessions_dir=cfg.sessions_resolved)
    without_budget = service.retrieve(
        "省钱卡 支付金额 支付时间",
        project_id="savings-card-q2",
        include_evidence=True,
    )
    with_budget = service.retrieve(
        "省钱卡 支付金额 支付时间",
        project_id="savings-card-q2",
        include_evidence=True,
        max_evidence_chars=1000,
    )

    assert without_budget.evidence_items == []
    assert with_budget.evidence_items
```

- [ ] **Step 2: Run test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_retrieval_budget_real_data.py -q
```

Expected: PASS.

- [ ] **Step 3: Run related retrieval suites**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_retrieval_budget_real_data.py tests/test_retrieval_budget_phase2.py tests/test_knowledge_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add tests/test_mvp_retrieval_budget_real_data.py src/data_agent/knowledge/retrieval.py
git commit -m "Validate retrieval budgets with real data scenarios"
```

If `src/data_agent/knowledge/retrieval.py` did not change, omit it from `git add`.

---

### Task 4: Management Center Review Workflow Quality

**Files:**

- Create: `tests/test_mvp_management_center_quality.py`
- Modify: `src/data_agent/web/blueprints/management.py` only if tests expose an API contract gap.
- Modify: `src/data_agent/web/templates/index.html` only if tests expose a UI contract gap.
- Modify: `src/data_agent/web/static/js/app.js` only if tests expose a UI workflow gap.
- Modify: `src/data_agent/web/static/css/app.css` only if tests expose a targeted visual consistency gap.

- [ ] **Step 1: Write management quality tests**

Create `tests/test_mvp_management_center_quality.py`:

```python
import json
from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


ROOT = Path(__file__).resolve().parents[1]


def _client(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return create_app().test_client(), cfg


def test_management_center_review_flow_api_contract(tmp_path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    session_dir = cfg.sessions_resolved / "review_flow"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "game", "saved_at": "2026-05-25T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [{"role": "user", "content": "请记住：游戏留存分析默认先看次日留存，再看7日留存。"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    extract = client.post("/api/management/memory/extract", json={"session_id": "review_flow"})
    assert extract.status_code == 200
    candidate = client.get("/api/management/memory?status=candidate").get_json()[0]

    assert candidate["reason"]
    assert candidate["source_evidence_ids"]
    assert candidate["dedup_key"]

    sources = client.get(f"/api/management/memory/{candidate['id']}/sources").get_json()
    assert sources["memory_id"] == candidate["id"]
    assert sources["sources"]

    edit = client.patch(
        f"/api/management/memory/{candidate['id']}",
        json={"review_note": "Reviewed from MVP quality flow", "needs_review": "false"},
    )
    assert edit.status_code == 200
    assert edit.get_json()["review_note"] == "Reviewed from MVP quality flow"
    assert edit.get_json()["needs_review"] is False


def test_management_center_static_contract_for_review_workflow():
    html = (ROOT / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    js = (ROOT / "src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")

    assert "提取当前会话记忆" in html
    assert "查看来源" in html
    assert "需要审核" in html
    assert "review_note" in js
    assert "source_evidence_ids" in js
    assert "currentSessionId === '_pending_'" in js
```

- [ ] **Step 2: Run test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_management_center_quality.py -q
```

Expected: PASS.

- [ ] **Step 3: Run related web suites**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_management_center_quality.py tests/test_web_memory_candidates_phase2.py tests/test_web_memory_review_ui_phase2.py tests/test_web_management_ui_phase15.py tests/test_web_overhaul.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add tests/test_mvp_management_center_quality.py src/data_agent/web/blueprints/management.py src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css
git commit -m "Validate management center review workflow"
```

Only include modified source files. If only the test changed, stage only the test.

---

### Task 5: Browser Smoke Validation for Management Center

**Files:**

- Modify: `docs/superpowers/specs/2026-05-25-mvp-quality-results.md`
- Modify source files only if Browser validation exposes a real issue.

- [ ] **Step 1: Start the web app**

Run the project’s existing web command. If no current command is documented, inspect `README.md`, `pyproject.toml`, and app entrypoints before choosing.

Expected: a local URL such as `http://127.0.0.1:5000`.

- [ ] **Step 2: Open Browser and validate management center**

Use the Browser plugin to open the local app.

Validate:

- Management center opens from the sidebar.
- Memory page has `提取当前会话记忆`.
- Memory cards show reason/source/review state when candidates exist.
- Drawer fields are visible and do not overlap on desktop width.
- Source loading failure does not leave stale source content.
- Skill and MCP pages still render after memory UI changes.

- [ ] **Step 3: Record results**

Append to `docs/superpowers/specs/2026-05-25-mvp-quality-results.md`:

```markdown
## Browser Smoke Validation

- Date: 2026-05-25
- Target URL: record the actual local URL used during validation.
- Passed checks: list each checked workflow that worked.
- Issues found: write `None` when no issue was found; otherwise list concrete issue titles.
- Fixes applied: write `None` when no fix was required; otherwise list committed fix summaries.
```

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-05-25-mvp-quality-results.md src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css
git commit -m "Record management center browser validation"
```

Only include modified source files if fixes were required.

---

### Task 6: Final MVP Quality Gate

**Files:**

- Modify: `docs/superpowers/specs/2026-05-25-mvp-quality-results.md`
- Test-only or targeted source fixes if final checks expose a real issue.

- [ ] **Step 1: Run focused MVP suite**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mvp_real_data_fixtures.py tests/test_mvp_memory_quality_real_data.py tests/test_mvp_retrieval_budget_real_data.py tests/test_mvp_management_center_quality.py -q
```

Expected: PASS or SKIP only when `reference/test_doc` is absent.

- [ ] **Step 2: Run Phase 2 regression suite**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_metadata_phase2.py tests/test_memory_candidate_extractor.py tests/test_memory_candidate_auto_extract.py tests/test_retrieval_phase2.py tests/test_retrieval_budget_phase2.py tests/test_web_memory_candidates_phase2.py tests/test_web_memory_review_ui_phase2.py tests/test_knowledge_tools_phase2.py tests/test_memory_candidate_integration_phase2.py -q
```

Expected: PASS.

- [ ] **Step 3: Run related regression suite**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_store.py tests/test_memory_promotion.py tests/test_evidence_store.py tests/test_evidence_auto_index.py tests/test_evidence_kinds.py tests/test_knowledge_retrieval.py tests/test_knowledge_integration.py tests/test_real_data_integration.py tests/test_web_management.py tests/test_web_management_comprehensive.py tests/test_web_management_phase15.py tests/test_web_management_search_phase15.py tests/test_web_management_ui_phase15.py tests/test_web_overhaul.py tests/test_knowledge_tools_phase1.py tests/test_knowledge_tools_phase15.py -q
```

Expected: PASS.

- [ ] **Step 4: Run syntax checks**

Run:

```bash
.\.venv\Scripts\python.exe -m compileall -q src\data_agent
C:\Users\duguy\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe --check src\data_agent\web\static\js\app.js
```

Expected: PASS.

- [ ] **Step 5: Record final results**

Append to `docs/superpowers/specs/2026-05-25-mvp-quality-results.md`:

```markdown
## Final Quality Gate

- MVP fixture suite: record command result and pass/skip count.
- Phase 2 regression suite: record command result and pass count.
- Related regression suite: record command result and pass count.
- Python compile: record exit status.
- JS syntax: record exit status.
- Known warnings: record `.pytest_cache` permission warning when present; otherwise write `None`.
- Accepted residual risks: write `None` when no residual risk remains; otherwise list concrete accepted risks.
```

- [ ] **Step 6: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-05-25-mvp-quality-results.md
git commit -m "Record MVP quality gate results"
```

---

## Completion Criteria

- Real data fixture inventory passes or skips cleanly.
- Ordinary real-data analysis sessions do not create noisy memory candidates.
- Explicit remember/default/correction sessions create traceable candidates.
- Candidate memories remain out of retrieval before confirmation.
- Confirmed memories retrieve under rendered prompt budget limits.
- Evidence remains excluded unless an explicit evidence budget is provided.
- Management center review API and static UI contracts are covered.
- Browser smoke validation results are recorded.
- Focused MVP, Phase 2, related regression, compile, and JS syntax checks pass.
- Any source changes are driven by validation failures, not speculative expansion.
