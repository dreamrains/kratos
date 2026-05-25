# Knowledge Memory Closed Loop Phase 1.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 1 knowledge and memory foundation into an end-to-end usable loop: session evidence is indexed automatically, memory can be reviewed and promoted into formal knowledge, retrieval uses domain-aware context, and the management center exposes the missing review operations.

**Architecture:** Keep the existing separation between Formal Knowledge, Memory Inbox, and Session Evidence. Add narrow store methods and web/tool endpoints around those boundaries instead of creating a new orchestration layer. Prefer traceable soft lifecycle changes for reviewed items, and reserve hard delete for candidate or explicitly user-deleted records.

**Tech Stack:** Python 3, Flask blueprints, SQLite, Markdown knowledge files, Alpine.js management UI, pytest.

---

## Scope Guard

This plan is Phase 1.5 hardening, not the full Phase 2 self-learning system.

In scope:
- Remove or hide old domain/experience tools from agent-facing tool selection.
- Auto-index saved sessions into Evidence Store.
- Extend Evidence indexing beyond plain messages where structured data already exists.
- Add Memory edit/delete/promote-to-knowledge behavior.
- Improve retrieval domain/query handling and reuse retrieval service per AgentLoop.
- Add management center UI/API for the new closed-loop operations.
- Add UTF-8 and Chinese regression tests for the management center and retrieval.

Out of scope:
- LLM-based automatic memory extraction.
- Embeddings/vector database.
- Full knowledge version diff UI.
- Skill auto-generation from repeated workflows.
- Advanced conflict adjudication with ask_user_question.

---

## File Structure

- Modify `src/data_agent/knowledge/sqlite_store.py`: connection pragmas for WAL, busy timeout, and foreign-key readiness.
- Modify `src/data_agent/knowledge/evidence.py`: robust UTF-8 reading, automatic index helper, multi-kind evidence extraction from session messages and analysis state artifacts.
- Modify `src/data_agent/session/history.py`: call evidence indexing after successful `save_session`.
- Modify `src/data_agent/knowledge/memory.py`: update, soft delete/reject/delete candidate, and promote-to-knowledge methods.
- Modify `src/data_agent/knowledge/library.py`: create knowledge from promoted memory with source metadata and optional domain helpers.
- Modify `src/data_agent/knowledge/retrieval.py`: query normalization, Chinese-friendly token extraction, domain-aware fallback retrieval.
- Modify `src/data_agent/agent/loop.py`: reuse `KnowledgeRetrievalService`, infer domain, remove unused old domain/experience variables.
- Modify `src/data_agent/tools/knowledge_tools.py`: remove old domain/experience tools from active registration or make them non-agent-facing deprecated helpers.
- Modify `src/data_agent/tools/registry.py`: remove old tools from agent-relevant tool groups.
- Modify `src/data_agent/web/blueprints/management.py`: memory update/delete/promote APIs, evidence index endpoint, global search endpoint, domain list endpoint.
- Modify `src/data_agent/web/templates/index.html`: add management controls for memory edit/delete/promote, evidence reindex, domain picker, global search.
- Modify `src/data_agent/web/static/js/app.js`: wire new management actions and client validation.
- Modify `src/data_agent/web/static/css/app.css`: keep new states visually consistent with home page.
- Add/modify tests under `tests/`: focused backend tests first, then web API/UI smoke tests.

---

### Task 1: SQLite Reliability Baseline

**Files:**
- Modify: `src/data_agent/knowledge/sqlite_store.py`
- Test: `tests/test_knowledge_database.py`

- [ ] **Step 1: Write failing tests for SQLite pragmas**

Create `tests/test_knowledge_database.py`:

```python
from data_agent.knowledge.sqlite_store import KnowledgeDatabase


def test_knowledge_database_sets_wal_and_busy_timeout(tmp_path):
    db = KnowledgeDatabase(tmp_path / "knowledge.sqlite3")

    with db.connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert busy_timeout >= 5000
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_knowledge_database.py -q`

Expected: FAIL because `busy_timeout` is currently the SQLite default and WAL is not set by `connect()`.

- [ ] **Step 3: Implement connection pragmas**

Update `KnowledgeDatabase.connect()`:

```python
def connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

Update `initialize()` to use `self.connect()` so initialization receives the same pragmas.

- [ ] **Step 4: Run verification**

Run: `pytest tests/test_knowledge_database.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/knowledge/sqlite_store.py tests/test_knowledge_database.py
git commit -m "Harden knowledge sqlite connections"
```

---

### Task 2: Retire Old Domain and Experience Agent Tools

**Files:**
- Modify: `src/data_agent/tools/knowledge_tools.py`
- Modify: `src/data_agent/tools/registry.py`
- Modify: `src/data_agent/agent/loop.py`
- Test: `tests/test_knowledge_tools_phase15.py`

- [ ] **Step 1: Write failing tests for active tool surface**

Create `tests/test_knowledge_tools_phase15.py`:

```python
from data_agent.tools.registry import registry


def test_old_domain_experience_tools_are_not_agent_facing():
    names = set(registry.tool_names)

    assert "search_knowledge" in names
    assert "create_memory_candidate" in names
    assert "show_domain_knowledge" not in names
    assert "set_domain" not in names
    assert "show_experience_log" not in names
    assert "confirm_experience" not in names
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_knowledge_tools_phase15.py -q`

Expected: FAIL because old tools are still registered or still present in registry groups.

- [ ] **Step 3: Remove old tools from agent-facing registration**

In `src/data_agent/tools/knowledge_tools.py`, remove or comment out the `@tool(...)` decorators for:

```python
show_domain_knowledge
set_domain
show_experience_log
confirm_experience
```

Keep plain helper functions only if existing code still imports them. Add docstrings that say they are legacy helpers and not agent-facing tools.

In `src/data_agent/tools/registry.py`, remove these names from capability groups and any built-in allowlists:

```python
"set_domain"
"confirm_experience"
"show_domain_knowledge"
"show_experience_log"
```

In `src/data_agent/agent/loop.py`, replace:

```python
project_rules, _domain_knowledge, _experience_log = get_knowledge_instances()
```

with:

```python
project_rules, _, _ = get_knowledge_instances()
```

If `get_knowledge_instances()` is only needed for project rules, prefer a small follow-up helper in `knowledge_tools.py`:

```python
def get_project_rules_instance():
    return _project_rules
```

Then use that helper in `loop.py`.

- [ ] **Step 4: Run verification**

Run:

```bash
pytest tests/test_knowledge_tools_phase15.py tests/test_knowledge_tools_phase1.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/tools/knowledge_tools.py src/data_agent/tools/registry.py src/data_agent/agent/loop.py tests/test_knowledge_tools_phase15.py
git commit -m "Retire legacy knowledge tools from agent surface"
```

---

### Task 3: Auto-Index Session Evidence

**Files:**
- Modify: `src/data_agent/knowledge/evidence.py`
- Modify: `src/data_agent/session/history.py`
- Test: `tests/test_evidence_auto_index.py`

- [ ] **Step 1: Write failing test for automatic indexing after save_session**

Create `tests/test_evidence_auto_index.py`:

```python
from data_agent.config import get_config
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.session.history import save_session


def test_save_session_indexes_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_AGENT_HOME", str(tmp_path))
    cfg = get_config()
    session_id = "auto_index_cn"

    save_session(
        [
            {"role": "user", "content": "请记住 GMV 需要排除取消订单"},
            {"role": "assistant", "content": "已确认该业务口径。"},
        ],
        session_id,
        project_name="ecommerce",
    )

    records = EvidenceStore(cfg.knowledge_dir, sessions_dir=cfg.sessions_resolved).search(
        "GMV",
        project_id="ecommerce",
    )

    assert len(records) >= 1
    assert records[0].session_id == session_id
    assert "GMV" in records[0].content
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_evidence_auto_index.py -q`

Expected: FAIL because `save_session()` does not call `EvidenceStore.index_session()`.

- [ ] **Step 3: Add safe indexing hook after save_session writes files**

In `src/data_agent/session/history.py`, after `conversation.json` and `meta.json` are successfully written, add:

```python
def _try_index_session_evidence(session_id: str) -> None:
    try:
        from data_agent.knowledge.evidence import EvidenceStore

        EvidenceStore().index_session(session_id)
    except Exception:
        return
```

Call it at the end of `save_session()` after the JSONL file is cleared:

```python
_try_index_session_evidence(session_id)
```

Do not let indexing failure break session persistence.

- [ ] **Step 4: Harden JSON readers for UTF-8 BOM**

In `EvidenceStore._read_json()`, change:

```python
return json.loads(path.read_text(encoding="utf-8"))
```

to:

```python
return json.loads(path.read_text(encoding="utf-8-sig"))
```

In `_read_messages()`, read JSONL with `encoding="utf-8-sig"` as well.

- [ ] **Step 5: Run verification**

Run:

```bash
pytest tests/test_evidence_auto_index.py tests/test_evidence_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/knowledge/evidence.py src/data_agent/session/history.py tests/test_evidence_auto_index.py
git commit -m "Index session evidence after saving sessions"
```

---

### Task 4: Add Multi-Kind Evidence Extraction

**Files:**
- Modify: `src/data_agent/knowledge/evidence.py`
- Test: `tests/test_evidence_kinds.py`

- [ ] **Step 1: Write failing test for tool call and user correction evidence**

Create `tests/test_evidence_kinds.py`:

```python
import json

from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.models import EvidenceKind


def test_index_session_extracts_tool_calls_and_user_corrections(tmp_path):
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "s1"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "ecommerce", "saved_at": "2026-05-23T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "record_evidence_record", "arguments": "{}"}}
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "record_evidence_record",
                    "content": '{"claim":"GMV excludes canceled orders","confidence":0.9}',
                },
                {"role": "user", "content": "纠正一下：GMV 还要排除退款订单"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = EvidenceStore(tmp_path / "knowledge", sessions_dir=sessions_dir)
    assert store.index_session("s1") >= 3

    records = store.search("GMV", project_id="ecommerce")
    kinds = {record.kind for record in records}

    assert EvidenceKind.TOOL_CALL in kinds
    assert EvidenceKind.USER_CORRECTION in kinds
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_evidence_kinds.py -q`

Expected: FAIL because indexing currently creates only `EvidenceKind.MESSAGE`.

- [ ] **Step 3: Implement kind detection helper**

In `src/data_agent/knowledge/evidence.py`, add:

```python
def _evidence_kind_for_message(self, message: dict[str, Any]) -> EvidenceKind:
    role = str(message.get("role", ""))
    name = str(message.get("name", ""))
    content = self._message_content(message)
    correction_markers = ("纠正", "更正", "修正", "不是", "应为", "应该是", "correction", "correct")

    if role == "tool" or name in {"record_evidence_record", "record_insight_record", "generate_report"}:
        if name == "generate_report":
            return EvidenceKind.REPORT
        if name in {"record_evidence_record", "record_insight_record"}:
            return EvidenceKind.ANALYSIS_RESULT
        return EvidenceKind.TOOL_CALL
    if any(marker in content.lower() for marker in correction_markers):
        return EvidenceKind.USER_CORRECTION
    if message.get("tool_calls"):
        return EvidenceKind.TOOL_CALL
    return EvidenceKind.MESSAGE
```

Use the returned kind when inserting `evidence_records`.

- [ ] **Step 4: Run verification**

Run:

```bash
pytest tests/test_evidence_kinds.py tests/test_evidence_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/knowledge/evidence.py tests/test_evidence_kinds.py
git commit -m "Extract typed evidence from saved sessions"
```

---

### Task 5: Memory Edit, Delete, and Promotion to Knowledge

**Files:**
- Modify: `src/data_agent/knowledge/memory.py`
- Modify: `src/data_agent/knowledge/library.py`
- Modify: `src/data_agent/web/blueprints/management.py`
- Test: `tests/test_memory_promotion.py`
- Test: `tests/test_web_management_phase15.py`

- [ ] **Step 1: Write failing store test for promotion**

Create `tests/test_memory_promotion.py`:

```python
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import KnowledgeSource, MemoryStatus


def test_memory_promotes_to_knowledge_with_traceable_source(tmp_path):
    root = tmp_path / "knowledge"
    memory = MemoryStore(root)
    library = KnowledgeLibrary(root)
    item = memory.create_candidate(
        text="GMV must exclude canceled and refunded orders.",
        summary="GMV口径",
        domain="ecommerce",
        tags=["gmv"],
        source_session_id="s1",
    )
    memory.confirm(item.id)

    knowledge = memory.promote_to_knowledge(
        item.id,
        library=library,
        title="GMV 口径",
        summary="GMV 排除取消与退款订单",
    )
    promoted = memory.get(item.id)

    assert knowledge is not None
    assert knowledge.source == KnowledgeSource.MEMORY_PROMOTION
    assert knowledge.domain == "ecommerce"
    assert "GMV" in knowledge.content
    assert promoted.status == MemoryStatus.PROMOTED
    assert promoted.promotion_target == knowledge.id
```

- [ ] **Step 2: Write failing API test for memory edit/delete/promote**

Create `tests/test_web_management_phase15.py`:

```python
def test_management_memory_edit_delete_promote(client):
    create = client.post(
        "/api/management/memory",
        json={
            "text": "GMV excludes canceled orders.",
            "summary": "GMV rule",
            "domain": "ecommerce",
            "tags": ["gmv"],
        },
    )
    assert create.status_code == 201
    memory_id = create.get_json()["id"]

    edit = client.patch(
        f"/api/management/memory/{memory_id}",
        json={"text": "GMV excludes canceled and refunded orders.", "summary": "GMV updated"},
    )
    assert edit.status_code == 200
    assert "refunded" in edit.get_json()["text"]

    client.post(f"/api/management/memory/{memory_id}/confirm")
    promote = client.post(
        f"/api/management/memory/{memory_id}/promote",
        json={"title": "GMV 口径", "summary": "GMV excludes canceled and refunded orders."},
    )
    assert promote.status_code == 201
    payload = promote.get_json()
    assert payload["memory"]["status"] == "promoted"
    assert payload["knowledge"]["source"] == "memory_promotion"

    delete = client.delete(f"/api/management/memory/{memory_id}")
    assert delete.status_code == 409
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
pytest tests/test_memory_promotion.py tests/test_web_management_phase15.py -q
```

Expected: FAIL because store and API methods do not exist.

- [ ] **Step 4: Implement MemoryStore update/delete/promote**

Add `update()`:

```python
def update(
    self,
    item_id: str,
    text: str | None = None,
    summary: str | None = None,
    memory_type: MemoryType | str | None = None,
    confidence: float | None = None,
    domain: str | None = None,
    tags: list[str] | None = None,
) -> MemoryItem | None:
    item = self.get(item_id)
    if item is None:
        return None
    if item.status in {MemoryStatus.PROMOTED, MemoryStatus.DEPRECATED}:
        raise ValueError("Promoted or deprecated memories cannot be edited")
    next_type = _memory_type(memory_type) if memory_type is not None else item.type
    next_confidence = item.confidence if confidence is None else float(confidence)
    if not math.isfinite(next_confidence) or next_confidence < 0 or next_confidence > 1:
        raise ValueError(f"Invalid confidence: {confidence}")
    with self.db.connect() as conn:
        conn.execute(
            """
            UPDATE memory_items
            SET text = ?, summary = ?, type = ?, confidence = ?, domain = ?, tags = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                text if text is not None else item.text,
                summary if summary is not None else item.summary,
                next_type.value,
                next_confidence,
                (domain.strip() if domain is not None and domain.strip() else item.domain),
                _json_list(tags if tags is not None else item.tags, "tags"),
                _now(),
                item_id,
            ),
        )
    return self.get(item_id)
```

Add `delete_candidate()`:

```python
def delete_candidate(self, item_id: str) -> bool:
    item = self.get(item_id)
    if item is None:
        return False
    if item.status not in {MemoryStatus.CANDIDATE, MemoryStatus.REJECTED}:
        raise ValueError("Only candidate or rejected memories can be deleted")
    with self.db.connect() as conn:
        conn.execute("DELETE FROM memory_items WHERE id = ?", (item_id,))
    return True
```

Add `promote_to_knowledge()`:

```python
def promote_to_knowledge(
    self,
    item_id: str,
    library,
    title: str = "",
    summary: str = "",
):
    from data_agent.knowledge.models import KnowledgeSource, MemoryStatus

    item = self.get(item_id)
    if item is None:
        return None
    if item.status != MemoryStatus.CONFIRMED:
        raise ValueError("Only confirmed memories can be promoted")
    knowledge = library.create(
        title=title or item.summary or item.text[:60],
        domain=item.domain or "general",
        content=item.text,
        summary=summary or item.summary,
        tags=item.tags,
        source=KnowledgeSource.MEMORY_PROMOTION,
    )
    with self.db.connect() as conn:
        conn.execute(
            """
            UPDATE memory_items
            SET status = ?, promotion_target = ?, updated_at = ?
            WHERE id = ?
            """,
            (MemoryStatus.PROMOTED.value, knowledge.id, _now(), item_id),
        )
    return knowledge
```

- [ ] **Step 5: Implement management API endpoints**

In `src/data_agent/web/blueprints/management.py`, add:

```python
@management_bp.patch("/management/memory/<memory_id>")
def update_memory(memory_id: str):
    data = _json()
    try:
        item = MemoryStore().update(
            memory_id,
            text=data.get("text"),
            summary=data.get("summary"),
            memory_type=data.get("memory_type"),
            confidence=data.get("confidence"),
            domain=data.get("domain"),
            tags=data.get("tags"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if item is None:
        return jsonify({"error": "Memory not found"}), 404
    return jsonify(_memory_to_dict(item))


@management_bp.delete("/management/memory/<memory_id>")
def delete_memory(memory_id: str):
    try:
        deleted = MemoryStore().delete_candidate(memory_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    if not deleted:
        return jsonify({"error": "Memory not found"}), 404
    return jsonify({"deleted": True})


@management_bp.post("/management/memory/<memory_id>/promote")
def promote_memory(memory_id: str):
    data = _json()
    try:
        memory_store = MemoryStore()
        knowledge = memory_store.promote_to_knowledge(
            memory_id,
            library=KnowledgeLibrary(),
            title=str(data.get("title") or ""),
            summary=str(data.get("summary") or ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if knowledge is None:
        return jsonify({"error": "Memory not found"}), 404
    memory = memory_store.get(memory_id)
    return jsonify({"memory": _memory_to_dict(memory), "knowledge": _knowledge_to_dict(knowledge)}), 201
```

- [ ] **Step 6: Run verification**

Run:

```bash
pytest tests/test_memory_promotion.py tests/test_web_management_phase15.py tests/test_memory_store.py tests/test_web_management.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/data_agent/knowledge/memory.py src/data_agent/knowledge/library.py src/data_agent/web/blueprints/management.py tests/test_memory_promotion.py tests/test_web_management_phase15.py
git commit -m "Add memory editing and promotion workflow"
```

---

### Task 6: Domain-Aware Retrieval and Query Normalization

**Files:**
- Modify: `src/data_agent/knowledge/retrieval.py`
- Modify: `src/data_agent/agent/loop.py`
- Test: `tests/test_retrieval_phase15.py`

- [ ] **Step 1: Write failing tests for domain filtering and Chinese query normalization**

Create `tests/test_retrieval_phase15.py`:

```python
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.retrieval import KnowledgeRetrievalService


def test_retrieval_prefers_requested_domain(tmp_path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    library.create(
        title="电商 GMV",
        domain="ecommerce",
        content="GMV excludes canceled orders.",
        summary="GMV口径",
    )
    library.create(
        title="游戏 留存",
        domain="game",
        content="Retention means next-day active users.",
        summary="留存口径",
    )

    service = KnowledgeRetrievalService(root=tmp_path / "knowledge")
    context = service.retrieve("GMV 如何计算", domain="ecommerce")

    assert [item.domain for item in context.knowledge_items] == ["ecommerce"]


def test_query_normalization_keeps_chinese_metric_terms(tmp_path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    library.create(
        title="留存率口径",
        domain="game",
        content="留存率 = 次日活跃用户 / 当日新增用户。",
        summary="留存率",
        tags=["留存率"],
    )

    service = KnowledgeRetrievalService(root=tmp_path / "knowledge")
    context = service.retrieve("帮我分析一下这个数据，我需要知道留存率和付费转化率的关系", domain="game")

    assert context.knowledge_items
    assert context.knowledge_items[0].title == "留存率口径"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_retrieval_phase15.py -q`

Expected: at least the Chinese query test may fail with current whitespace-only search.

- [ ] **Step 3: Add query term extraction**

In `src/data_agent/knowledge/retrieval.py`, add:

```python
def _query_terms(query: str) -> list[str]:
    lowered = query.lower()
    ascii_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9_]{1,}", lowered)
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    stopwords = {"帮我", "分析一下", "这个数据", "需要知道", "关系", "一下", "如何", "什么"}
    terms = [term for term in ascii_terms + cjk_terms if term not in stopwords]
    compact_terms: list[str] = []
    for term in terms:
        if len(term) > 8 and re.search(r"[\u4e00-\u9fff]", term):
            compact_terms.extend([term[i : i + 4] for i in range(0, len(term) - 1, 2)])
        else:
            compact_terms.append(term)
    seen = set()
    result = []
    for term in compact_terms:
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result
```

Use `" ".join(_query_terms(query)) or query` when calling library, memory, and evidence searches.

- [ ] **Step 4: Add AgentLoop retrieval service reuse and domain inference**

In `AgentLoop.__init__()`, add:

```python
self._knowledge_retrieval_service = None
```

Add helper:

```python
def _get_knowledge_retrieval_service(self):
    if self._knowledge_retrieval_service is None:
        from data_agent.knowledge.retrieval import KnowledgeRetrievalService

        self._knowledge_retrieval_service = KnowledgeRetrievalService()
    return self._knowledge_retrieval_service
```

Add helper:

```python
def _infer_retrieval_domain(self, user_input: str) -> str:
    text = f"{self.context.project_name or ''} {user_input}".lower()
    mappings = {
        "ecommerce": ("电商", "gmv", "订单", "退款", "转化"),
        "game": ("游戏", "留存", "付费率", "arpu", "dau"),
        "finance": ("金融", "授信", "逾期", "资产", "风控"),
    }
    for domain, markers in mappings.items():
        if any(marker in text for marker in markers):
            return domain
    return ""
```

Replace the local `KnowledgeRetrievalService()` construction in `_build_system_prompt()` with:

```python
service = self._get_knowledge_retrieval_service()
context = service.retrieve(
    retrieval_query,
    domain=self._infer_retrieval_domain(user_input),
    project_id=self.context.project_name or "",
    include_evidence=False,
)
```

- [ ] **Step 5: Run verification**

Run:

```bash
pytest tests/test_retrieval_phase15.py tests/test_knowledge_retrieval.py tests/test_knowledge_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/knowledge/retrieval.py src/data_agent/agent/loop.py tests/test_retrieval_phase15.py
git commit -m "Improve domain-aware knowledge retrieval"
```

---

### Task 7: Management API for Evidence Indexing, Domains, and Global Search

**Files:**
- Modify: `src/data_agent/web/blueprints/management.py`
- Test: `tests/test_web_management_search_phase15.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_web_management_search_phase15.py`:

```python
import json


def test_management_can_reindex_session_and_global_search(client, tmp_path, monkeypatch):
    from data_agent.config import get_config

    cfg = get_config()
    session_dir = cfg.sessions_resolved / "s_global"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"project_name": "ecommerce", "saved_at": "2026-05-23T10:00:00"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "conversation.json").write_text(
        json.dumps([{"role": "user", "content": "GMV 排除取消订单"}], ensure_ascii=False),
        encoding="utf-8",
    )

    index_resp = client.post("/api/management/evidence/index", json={"session_id": "s_global"})
    assert index_resp.status_code == 200
    assert index_resp.get_json()["indexed"] >= 1

    knowledge_resp = client.post(
        "/api/management/knowledge",
        json={"title": "GMV 口径", "domain": "ecommerce", "content": "GMV excludes canceled orders."},
    )
    assert knowledge_resp.status_code == 201

    search = client.get("/api/management/search?q=GMV")
    assert search.status_code == 200
    payload = search.get_json()
    assert payload["knowledge"]
    assert payload["evidence"]


def test_management_domains_lists_known_domains(client):
    client.post(
        "/api/management/knowledge",
        json={"title": "留存率", "domain": "game", "content": "留存率定义"},
    )

    resp = client.get("/api/management/domains")

    assert resp.status_code == 200
    assert "game" in resp.get_json()["domains"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_web_management_search_phase15.py -q`

Expected: FAIL because endpoints do not exist.

- [ ] **Step 3: Add endpoints**

In `management.py`, add:

```python
@management_bp.post("/management/evidence/index")
def index_evidence():
    data = _json()
    session_id = str(data.get("session_id") or "")
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    indexed = EvidenceStore().index_session(session_id)
    return jsonify({"indexed": indexed})


@management_bp.get("/management/search")
def global_search():
    query = request.args.get("q", "")
    domain = request.args.get("domain", "")
    project_id = request.args.get("project_id", "")
    return jsonify({
        "knowledge": [_knowledge_to_dict(item) for item in KnowledgeLibrary().search(query, domain=domain, limit=8)],
        "memory": [_memory_to_dict(item) for item in MemoryStore().search(query, domain=domain, limit=8)],
        "evidence": [_evidence_to_dict(item) for item in EvidenceStore().search(query, project_id=project_id, limit=8)],
    })


@management_bp.get("/management/domains")
def list_domains():
    domains = set()
    for item in KnowledgeLibrary().list():
        domains.add(item.domain)
    for item in MemoryStore().list():
        domains.add(item.domain)
    return jsonify({"domains": sorted(domain for domain in domains if domain)})
```

- [ ] **Step 4: Run verification**

Run:

```bash
pytest tests/test_web_management_search_phase15.py tests/test_web_management.py tests/test_web_management_comprehensive.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/data_agent/web/blueprints/management.py tests/test_web_management_search_phase15.py
git commit -m "Add management search and evidence indexing APIs"
```

---

### Task 8: Management Center UI Closed-Loop Controls

**Files:**
- Modify: `src/data_agent/web/templates/index.html`
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `src/data_agent/web/static/css/app.css`
- Test: `tests/test_web_overhaul.py`
- Test: `tests/test_web_management_ui_phase15.py`

- [ ] **Step 1: Write failing UI structure tests**

Create `tests/test_web_management_ui_phase15.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_web_management_ui_phase15.py -q`

Expected: FAIL because new labels and JS methods do not exist.

- [ ] **Step 3: Add UI actions**

In the Memory management list, add buttons:

```html
<button @click="openMemoryDrawer(item)" class="mgmt-icon-button" title="编辑记忆">编辑</button>
<button x-show="item.status === 'confirmed'" @click="openPromoteMemoryDrawer(item)" class="mgmt-icon-button" title="提升为知识">提升为知识</button>
<button x-show="item.status === 'candidate' || item.status === 'rejected'" @click="deleteMemory(item)" class="mgmt-icon-button danger" title="删除记忆">删除</button>
```

In the Evidence panel header, add:

```html
<button @click="indexEvidence()" class="mgmt-primary-button">重新索引</button>
```

In the management sidebar or top content area, add a global search input:

```html
<input x-model="managementCenter.globalQuery" @keydown.enter="globalManagementSearch()" class="mgmt-input" placeholder="全局搜索知识、记忆与证据">
```

- [ ] **Step 4: Add JS methods**

In `app.js`, add:

```javascript
async updateMemory() {
    const form = this.managementDrawer.form || {};
    const res = await fetch(`/api/management/memory/${encodeURIComponent(form.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
    });
    if (!res.ok) {
        this.showToast('记忆更新失败', 'error');
        return;
    }
    this.closeManagementDrawer();
    await this.loadManagementSection('memory');
}

async promoteMemory(form) {
    const res = await fetch(`/api/management/memory/${encodeURIComponent(form.id)}/promote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: form.title, summary: form.summary }),
    });
    if (!res.ok) {
        this.showToast('提升为知识失败', 'error');
        return;
    }
    this.closeManagementDrawer();
    await this.loadManagementSection('memory');
}

async deleteMemory(item) {
    const res = await fetch(`/api/management/memory/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
    if (!res.ok) {
        this.showToast('只能删除候选或已拒绝的记忆', 'error');
        return;
    }
    await this.loadManagementSection('memory');
}

async indexEvidence() {
    const sessionId = this.currentSessionId || '';
    if (!sessionId) {
        this.showToast('请先打开一个会话', 'error');
        return;
    }
    const res = await fetch('/api/management/evidence/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
    });
    if (!res.ok) {
        this.showToast('证据索引失败', 'error');
        return;
    }
    await this.searchEvidence();
}

async globalManagementSearch() {
    const q = encodeURIComponent(this.managementCenter.globalQuery || '');
    const res = await fetch(`/api/management/search?q=${q}`);
    this.managementCenter.globalResults = res.ok ? await res.json() : { knowledge: [], memory: [], evidence: [] };
}
```

Wire these methods into existing drawer submit logic so memory edit and promote use separate drawer modes.

- [ ] **Step 5: Run static verification**

Run:

```bash
pytest tests/test_web_management_ui_phase15.py tests/test_web_overhaul.py -q
node --check src/data_agent/web/static/js/app.js
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/data_agent/web/templates/index.html src/data_agent/web/static/js/app.js src/data_agent/web/static/css/app.css tests/test_web_management_ui_phase15.py tests/test_web_overhaul.py
git commit -m "Add closed loop controls to management center"
```

---

### Task 9: Final Integration and Real Data Regression

**Files:**
- Modify: existing tests only if they expose real mismatches.

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
pytest tests/test_knowledge_models.py tests/test_knowledge_library.py tests/test_memory_store.py tests/test_memory_promotion.py tests/test_evidence_store.py tests/test_evidence_auto_index.py tests/test_evidence_kinds.py tests/test_knowledge_retrieval.py tests/test_retrieval_phase15.py -q
```

Expected: all pass.

- [ ] **Step 2: Run focused web suite**

Run:

```bash
pytest tests/test_web_management.py tests/test_web_management_comprehensive.py tests/test_web_management_phase15.py tests/test_web_management_search_phase15.py tests/test_web_management_ui_phase15.py tests/test_web_overhaul.py -q
```

Expected: all pass.

- [ ] **Step 3: Run related integration suite**

Run:

```bash
pytest tests/test_knowledge_integration.py tests/test_real_data_integration.py tests/test_knowledge_tools_phase1.py tests/test_knowledge_tools_phase15.py -q
```

Expected: all pass.

- [ ] **Step 4: Run syntax checks**

Run:

```bash
python -m compileall -q src/data_agent
node --check src/data_agent/web/static/js/app.js
```

Expected: both commands exit 0.

- [ ] **Step 5: Run one real data smoke flow**

Use a temp `DATA_AGENT_HOME` and verify:

```python
from data_agent.session.history import save_session
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.retrieval import KnowledgeRetrievalService

save_session(
    [
        {"role": "user", "content": "GMV 需要排除取消订单和退款订单"},
        {"role": "assistant", "content": "已确认 GMV 口径。"},
    ],
    "real_phase15",
    project_name="ecommerce",
)
records = EvidenceStore().search("GMV", project_id="ecommerce")
memory = MemoryStore().create_candidate("GMV 需要排除取消订单和退款订单", summary="GMV口径", domain="ecommerce")
MemoryStore().confirm(memory.id)
knowledge = MemoryStore().promote_to_knowledge(memory.id, library=KnowledgeLibrary(), title="GMV 口径")
context = KnowledgeRetrievalService().retrieve("GMV 如何计算", domain="ecommerce")

assert records
assert knowledge
assert context.knowledge_items
```

Expected: all assertions pass.

- [ ] **Step 6: Commit test adjustments if needed**

Run:

```bash
git status --short
git add <changed-files>
git commit -m "Verify knowledge memory closed loop"
```

Only commit files changed by this implementation. Do not stage unrelated existing workspace changes.

---

## Completion Criteria

- Old domain/experience agent tools are no longer visible in active tool selection.
- Saving a session automatically indexes searchable evidence.
- Evidence records can represent messages, tool calls, analysis results, user corrections, and reports when those structures exist in session history.
- Confirmed memory can be promoted into a formal knowledge item and records the promoted knowledge ID.
- Candidate/rejected memories can be edited or deleted; confirmed memories can be deprecated or promoted.
- Retrieval uses a reusable service per AgentLoop and can infer a practical domain for common data-analysis contexts.
- Management center exposes memory edit/delete/promote, evidence reindex, domain list, and global search.
- Chinese UI text and Chinese retrieval examples are covered by tests.
- Focused backend, web, integration, compile, and JS syntax checks pass.
