# Memory Candidate Extraction and Context Budgeting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2 MVP: automatically create reviewable memory candidates from high-signal evidence, keep them traceable and deduplicated, and enforce retrieval context budgets so knowledge and memory do not harm data-analysis quality.

**Architecture:** Extend the existing Evidence -> Memory -> Knowledge loop instead of introducing a larger memory platform. Add deterministic candidate extraction after evidence indexing, review metadata on memory candidates, strict retrieval budgets, and focused management APIs/UI. Candidate memories remain untrusted and never enter prompt retrieval until confirmed.

**Tech Stack:** Python 3, Flask blueprints, SQLite, Markdown knowledge files, Alpine.js management UI, pytest.

---

## Scope Boundary

Read these specs before implementation:

- `docs/superpowers/specs/2026-05-24-memory-candidate-context-budget-design.md`
- `docs/superpowers/specs/2026-05-24-knowledge-memory-usable-target.md`

In scope:

- Fix any remaining Chinese retrieval marker encoding debt before adding more logic.
- Migration-safe memory metadata fields: extraction reason, source evidence IDs, review state, review note, dedup key.
- Rule-first memory candidate extraction from indexed evidence.
- Deduplication by stable key.
- Best-effort auto extraction after session evidence indexing.
- Strict context budgets for knowledge, memory, and evidence retrieval.
- Management API and UI support for candidate review metadata and manual extraction.
- Tests with Chinese metric definitions, corrections, preferences, and ordinary non-memory conversations.

Out of scope:

- Persona system.
- Vector database as the primary retrieval layer.
- Automatic formal knowledge creation.
- Automatic Skill generation.
- Complex conflict resolution with `ask_user_question`.
- Full knowledge version diff UI.
- Knowledge graph UI.

---

## File Structure

- Modify `src/data_agent/knowledge/retrieval.py`: normalize Chinese retrieval/conflict markers and enforce context budgets.
- Modify `src/data_agent/knowledge/models.py`: add review metadata fields to `MemoryItem`.
- Modify `src/data_agent/knowledge/sqlite_store.py`: add migration-safe memory metadata columns and indexes.
- Modify `src/data_agent/knowledge/memory.py`: persist metadata, support filtering, deduplication, update, and serialization.
- Create `src/data_agent/knowledge/candidates.py`: implement deterministic candidate extraction and result dataclasses.
- Modify `src/data_agent/knowledge/evidence.py`: trigger candidate extraction after successful session indexing.
- Modify `src/data_agent/web/blueprints/management.py`: add extraction endpoint, source lookup endpoint, and memory filters.
- Modify `src/data_agent/web/templates/index.html`: expose candidate reason/source/review controls.
- Modify `src/data_agent/web/static/js/app.js`: wire extraction, source lookup, review metadata, and filters.
- Modify `src/data_agent/web/static/css/app.css`: style review badges and source summaries consistently with the management center.
- Modify `src/data_agent/tools/knowledge_tools.py`: add small CLI/agent tools for candidate extraction and listing.
- Add focused tests under `tests/`.

---

### Task 1: Normalize Chinese Retrieval Markers

**Files:**

- Modify: `src/data_agent/knowledge/retrieval.py`
- Test: `tests/test_retrieval_phase2.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_retrieval_phase2.py`:

```python
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.retrieval import KnowledgeRetrievalService, _cjk_bigrams, _query_terms


def test_query_terms_extract_chinese_metric_words():
    terms = _query_terms("帮我分析一下这个数据，我需要知道留存率和付费转化率的关系")

    assert "留存率" in terms
    assert "付费转化率" in terms


def test_cjk_bigrams_uses_real_chinese_range():
    grams = _cjk_bigrams("排除退款订单")

    assert "排除" in grams
    assert "退款" in grams


def test_chinese_conflict_detection_uses_real_markers(tmp_path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    memory = MemoryStore(tmp_path / "knowledge")
    library.create(
        title="GMV 口径",
        domain="ecommerce",
        content="GMV 排除取消订单。",
        summary="GMV 排除取消订单",
    )
    item = memory.create_candidate(
        text="GMV 包含所有订单。",
        summary="GMV 包含所有订单",
        memory_type="domain_fact",
        domain="ecommerce",
        confidence=0.8,
    )
    memory.confirm(item.id)

    context = KnowledgeRetrievalService(root=tmp_path / "knowledge").retrieve("GMV 口径", domain="ecommerce")

    assert context.conflicts
    assert context.conflicts[0].severity.value == "review"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_phase2.py -q
```

Expected: FAIL if retrieval still contains mojibake markers or incomplete CJK tokenization.

- [ ] **Step 3: Replace mojibake strings with real UTF-8 Chinese**

In `src/data_agent/knowledge/retrieval.py`, ensure `_query_terms()` uses real stopwords:

```python
stopwords = {
    "帮我", "分析", "一下", "这个", "数据",
    "需要", "知道", "关系", "如何", "什么",
}
```

Ensure `_cjk_bigrams()` uses:

```python
chars = re.findall(r"[\u4e00-\u9fff]", text)
```

Ensure conflict markers include:

```python
negative_markers = (
    " exclude", " excludes", " excluding", " not ",
    "排除", "不包含", "不含", "不包括",
)
inclusive_markers = (
    " include", " includes", " including", " all ",
    "包含", "包括", "全部", "所有",
)
```

- [ ] **Step 4: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_phase2.py tests/test_retrieval_phase15.py tests/test_knowledge_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/knowledge/retrieval.py tests/test_retrieval_phase2.py
git commit -m "Normalize Chinese retrieval markers"
```

---

### Task 2: Add Memory Review Metadata Schema

**Files:**

- Modify: `src/data_agent/knowledge/models.py`
- Modify: `src/data_agent/knowledge/sqlite_store.py`
- Modify: `src/data_agent/knowledge/memory.py`
- Test: `tests/test_memory_metadata_phase2.py`

- [ ] **Step 1: Write failing persistence tests**

Create `tests/test_memory_metadata_phase2.py`:

```python
from data_agent.knowledge.memory import MemoryStore


def test_memory_candidate_persists_review_metadata(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")

    item = store.create_candidate(
        text="GMV should exclude canceled orders.",
        summary="GMV rule",
        memory_type="domain_fact",
        domain="ecommerce",
        reason="User stated an explicit metric rule.",
        source_evidence_ids=["ev_s1_0"],
        needs_review=True,
        review_note="Possible conflict with older GMV rule.",
        dedup_key="domain_fact:ecommerce:gmv:exclude:canceled",
    )

    loaded = store.get(item.id)

    assert loaded.reason == "User stated an explicit metric rule."
    assert loaded.source_evidence_ids == ["ev_s1_0"]
    assert loaded.needs_review is True
    assert loaded.review_note == "Possible conflict with older GMV rule."
    assert loaded.dedup_key == "domain_fact:ecommerce:gmv:exclude:canceled"


def test_memory_list_filters_needs_review(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    store.create_candidate("A", needs_review=True, dedup_key="a")
    store.create_candidate("B", needs_review=False, dedup_key="b")

    items = store.list(needs_review=True)

    assert [item.text for item in items] == ["A"]


def test_create_candidate_reuses_duplicate_dedup_key(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    first = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")
    second = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")

    assert second.id == first.id
    assert len(store.list()) == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_metadata_phase2.py -q
```

Expected: FAIL because metadata fields do not exist.

- [ ] **Step 3: Extend `MemoryItem`**

Add these fields:

```python
reason: str = ""
source_evidence_ids: list[str] = field(default_factory=list)
needs_review: bool = False
review_note: str = ""
dedup_key: str = ""
```

- [ ] **Step 4: Add migration-safe SQLite columns**

Update fresh schema for `memory_items` and add an idempotent migration method:

```python
def _migrate(self, conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(memory_items)").fetchall()}
    columns = {
        "reason": "TEXT NOT NULL DEFAULT ''",
        "source_evidence_ids": "TEXT NOT NULL DEFAULT '[]'",
        "needs_review": "INTEGER NOT NULL DEFAULT 0",
        "review_note": "TEXT NOT NULL DEFAULT ''",
        "dedup_key": "TEXT NOT NULL DEFAULT ''",
    }
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE memory_items ADD COLUMN {name} {ddl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_dedup_key ON memory_items(dedup_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_needs_review ON memory_items(needs_review)")
```

Call `_migrate(conn)` after `SCHEMA` initialization.

- [ ] **Step 5: Update `MemoryStore`**

Extend `create_candidate()` with:

```python
reason: str = "",
source_evidence_ids: list[str] | None = None,
needs_review: bool = False,
review_note: str = "",
dedup_key: str = "",
```

Add `get_by_dedup_key()`:

```python
def get_by_dedup_key(self, dedup_key: str) -> MemoryItem | None:
    if not dedup_key:
        return None
    with self.db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM memory_items WHERE dedup_key = ? ORDER BY updated_at DESC LIMIT 1",
            (dedup_key,),
        ).fetchone()
    return self._item_from_row(dict(row)) if row else None
```

If `dedup_key` exists, return the existing item before inserting. Update `list()`, `update()`, and `_item_from_row()` to carry all new fields.

- [ ] **Step 6: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_metadata_phase2.py tests/test_memory_store.py tests/test_memory_promotion.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/data_agent/knowledge/models.py src/data_agent/knowledge/sqlite_store.py src/data_agent/knowledge/memory.py tests/test_memory_metadata_phase2.py
git commit -m "Add memory review metadata"
```

---

### Task 3: Implement Rule-Based Memory Candidate Extractor

**Files:**

- Create: `src/data_agent/knowledge/candidates.py`
- Test: `tests/test_memory_candidate_extractor.py`

- [ ] **Step 1: Write failing extractor tests**

Create `tests/test_memory_candidate_extractor.py`:

```python
import json

from data_agent.knowledge.candidates import MemoryCandidateExtractor
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.memory import MemoryStore


def _write_session(sessions_dir, session_id, content, project_name="ecommerce"):
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": project_name, "saved_at": "2026-05-24T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": content}], ensure_ascii=False),
        encoding="utf-8",
    )


def test_extractor_creates_metric_definition_candidate(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s1", "请记住：GMV 口径 = 支付金额 - 取消订单 - 退款订单。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s1")

    result = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir).extract_for_session("s1")

    assert result.created == 1
    item = MemoryStore(root).list()[0]
    assert item.status.value == "candidate"
    assert item.type.value == "domain_fact"
    assert item.reason
    assert item.source_evidence_ids
    assert item.dedup_key


def test_extractor_ignores_ordinary_conversation(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s2", "你好，帮我看一下这个文件。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s2")

    result = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir).extract_for_session("s2")

    assert result.created == 0
    assert MemoryStore(root).list() == []


def test_extractor_deduplicates_repeated_runs(tmp_path):
    sessions_dir = tmp_path / "sessions"
    _write_session(sessions_dir, "s3", "以后默认先做缺失值检查，再做趋势分析。")
    root = tmp_path / "knowledge"
    EvidenceStore(root, sessions_dir=sessions_dir).index_session("s3")
    extractor = MemoryCandidateExtractor(root=root, sessions_dir=sessions_dir)

    first = extractor.extract_for_session("s3")
    second = extractor.extract_for_session("s3")

    assert first.created == 1
    assert second.created == 0
    assert len(MemoryStore(root).list()) == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_candidate_extractor.py -q
```

Expected: FAIL because `candidates.py` does not exist.

- [ ] **Step 3: Add dataclasses**

Create `src/data_agent/knowledge/candidates.py` with:

```python
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from data_agent.config import get_config
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import EvidenceRecord, MemoryType


@dataclass(frozen=True)
class CandidateDraft:
    text: str
    summary: str
    memory_type: MemoryType
    confidence: float
    domain: str
    tags: list[str]
    reason: str
    source_evidence_ids: list[str]
    needs_review: bool = False
    review_note: str = ""
    dedup_key: str = ""


@dataclass
class CandidateExtractionResult:
    scanned: int = 0
    created: int = 0
    skipped: int = 0
    candidates: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Implement extraction rules**

Add `MemoryCandidateExtractor`:

```python
class MemoryCandidateExtractor:
    def __init__(self, root: Path | None = None, sessions_dir: Path | None = None):
        self.root = root or get_config().knowledge_dir
        self.evidence = EvidenceStore(self.root, sessions_dir=sessions_dir)
        self.memory = MemoryStore(self.root)

    def extract_for_session(self, session_id: str, max_candidates: int = 10) -> CandidateExtractionResult:
        records = self._records_for_session(session_id)
        result = CandidateExtractionResult(scanned=len(records))
        for record in records:
            for draft in self._drafts_from_record(record):
                if result.created >= max_candidates or self.memory.get_by_dedup_key(draft.dedup_key):
                    result.skipped += 1
                    continue
                item = self.memory.create_candidate(
                    text=draft.text,
                    summary=draft.summary,
                    memory_type=draft.memory_type,
                    confidence=draft.confidence,
                    source_session_id=record.session_id,
                    project_id=record.project_id,
                    domain=draft.domain,
                    tags=draft.tags,
                    reason=draft.reason,
                    source_evidence_ids=draft.source_evidence_ids,
                    needs_review=draft.needs_review,
                    review_note=draft.review_note,
                    dedup_key=draft.dedup_key,
                )
                result.created += 1
                result.candidates.append(item.id)
        return result
```

Implement `_records_for_session()` with a direct SQLite query on `evidence_records`.

Implement `_drafts_from_record()` using these high-signal markers only:

```python
MEMORY_MARKERS = ("请记住", "记住", "以后默认", "下次", "默认", "remember", "default", "next time")
CORRECTION_MARKERS = ("纠正", "更正", "不是", "应该是", "修正", "correction", "correct")
METRIC_MARKERS = ("口径", "定义", "公式", "指标", "=", "等于")
```

Classification:

- content with metric markers -> `MemoryType.DOMAIN_FACT`
- content with correction markers -> `MemoryType.DOMAIN_FACT`, `needs_review=True`
- content with memory/default markers -> `MemoryType.PREFERENCE`
- content mentioning workflow sequence such as `先...再...` -> `MemoryType.WORKFLOW`

Generate dedup keys with normalized text:

```python
def _dedup_key(self, memory_type: MemoryType, domain: str, text: str) -> str:
    normalized = re.sub(r"\s+", "", text.lower())
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{memory_type.value}:{domain or 'general'}:{digest}"
```

- [ ] **Step 5: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_candidate_extractor.py tests/test_memory_metadata_phase2.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/knowledge/candidates.py tests/test_memory_candidate_extractor.py
git commit -m "Add memory candidate extractor"
```

---

### Task 4: Auto Extract Candidates After Evidence Indexing

**Files:**

- Modify: `src/data_agent/knowledge/evidence.py`
- Test: `tests/test_memory_candidate_auto_extract.py`

- [ ] **Step 1: Write failing auto-extraction tests**

Create `tests/test_memory_candidate_auto_extract.py`:

```python
import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.session.history import save_session


def test_save_session_auto_extracts_high_signal_candidate(tmp_path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)

    save_session(
        [{"role": "user", "content": "请记住：GMV 需要排除取消订单和退款订单。"}],
        "auto_candidate",
        extra_meta={"project_name": "ecommerce"},
    )

    candidates = MemoryStore(cfg.knowledge_dir).list(status="candidate")

    assert len(candidates) == 1
    assert candidates[0].source_evidence_ids


def test_save_session_does_not_create_candidate_for_ordinary_chat(tmp_path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)

    save_session([{"role": "user", "content": "帮我分析这个 CSV 文件。"}], "ordinary")

    assert MemoryStore(cfg.knowledge_dir).list(status="candidate") == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_candidate_auto_extract.py -q
```

Expected: FAIL because evidence indexing does not extract candidates.

- [ ] **Step 3: Add best-effort extraction hook**

In `EvidenceStore.index_session()`, after records are indexed successfully, call a private hook:

```python
def _try_extract_memory_candidates(self, session_id: str) -> None:
    try:
        from data_agent.knowledge.candidates import MemoryCandidateExtractor

        MemoryCandidateExtractor(root=self.root, sessions_dir=self.sessions_dir).extract_for_session(session_id)
    except Exception:
        return
```

Call it only after a successful index operation. Do not let extraction failure break evidence indexing or `save_session()`.

- [ ] **Step 4: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_candidate_auto_extract.py tests/test_evidence_auto_index.py tests/test_evidence_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/knowledge/evidence.py tests/test_memory_candidate_auto_extract.py
git commit -m "Extract memory candidates after evidence indexing"
```

---

### Task 5: Enforce Retrieval Context Budgets

**Files:**

- Modify: `src/data_agent/knowledge/retrieval.py`
- Test: `tests/test_retrieval_budget_phase2.py`

- [ ] **Step 1: Write failing budget tests**

Create `tests/test_retrieval_budget_phase2.py`:

```python
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.retrieval import KnowledgeRetrievalService


def test_retrieval_enforces_total_context_budget(tmp_path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)
    for idx in range(6):
        library.create(
            title=f"GMV rule {idx}",
            domain="ecommerce",
            content="GMV " + ("very long rule " * 200),
            summary="GMV long rule",
            tags=["gmv"],
        )

    context = KnowledgeRetrievalService(root=root).retrieve(
        "GMV rule",
        domain="ecommerce",
        knowledge_limit=6,
        max_total_retrieval_chars=1200,
    )

    assert context.metadata["trimmed"] is True
    assert context.metadata["total_retrieval_chars"] <= 1200
    assert len(context.knowledge_items) < 6


def test_candidate_memory_not_retrieved_before_confirmation(tmp_path):
    root = tmp_path / "knowledge"
    MemoryStore(root).create_candidate("Always use GMV.", domain="ecommerce", dedup_key="pref:gmv")

    context = KnowledgeRetrievalService(root=root).retrieve("GMV", domain="ecommerce")

    assert context.memory_items == []


def test_budget_metadata_exists_for_empty_retrieval(tmp_path):
    context = KnowledgeRetrievalService(root=tmp_path / "knowledge").retrieve("nothing")

    assert context.metadata["knowledge_chars"] == 0
    assert context.metadata["memory_chars"] == 0
    assert context.metadata["evidence_chars"] == 0
    assert context.metadata["total_retrieval_chars"] == 0
    assert context.metadata["trimmed"] is False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_budget_phase2.py -q
```

Expected: FAIL because budget kwargs and trimming do not exist.

- [ ] **Step 3: Add budget constants and helpers**

Add:

```python
DEFAULT_MAX_KNOWLEDGE_CHARS = 1800
DEFAULT_MAX_MEMORY_CHARS = 720
DEFAULT_MAX_EVIDENCE_CHARS = 0
DEFAULT_MAX_TOTAL_RETRIEVAL_CHARS = 2600
```

Add:

```python
def _item_text_length(item: object) -> int:
    if isinstance(item, KnowledgeItem):
        return len(item.title) + len(item.summary) + len(item.content)
    if isinstance(item, MemoryItem):
        return len(item.summary) + len(item.text)
    if isinstance(item, EvidenceRecord):
        return len(item.summary) + len(item.content)
    return 0


def _trim_items_to_budget(items: list, max_chars: int) -> tuple[list, int, bool]:
    if max_chars <= 0:
        return [], 0, bool(items)
    kept = []
    used = 0
    trimmed = False
    for item in items:
        size = _item_text_length(item)
        if used + size > max_chars:
            trimmed = True
            continue
        kept.append(item)
        used += size
    return kept, used, trimmed
```

- [ ] **Step 4: Extend `retrieve()` signature**

Add keyword-only parameters:

```python
max_knowledge_chars: int = DEFAULT_MAX_KNOWLEDGE_CHARS,
max_memory_chars: int = DEFAULT_MAX_MEMORY_CHARS,
max_evidence_chars: int = DEFAULT_MAX_EVIDENCE_CHARS,
max_total_retrieval_chars: int = DEFAULT_MAX_TOTAL_RETRIEVAL_CHARS,
```

Apply per-kind budgets first, then enforce total budget by dropping items in this order:

1. evidence
2. memory
3. knowledge

Store post-trim values in metadata:

```python
"knowledge_chars": knowledge_chars,
"memory_chars": memory_chars,
"evidence_chars": evidence_chars,
"total_retrieval_chars": total,
"trimmed": trimmed,
"trim_reason": "retrieval_context_budget" if trimmed else "",
```

- [ ] **Step 5: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_budget_phase2.py tests/test_retrieval_phase2.py tests/test_knowledge_retrieval.py tests/test_knowledge_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/knowledge/retrieval.py tests/test_retrieval_budget_phase2.py
git commit -m "Enforce retrieval context budgets"
```

---

### Task 6: Add Management APIs for Candidate Review

**Files:**

- Modify: `src/data_agent/web/blueprints/management.py`
- Test: `tests/test_web_memory_candidates_phase2.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_web_memory_candidates_phase2.py`:

```python
import json

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.web.app import create_app


def _client(tmp_path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    return create_app().test_client(), cfg


def test_management_extract_memory_candidates(tmp_path, monkeypatch):
    client, cfg = _client(tmp_path, monkeypatch)
    session_dir = cfg.sessions_resolved / "s1"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "ecommerce", "saved_at": "2026-05-24T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": "请记住：GMV 需要排除取消订单。"}], ensure_ascii=False),
        encoding="utf-8",
    )
    client.post("/api/management/evidence/index", json={"session_id": "s1"})

    resp = client.post("/api/management/memory/extract", json={"session_id": "s1"})

    assert resp.status_code == 200
    assert resp.get_json()["created"] >= 0
    candidates = client.get("/api/management/memory?status=candidate").get_json()
    assert candidates
    assert candidates[0]["reason"]
    assert candidates[0]["source_evidence_ids"]


def test_management_memory_needs_review_filter_and_sources(tmp_path, monkeypatch):
    client, _cfg = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/management/memory",
        json={
            "text": "GMV includes all orders.",
            "reason": "test",
            "source_evidence_ids": ["ev_missing"],
            "needs_review": True,
        },
    )
    memory_id = created.get_json()["id"]

    filtered = client.get("/api/management/memory?needs_review=true")
    sources = client.get(f"/api/management/memory/{memory_id}/sources")

    assert filtered.status_code == 200
    assert filtered.get_json()[0]["id"] == memory_id
    assert sources.status_code == 200
    assert sources.get_json()["memory_id"] == memory_id
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_web_memory_candidates_phase2.py -q
```

Expected: FAIL because APIs/serialization are missing.

- [ ] **Step 3: Extend serialization and memory create/update/list**

Add these fields to `_memory_to_dict()`:

```python
"reason": item.reason,
"source_evidence_ids": item.source_evidence_ids,
"needs_review": item.needs_review,
"review_note": item.review_note,
"dedup_key": item.dedup_key,
```

Pass the same fields through create and update endpoints. Parse `needs_review` in list requests and pass it to `MemoryStore().list(...)`.

- [ ] **Step 4: Add extraction and source endpoints**

Add:

```python
@management_bp.post("/management/memory/extract")
def extract_memory_candidates():
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    from data_agent.knowledge.candidates import MemoryCandidateExtractor

    result = MemoryCandidateExtractor().extract_for_session(session_id)
    return jsonify({
        "scanned": result.scanned,
        "created": result.created,
        "skipped": result.skipped,
        "candidates": result.candidates,
    })


@management_bp.get("/management/memory/<memory_id>/sources")
def memory_sources(memory_id: str):
    memory = MemoryStore().get(memory_id)
    if memory is None:
        return jsonify({"error": "memory not found"}), 404
    evidence = EvidenceStore()
    sources = []
    for evidence_id in memory.source_evidence_ids:
        record = evidence.get(evidence_id)
        if record:
            sources.append(_evidence_to_dict(record))
    return jsonify({"memory_id": memory_id, "sources": sources})
```

- [ ] **Step 5: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_web_memory_candidates_phase2.py tests/test_web_management_phase15.py tests/test_web_management_search_phase15.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/web/blueprints/management.py tests/test_web_memory_candidates_phase2.py
git commit -m "Add memory candidate management APIs"
```

---

### Task 7: Enhance Management Center Review UI

**Files:**

- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/static/css/app.css`
- Test: `tests/test_web_memory_review_ui_phase2.py`

- [ ] **Step 1: Write failing UI tests**

Create `tests/test_web_memory_review_ui_phase2.py`:

```python
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
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_web_memory_review_ui_phase2.py -q
```

Expected: FAIL because UI fields/actions are not present.

- [ ] **Step 3: Add visible review controls**

In the memory management view, add:

- A `提取当前会话记忆` button that calls `extractMemoryCandidates()`.
- A `需要审核` badge when `item.needs_review` is true.
- `提取原因` and `来源证据` rows in memory cards.
- A `查看来源` action that calls `loadMemorySources(item)`.
- Drawer fields for `reason`, `review_note`, `needs_review`, and `dedup_key`.

- [ ] **Step 4: Wire JS methods**

Add methods:

```javascript
async extractMemoryCandidates() {
    if (!this.currentSessionId) {
        this.showToast('请先打开一个会话');
        return;
    }
    const res = await fetch('/api/management/memory/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: this.currentSessionId }),
    });
    if (!res.ok) {
        this.showToast('记忆提取失败');
        return;
    }
    const data = await res.json();
    this.showToast(`已创建 ${data.created || 0} 条候选记忆`);
    await this.loadManagementSection('memory');
}

async loadMemorySources(item) {
    const res = await fetch(`/api/management/memory/${encodeURIComponent(item.id)}/sources`);
    this.managementCenter.memorySources = res.ok ? await res.json() : { sources: [] };
    const count = (this.managementCenter.memorySources.sources || []).length;
    this.showToast(`来源证据 ${count} 条`);
}
```

Ensure create/update memory payloads include:

```javascript
reason: form.reason || '',
source_evidence_ids: form.source_evidence_ids || [],
needs_review: !!form.needs_review,
review_note: form.review_note || '',
dedup_key: form.dedup_key || '',
```

- [ ] **Step 5: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_web_memory_review_ui_phase2.py tests/test_web_management_ui_phase15.py tests/test_web_overhaul.py -q
C:\Users\duguy\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe --check src\data_agent\web\static\js\app.js
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css tests/test_web_memory_review_ui_phase2.py
git commit -m "Enhance memory review UI"
```

---

### Task 8: Add Candidate Tools for CLI/Agent Operations

**Files:**

- Modify: `src/data_agent/tools/knowledge_tools.py`
- Test: `tests/test_knowledge_tools_phase2.py`

- [ ] **Step 1: Write failing tool tests**

Create `tests/test_knowledge_tools_phase2.py`:

```python
import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.tools import knowledge_tools
from data_agent.tools.registry import registry


def test_memory_candidate_tools_are_registered():
    names = set(registry.tool_names)

    assert "extract_memory_candidates" in names
    assert "list_memory_candidates" in names


def test_list_memory_candidates_returns_only_candidates(tmp_path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)
    knowledge_tools.reset_knowledge_services_for_tests()

    knowledge_tools.create_memory_candidate("candidate memory", domain="general")
    result = knowledge_tools.list_memory_candidates()

    assert result
    assert result[0]["status"] == "candidate"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_tools_phase2.py -q
```

Expected: FAIL because tools do not exist.

- [ ] **Step 3: Add tools**

Add:

```python
@registry.register(
    name="extract_memory_candidates",
    description="Extract reviewable memory candidates from a saved session. Candidates are not used until confirmed.",
)
def extract_memory_candidates(session_id: str = "") -> dict:
    from data_agent.knowledge.candidates import MemoryCandidateExtractor

    sid = session_id or get_active_session_id() or ""
    if not sid:
        return {"error": "session_id is required"}
    result = MemoryCandidateExtractor().extract_for_session(sid)
    return {
        "scanned": result.scanned,
        "created": result.created,
        "skipped": result.skipped,
        "candidates": result.candidates,
    }


@registry.register(
    name="list_memory_candidates",
    description="List reviewable memory candidates. Candidates are not trusted until confirmed.",
)
def list_memory_candidates(needs_review: bool = False) -> list[dict]:
    return [
        _memory_to_dict(item)
        for item in _memory().list(status="candidate", needs_review=True if needs_review else None)
    ]
```

Extend `_memory_to_dict()` with the new review metadata fields.

- [ ] **Step 4: Run verification**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_tools_phase2.py tests/test_knowledge_tools_phase1.py tests/test_knowledge_tools_phase15.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/tools/knowledge_tools.py tests/test_knowledge_tools_phase2.py
git commit -m "Add memory candidate tools"
```

---

### Task 9: Integration and Real Data Regression

**Files:**

- Add: `tests/test_memory_candidate_integration_phase2.py`

- [ ] **Step 1: Write end-to-end integration test**

Create `tests/test_memory_candidate_integration_phase2.py`:

```python
from pathlib import Path

import data_agent.config as config_module
from data_agent.config import AgentConfig
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.retrieval import KnowledgeRetrievalService
from data_agent.session.history import save_session


def test_candidate_to_confirmed_retrieval_flow_with_budget(tmp_path: Path, monkeypatch):
    cfg = AgentConfig(WORKSPACE_DIR=tmp_path / "workspace", SESSIONS_DIR=tmp_path / "sessions")
    monkeypatch.setattr(config_module, "_config", cfg)

    save_session(
        [{"role": "user", "content": "请记住：GMV 需要排除取消订单和退款订单。"}],
        "phase2_flow",
        extra_meta={"project_name": "ecommerce"},
    )

    store = MemoryStore(cfg.knowledge_dir)
    candidates = store.list(status="candidate")
    assert candidates

    before = KnowledgeRetrievalService().retrieve("GMV 如何计算", domain="ecommerce")
    assert before.memory_items == []

    store.confirm(candidates[0].id)
    after = KnowledgeRetrievalService().retrieve(
        "GMV 如何计算",
        domain="ecommerce",
        max_total_retrieval_chars=1200,
    )

    assert after.memory_items
    assert after.metadata["total_retrieval_chars"] <= 1200
```

- [ ] **Step 2: Run focused Phase 2 suite**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_memory_metadata_phase2.py tests/test_memory_candidate_extractor.py tests/test_memory_candidate_auto_extract.py tests/test_retrieval_phase2.py tests/test_retrieval_budget_phase2.py tests/test_web_memory_candidates_phase2.py tests/test_web_memory_review_ui_phase2.py tests/test_knowledge_tools_phase2.py tests/test_memory_candidate_integration_phase2.py -q
```

Expected: PASS.

- [ ] **Step 3: Run related regression suites**

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

- [ ] **Step 5: Commit integration test or final fixes**

Run:

```bash
git add tests/test_memory_candidate_integration_phase2.py
git commit -m "Verify memory candidate extraction flow"
```

If no files changed after verification, no final commit is needed.

---

## Completion Criteria

- Explicit memory/correction/metric-definition sessions create candidate memories.
- Ordinary sessions do not create noisy memory candidates.
- Candidate memories include reason, source evidence IDs, dedup key, and review metadata.
- Repeated extraction is idempotent.
- Candidate memories never appear in prompt retrieval.
- Confirmed memories continue to retrieve normally.
- Retrieval context budget metadata is present and trimming is enforced.
- Management API can extract candidates and fetch source evidence.
- Management UI shows reason/source/review state and can trigger extraction.
- Evidence and memory failures never break session saving or the analysis flow.
- Focused backend, web, integration, compile, and JS syntax checks pass.
