# 矩阵测试韧性修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实 Provider 矩阵测试能稳定跑完六场景：错误可归因、瞬态可重试、仅全局错误停批且可恢复、oracle 可审计。

**Architecture:** 分类/重试全部实现在验收 guard 层（`strict_provider_guard.py` + 新 `provider_error_taxonomy.py`），不动产品 LLM client；整批停止与恢复以收据里的 `error_class` 为决策依据（`real_provider_browser_batch.py` + 新 `resume_batch.py`）；oracle 检查从 tmp 一次性脚本提炼进版本库（`matrix_oracles.py`）。

**Tech Stack:** Python 3.11+ / pytest / litellm（仅异常属性消费）/ 现有 acceptance 脚本体系。

**Spec:** `docs/superpowers/specs/2026-09-05-matrix-resilience-design.md`

## Global Constraints

- 错误类别枚举固定为：`quota_exhausted` / `credential_invalid` / `rate_limited` / `content_rejected` / `server_error` / `network_transient` / `unclassified`。
- `GLOBAL_FATAL_CLASSES = {"quota_exhausted", "credential_invalid"}`（仅此类停整批，外加连续 3 场景同签名）。
- `RETRYABLE_ERROR_CLASSES = {"rate_limited", "network_transient", "server_error"}`；每逻辑调用最多 1 次重试，固定退避 20 秒（构造器可注入以便测试）。
- 每次物理尝试都是收据独立 ordinal，重试记录带 `retry_of`，重试计入 call_cap。
- latch 的 `code` 保持 `"provider_request_failed"` 不变（兼容既有消费者），类别放 `error_class` 字段（规格中"code 携带类别"的实现简化，已记录于此）。
- 不改产品 `src/data_agent/llm/client.py` 的重试；不放松收据/计量/隔离边界；不引入模型 fallback。
- 收据新增字段（`error_class` / `http_status` / `request_id` / `error_message`）不得包含 API key；`error_message` 截断 500 字符。
- 提交信息结尾带 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 每个任务收尾必须跑该任务的测试命令并确认结果后才能 commit。

---

### Task 1: 基线回归与工作区分组提交

**Files:**
- Modify: `.gitignore`（仅当需要追加 `tmp/`）
- Commit: 全部 53 个修改 + 175 个未跟踪文件（除 tmp/、artifacts/ 运行时产物）

**Interfaces:**
- Produces: 干净的已提交基线，后续任务在其上增量修改。

- [ ] **Step 1: 全量离线回归确认绿**

Run: `uv run pytest tests/ -q 2>&1 | tail -5`
Expected: `2538 passed, 1 skipped`（数字允许 ±少量新增；若出现失败，先单独重跑失败项区分已知顺序性抖动——见记忆 test-suite-order-dependent-flakiness——仅当单独重跑仍失败才视为回归并停下报告，不继续提交）

- [ ] **Step 2: 提交组 A——产品修复与其测试**

```bash
git add src/data_agent/agent src/data_agent/tools src/data_agent/session src/data_agent/llm src/data_agent/utils tests/
git commit -m "fix: land A01-A04 systemic repairs (evidence projection, publication isolation)

Uncommitted since 2026-08-28 (HEAD 3b271d7). Evidence projection for
analyze_time_series real fields, publication_rejected isolation with one
bounded rewrite, freeze-entry single-digest authorization, and their
regression tests (54 focused + full-suite green).

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 3: 提交组 B——验收基础设施**

```bash
git add scripts/acceptance
git commit -m "feat: acceptance infrastructure (guard, batch ledger, counted servers)

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 4: 提交组 C——web 变更**

```bash
git add src/data_agent/web
git commit -m "feat: web UI updates from A02-A04 remediation

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 5: 提交组 D——批次证据记录**

```bash
git add docs/audit
git commit -m "docs: record A01-A05R2 batch evidence and systemic reviews

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 6: 处理残余未跟踪项**

Run: `git status --porcelain` — 若仅剩 `tmp/`、`artifacts/` 下条目：确认二者无已跟踪文件（`git ls-files -- tmp artifacts` 输出为空），把 `tmp/` 与 `artifacts/` 追加进 `.gitignore` 并提交 `chore: ignore runtime outputs`。若 `git ls-files artifacts` 非空（golden-quality 基线被跟踪），则只追加 `tmp/`。
Expected: `git status --porcelain` 最终为空。

---

### Task 2: 错误分类模块 provider_error_taxonomy

**Files:**
- Create: `scripts/acceptance/provider_error_taxonomy.py`
- Test: `tests/test_provider_error_taxonomy.py`

**Interfaces:**
- Produces: `classify_provider_error(exc: BaseException) -> str`（返回 Global Constraints 的 7 类之一）；`error_evidence(exc: BaseException) -> dict`（键：`http_status`、`request_id`、`error_message`，可能为 None/省略）；常量 `GLOBAL_FATAL_CLASSES`、`RETRYABLE_ERROR_CLASSES`。Task 3/5/6/7/10 消费。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_provider_error_taxonomy.py
from scripts.acceptance.provider_error_taxonomy import (
    GLOBAL_FATAL_CLASSES, RETRYABLE_ERROR_CLASSES,
    classify_provider_error, error_evidence,
)


class _FakeProviderError(Exception):
    def __init__(self, message="", status_code=None, request_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


def test_quota_exhausted_by_status_402():
    assert classify_provider_error(_FakeProviderError("x", status_code=402)) == "quota_exhausted"

def test_quota_exhausted_by_text_on_400():
    # DeepSeek 余额不足是 400 + 文本，必须文本匹配
    exc = _FakeProviderError("Error code: 400 - Insufficient Balance", status_code=400)
    assert classify_provider_error(exc) == "quota_exhausted"

def test_credential_invalid():
    assert classify_provider_error(_FakeProviderError("bad key", status_code=401)) == "credential_invalid"
    assert classify_provider_error(_FakeProviderError("forbidden", status_code=403)) == "credential_invalid"

def test_rate_limited_and_server_error():
    assert classify_provider_error(_FakeProviderError("slow down", status_code=429)) == "rate_limited"
    assert classify_provider_error(_FakeProviderError("boom", status_code=503)) == "server_error"

def test_content_rejected_default_for_400():
    assert classify_provider_error(_FakeProviderError("bad request", status_code=400)) == "content_rejected"

def test_network_transient_by_type_name():
    for name in ("APIConnectionError", "APITimeoutError", "Timeout", "ConnectionError"):
        exc = _FakeProviderError(name)
        exc.__class__.__name__ = name
        assert classify_provider_error(exc) == "network_transient", name

def test_unclassified_for_unknown():
    assert classify_provider_error(ValueError("local bug")) == "unclassified"

def test_error_evidence_truncates_and_collects():
    exc = _FakeProviderError("E" * 900, status_code=402, request_id="req-1")
    ev = error_evidence(exc)
    assert ev == {"http_status": 402, "request_id": "req-1", "error_message": "E" * 500}

def test_fatal_and_retryable_sets():
    assert GLOBAL_FATAL_CLASSES == {"quota_exhausted", "credential_invalid"}
    assert RETRYABLE_ERROR_CLASSES == {"rate_limited", "network_transient", "server_error"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_provider_error_taxonomy.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 最小实现**

```python
# scripts/acceptance/provider_error_taxonomy.py
"""Classify real-Provider failures from litellm-style exceptions.

Acceptance-only: turns a bare exception name into a decision-grade error
class so the batch controller can distinguish global-fatal conditions
(quota, credentials) from scenario-level and transient failures.
"""
from __future__ import annotations

GLOBAL_FATAL_CLASSES = frozenset({"quota_exhausted", "credential_invalid"})
RETRYABLE_ERROR_CLASSES = frozenset({"rate_limited", "network_transient", "server_error"})

_QUOTA_TEXT_MARKERS = (
    "insufficient balance", "insufficient_quota", "arrearage", "余额不足", "quota exceeded",
)
_NETWORK_TYPE_NAMES = frozenset({
    "APIConnectionError", "APITimeoutError", "Timeout", "ConnectionError", "ReadTimeout",
})
_MESSAGE_LIMIT = 500


def _status(exc: BaseException):
    value = getattr(exc, "status_code", None)
    return int(value) if isinstance(value, int) else None


def classify_provider_error(exc: BaseException) -> str:
    status = _status(exc)
    name = type(exc).__name__
    text = str(exc).lower()
    if name in _NETWORK_TYPE_NAMES:
        return "network_transient"
    if status == 402 or (status == 400 and any(m in text for m in _QUOTA_TEXT_MARKERS)) \
            or any(m in text for m in _QUOTA_TEXT_MARKERS):
        return "quota_exhausted"
    if status in (401, 403):
        return "credential_invalid"
    if status == 429:
        return "rate_limited"
    if status is not None and status >= 500:
        return "server_error"
    if status is not None and status >= 400:
        return "content_rejected"
    if name in ("BadRequestError", "NotFoundError"):
        return "content_rejected"
    return "unclassified"


def error_evidence(exc: BaseException) -> dict:
    evidence: dict = {}
    status = _status(exc)
    if status is not None:
        evidence["http_status"] = status
    request_id = getattr(exc, "request_id", None)
    if request_id:
        evidence["request_id"] = str(request_id)[:120]
    message = str(exc)
    if message:
        evidence["error_message"] = message[:_MESSAGE_LIMIT]
    return evidence
```

注意 `test_network_transient_by_type_name` 用改 `__class__.__name__` 的假异常验证按类型名分类的分支；实现里网络类判断放在最前，避免 4xx 文本误伤。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_provider_error_taxonomy.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/provider_error_taxonomy.py tests/test_provider_error_taxonomy.py
git commit -m "feat: classify provider failures into decision-grade error classes

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: guard 收据详录错误证据

**Files:**
- Modify: `scripts/acceptance/strict_provider_guard.py:236-254`（`_finish`）
- Test: `tests/test_strict_provider_guard.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `classify_provider_error` / `error_evidence`。
- Produces: 失败收据记录含 `error_class`/`http_status`/`request_id`/`error_message`；latch 详情含 `error_class`。Task 5/6/7/10 依赖 `terminal_failure["error_class"]` 与记录字段。

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_strict_provider_guard.py 追加
class _ProviderHttpError(Exception):
    def __init__(self, message, status_code=None, request_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


def test_failed_call_records_error_class_and_evidence(tmp_path):
    completion = _Completion([_ProviderHttpError("Insufficient Balance", status_code=400, request_id="req-9")])
    guard = _guard(tmp_path, completion)
    with pytest.raises(_ProviderHttpError):
        _call(guard)
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    call = receipt["calls"][0]
    assert call["status"] == "failed"
    assert call["error_class"] == "quota_exhausted"
    assert call["http_status"] == 400
    assert call["request_id"] == "req-9"
    assert "Insufficient Balance" in call["error_message"]
    assert receipt["terminal_failure"]["code"] == "provider_request_failed"
    assert receipt["terminal_failure"]["error_class"] == "quota_exhausted"


def test_failed_call_without_evidence_still_gets_class(tmp_path):
    completion = _Completion([ValueError("local transport bug")])
    guard = _guard(tmp_path, completion)
    with pytest.raises(ValueError):
        _call(guard)
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert receipt["calls"][0]["error_class"] == "unclassified"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_strict_provider_guard.py -q -k error_class`
Expected: FAIL（KeyError: 'error_class'）

- [ ] **Step 3: 修改 `_finish`**

```python
# scripts/acceptance/strict_provider_guard.py —— 替换 _finish 中 error 分支
    def _finish(self, record: dict[str, Any], status: str, error: BaseException | None = None,
                *, trip_latch: bool = True) -> None:
        with self._lock:
            if record["status"] != "started":
                return
            record["status"] = status
            record["finished_at"] = _utc_now()
            record["local_request_stopped"] = status != "unknown"
            record["response_received"] = status == "completed"
            record["completion_semantics"] = "transport_exhausted" if record["stream"] else "response_returned"
            if status in {"cancelled", "unknown"}:
                self._latch.trip("provider_request_" + status, ordinal=record["ordinal"])
            if error is not None:
                from scripts.acceptance.provider_error_taxonomy import (
                    classify_provider_error, error_evidence,
                )
                error_class = classify_provider_error(error)
                record["error_class"] = error_class
                record.update(error_evidence(error))
                if trip_latch:
                    self._latch.trip(
                        "provider_request_failed",
                        ordinal=record["ordinal"],
                        error_type=type(error).__name__,
                        error_class=error_class,
                    )
            self._write_receipt_locked()
```

（`trip_latch` 参数本任务先落位、默认 True 保持现行为，Task 4 使用 False 路径。）

- [ ] **Step 4: 跑全文件测试确认无回归**

Run: `uv run pytest tests/test_strict_provider_guard.py -q`
Expected: 全部 passed（含既有测试）

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/strict_provider_guard.py tests/test_strict_provider_guard.py
git commit -m "feat: guard receipt records error class and provider evidence

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: guard 受控重试

**Files:**
- Modify: `scripts/acceptance/strict_provider_guard.py`（`completion`、`_start`、构造器）
- Test: `tests/test_strict_provider_guard.py`（追加）

**Interfaces:**
- Consumes: Task 2 常量；Task 3 的 `trip_latch` 参数。
- Produces: `StrictProviderCallGuard(..., retry_backoff_seconds: float = 20.0)`；收据重试记录 `retry_of: int`。仅同步异常路径重试；流建立后的中途断流不重试（loop 层事务，超出本设计）。

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_strict_provider_guard.py 追加
def _guard_fast_retry(tmp_path, completion, *, call_cap=4):
    from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard
    return StrictProviderCallGuard(
        completion=completion, receipt_path=tmp_path / "provider-calls.json",
        candidate_id="candidate-test", source_digest="sha256:source", call_cap=call_cap,
        expected_model="provider/model", allowed_max_tokens={300, 800, 8000},
        temperature=0.0, timeout_seconds=120, retry_backoff_seconds=0.0,
    )


def test_rate_limited_gets_one_retry_and_succeeds(tmp_path):
    completion = _Completion([
        _ProviderHttpError("rate limited", status_code=429),
        object(),
    ])
    guard = _guard_fast_retry(tmp_path, completion)
    response = _call(guard)
    assert response is not None and len(completion.calls) == 2
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert [c["status"] for c in receipt["calls"]] == ["failed", "completed"]
    assert receipt["calls"][1]["retry_of"] == 1
    assert receipt["calls"][0]["error_class"] == "rate_limited"
    assert receipt["terminal_failure"] is None


def test_quota_error_never_retries(tmp_path):
    completion = _Completion([_ProviderHttpError("Insufficient Balance", status_code=400)])
    guard = _guard_fast_retry(tmp_path, completion)
    with pytest.raises(_ProviderHttpError):
        _call(guard)
    assert len(completion.calls) == 1


def test_second_retryable_failure_trips_latch(tmp_path):
    completion = _Completion([
        _ProviderHttpError("timeout A"), _ProviderHttpError("timeout B"),
    ])
    for exc in completion._responses:
        exc.__class__.__name__ = "APITimeoutError"
    guard = _guard_fast_retry(tmp_path, completion)
    with pytest.raises(_ProviderHttpError):
        _call(guard)
    receipt = json.loads((tmp_path / "provider-calls.json").read_text(encoding="utf-8"))
    assert [c["status"] for c in receipt["calls"]] == ["failed", "failed"]
    assert receipt["terminal_failure"]["error_class"] == "network_transient"


def test_retry_respects_call_cap(tmp_path):
    completion = _Completion([_ProviderHttpError("rate limited", status_code=429), object()])
    guard = _guard_fast_retry(tmp_path, completion, call_cap=1)
    with pytest.raises(_ProviderHttpError):
        _call(guard)
    assert len(completion.calls) == 1  # cap 耗尽，不重试
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_strict_provider_guard.py -q -k retry`
Expected: FAIL（TypeError: unexpected keyword retry_backoff_seconds 或无重试行为）

- [ ] **Step 3: 实现重试**

构造器追加参数 `retry_backoff_seconds: float = 20.0`，存 `self._retry_backoff_seconds = float(retry_backoff_seconds)`。`_start` 追加可选参数 `retry_of: int | None = None`，record 创建时若非 None 则 `record["retry_of"] = int(retry_of)`。`completion` 整体替换为：

```python
    def completion(self, **kwargs: Any) -> Any:
        from scripts.acceptance.provider_error_taxonomy import (
            RETRYABLE_ERROR_CLASSES, classify_provider_error,
        )
        guarded_kwargs = dict(kwargs)
        guarded_kwargs["num_retries"] = 0
        guarded_kwargs["temperature"] = self._temperature
        guarded_kwargs["timeout"] = self._timeout_seconds
        record = self._start(guarded_kwargs)
        try:
            response = self._completion(**guarded_kwargs)
        except BaseException as exc:
            error_class = classify_provider_error(exc)
            retryable = (
                error_class in RETRYABLE_ERROR_CLASSES
                and self.calls_started < self._call_cap
                and self._latch.snapshot() is None
            )
            self._finish(record, "failed", exc, trip_latch=not retryable)
            if not retryable:
                raise
            time.sleep(self._retry_backoff_seconds)
            retry_record = self._start(guarded_kwargs, retry_of=record["ordinal"])
            try:
                response = self._completion(**guarded_kwargs)
            except BaseException as exc2:
                self._finish(retry_record, "failed", exc2)
                raise
            self._finish(retry_record, "completed")
            return self._dispatch_response(guarded_kwargs, retry_record, response)
        self._finish(record, "completed")
        return self._dispatch_response(guarded_kwargs, record, response)

    def _dispatch_response(self, guarded_kwargs: dict[str, Any], record: dict[str, Any], response: Any) -> Any:
        if not guarded_kwargs.get("stream"):
            return response
        stream = _CountedStream(self, record, response)
        with self._lock:
            self._streams[record["ordinal"]] = stream
            shutdown = self._latch.snapshot() is not None
        if shutdown:
            stream.close()
        return stream
```

- [ ] **Step 4: 跑全文件测试确认通过**

Run: `uv run pytest tests/test_strict_provider_guard.py -q`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/strict_provider_guard.py tests/test_strict_provider_guard.py
git commit -m "feat: single receipt-visible retry for transient provider failures

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: retry_policy 冻结契约

**Files:**
- Modify: `scripts/acceptance/real_provider_browser_batch.py:105-111`（preflight policy 校验）
- Modify: `scripts/acceptance/real_provider_browser_server.py:146-156`（guard 装配传入退避）
- Test: `tests/test_real_provider_browser_batch.py`（追加）

**Interfaces:**
- Consumes: Task 4 的 `retry_backoff_seconds`。
- Produces: 候选 `provider_policy.retry_policy` 必填字段：`{"max_retry_attempts": 1, "backoff_seconds": 20, "retry_error_classes": ["rate_limited", "network_transient", "server_error"]}`；`num_retries` 保持 0 校验不变。Task 12 的 A06 冻结脚本生成此字段。

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_real_provider_browser_batch.py 追加 —— 按既有测试的 batch/candidate 夹具模式
def test_preflight_requires_retry_policy_contract(tmp_path, frozen_batch_factory):
    batch, cases, batch_path, launcher = frozen_batch_factory(tmp_path)
    # 删掉 retry_policy → preflight 必须拒绝
    for case in cases:
        case["provider_policy"].pop("retry_policy", None)
    rewrite_case_files(batch, cases, tmp_path)
    with pytest.raises(ValueError, match="retry policy"):
        preflight(tmp_path, batch_path, launcher)


def test_preflight_rejects_widened_retry_classes(tmp_path, frozen_batch_factory):
    batch, cases, batch_path, launcher = frozen_batch_factory(tmp_path)
    cases[0]["provider_policy"]["retry_policy"]["retry_error_classes"].append("quota_exhausted")
    rewrite_case_files(batch, cases, tmp_path)
    with pytest.raises(ValueError, match="retry policy"):
        preflight(tmp_path, batch_path, launcher)
```

（`frozen_batch_factory` / `rewrite_case_files` 若该测试文件尚无等价夹具，按文件内既有构造 batch+cases 的 helper 复制扩展：生成六场景候选 JSON、数据文件与 batch JSON，使其能通过除 retry_policy 外的全部校验。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_real_provider_browser_batch.py -q -k retry_policy`
Expected: FAIL（当前无 retry_policy 概念，测试期望 preflight 拒绝缺失字段但现行为是放行）

- [ ] **Step 3: 修改 preflight 校验**

在 `real_provider_browser_batch.py` 的 policy 校验字典中保留 `"num_retries": 0`，并在其后追加：

```python
        retry_policy = policy.get("retry_policy")
        if retry_policy != {
            "max_retry_attempts": 1,
            "backoff_seconds": 20,
            "retry_error_classes": ["rate_limited", "network_transient", "server_error"],
        }:
            raise ValueError("case request policy outside strict batch contract: retry policy")
```

在 `real_provider_browser_server.py` guard 装配处传入：

```python
        retry_backoff_seconds=float(policy.get("retry_policy", {}).get("backoff_seconds", 20)),
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归该两文件**

Run: `uv run pytest tests/test_real_provider_browser_batch.py tests/test_real_provider_browser_server.py tests/test_strict_provider_guard.py -q`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/real_provider_browser_batch.py scripts/acceptance/real_provider_browser_server.py tests/test_real_provider_browser_batch.py
git commit -m "feat: freeze retry_policy in batch contract, wire backoff into guard

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 分级整批停止 + 计划文档修订

**Files:**
- Modify: `scripts/acceptance/real_provider_browser_batch.py:331-340`（main 中的前批检查）
- Modify: `docs/audit/2026-08-29-real-provider-browser-matrix-plan.md`（文末追加修订节）
- Test: `tests/test_real_provider_browser_batch.py`（追加）

**Interfaces:**
- Consumes: Task 3 的 `terminal_failure["error_class"]`。
- Produces: 纯函数 `batch_stop_reason(closed_records: list[dict]) -> str | None`（closed_records 为 ledger.state["cases"] 的已关闭项）；返回停止原因码或 None。签名小写 str。

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_real_provider_browser_batch.py 追加
from scripts.acceptance.real_provider_browser_batch import batch_stop_reason


def _closed(case_id, code="acceptance_server_closed", error_class=None, http_status=None):
    record = {"id": case_id, "status": "closed", "terminal_failure": {"code": code}}
    if error_class:
        record["terminal_failure"]["error_class"] = error_class
    if http_status:
        record["terminal_failure"]["http_status"] = http_status
    return record


def test_scenario_level_failure_does_not_stop_batch():
    assert batch_stop_reason([_closed("M01", error_class="content_rejected")]) is None


def test_quota_failure_stops_batch():
    reason = batch_stop_reason([_closed("M01", error_class="quota_exhausted", http_status=400)])
    assert reason == "provider_failure_global_fatal:quota_exhausted"


def test_three_consecutive_same_signature_stops_batch():
    records = [_closed(f"M0{i}", error_class="content_rejected", http_status=400) for i in (1, 2, 3)]
    assert batch_stop_reason(records) == "consecutive_same_signature:content_rejected:400"


def test_two_same_then_different_does_not_stop():
    records = [
        _closed("M01", error_class="content_rejected", http_status=400),
        _closed("M02", error_class="content_rejected", http_status=400),
        _closed("M03", error_class="unclassified"),
    ]
    assert batch_stop_reason(records) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_real_provider_browser_batch.py -q -k batch_stop`
Expected: FAIL（ImportError: batch_stop_reason）

- [ ] **Step 3: 实现**

在 `real_provider_browser_batch.py` 模块级追加：

```python
_GLOBAL_FATAL_CLASSES = frozenset({"quota_exhausted", "credential_invalid"})


def batch_stop_reason(closed_records: list[dict]) -> str | None:
    """Batch-wide stop is reserved for global-fatal conditions or a
    cross-scenario pattern (three consecutive closed cases with the same
    error signature).  Any other scenario failure must not skip the
    remaining frozen cases."""
    consecutive: list[tuple[str, str | None]] = []
    for record in closed_records:
        failure = record.get("terminal_failure") or {}
        if failure.get("code") != "provider_request_failed":
            consecutive.clear()
            continue
        error_class = failure.get("error_class") or "unclassified"
        if error_class in _GLOBAL_FATAL_CLASSES:
            return f"provider_failure_global_fatal:{error_class}"
        signature = (error_class, failure.get("http_status"))
        if consecutive and consecutive[-1] == signature:
            consecutive.append(signature)
        else:
            consecutive = [signature]
        if len(consecutive) >= 3:
            return f"consecutive_same_signature:{signature[0]}:{signature[1]}"
    return None
```

`main()` 中替换第 338-339 行的检查：

```python
        stop_reason = batch_stop_reason([c for c in ledger.state["cases"] if c.get("status") == "closed"])
        if stop_reason:
            raise ValueError("Provider failure stopped the whole batch: " + stop_reason)
```

（删除原 `if previous.get("terminal_failure", {}).get("code") == "provider_request_failed": raise ValueError("Provider failure stopped the whole batch")`。）

- [ ] **Step 4: 计划文档增补修订记录**

在 `docs/audit/2026-08-29-real-provider-browser-matrix-plan.md` 文末追加：

```markdown
## 2026-09-05 修订：分级整批停止与批次恢复（依据 docs/superpowers/specs/2026-09-05-matrix-resilience-design.md）

- 整批停止条件修订为仅限：额度耗尽（quota_exhausted）、凭证失效（credential_invalid）、连续 3 个场景以同签名（ErrorClass + HTTP status）失败。原实现的“任何 provider_request_failed 即停整批”与本文“相同错误签名不成为跳过其余场景的理由”冲突，予以纠正。
- 场景级 Provider 失败（含 content_rejected、重试后仍瞬态失败）保持场景内熔断，批次继续剩余场景。
- 对 rate_limited / network_transient / server_error 允许每次逻辑调用一次收据可见、计入上限的退避重试（20 秒），由候选冻结的 retry_policy 声明。
- 全局错误停批后，源码摘要未变时可机械派生恢复批（resumes_from 原批），被全局错误杀死的场景作废重试一次，已完成场景不重跑；恢复批需用户对新批次摘要重新授权。
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/test_real_provider_browser_batch.py -q`
Expected: 全部 passed（含既有测试——若既有测试断言旧的一刀切停止行为，按新语义更新该断言并在提交信息注明）

- [ ] **Step 6: Commit**

```bash
git add scripts/acceptance/real_provider_browser_batch.py tests/test_real_provider_browser_batch.py docs/audit/2026-08-29-real-provider-browser-matrix-plan.md
git commit -m "fix: batch stop only on global-fatal or cross-scenario signature

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 批次恢复 derive_resume_batch

**Files:**
- Create: `scripts/acceptance/resume_batch.py`
- Test: `tests/test_resume_batch.py`

**Interfaces:**
- Consumes: `release_source_digest(root)`（scripts/acceptance/release_source.py）；`_normalized_file_hash`、`_canonical_json_hash`、`_sha256_bytes`（real_provider_browser_server.py）；Task 6 的 `batch_stop_reason` 全局错误判定。
- Produces: `derive_resume_batch(root: Path, batch_path: Path, ledger_path: Path, *, new_batch_id: str, new_isolation_root: str) -> dict`。返回提案 dict：`{"batch_id", "batch_sha256", "batch_path", "case_paths", "resumes_from": {"batch_sha256", "batch_id", "completed_cases", "voided_cases"}, "authorization_required": "AUTHORIZED_BATCH_SHA256"}`。写入 docs/audit 下新候选 JSON 与新 batch JSON。void 判定：closed 且 `terminal_failure.error_class in GLOBAL_FATAL_CLASSES`；completed 判定：closed 且非 void。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_resume_batch.py
import json
from pathlib import Path

import pytest

from scripts.acceptance.resume_batch import derive_resume_batch


def _write_minimal_batch(root: Path, tmp: Path):
    """构造 M01-M03 微缩批次：M01 正常关闭、M02 quota 作废、M03 未跑。"""
    (root / "scripts/acceptance").mkdir(parents=True)
    (root / "tmp").mkdir()
    source_digest = "sha256:" + "a" * 64
    case_paths = []
    for case_id, cap in (("M01", 4), ("M02", 4), ("M03", 4)):
        candidate = {
            "schema_version": 1, "candidate_id": f"c_{case_id}", "matrix_case_id": case_id,
            "source_digest": source_digest, "model": "provider/model", "port": 7100,
            "data": [], "prompt": f"p-{case_id}", "prompts": [f"p-{case_id}"],
            "provider_policy": {"call_cap": cap, "analysis_turns": 1},
            "oracle": {"required_tools": []},
            "writes": {
                "workspace_dir": f"tmp/orig/M{case_id[1:]}/workspace",
                "sessions_dir": f"tmp/orig/M{case_id[1:]}/sessions",
                "provider_receipt_path": f"tmp/orig/M{case_id[1:]}/provider-calls.json",
                "report_path": f"docs/audit/orig-{case_id}-report.json",
                "process_control_dir": f"tmp/orig/M{case_id[1:]}/process-control",
            },
        }
        path = root / "docs/audit" / f"orig-{case_id}-candidate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        case_paths.append({"id": case_id, "path": str(path.relative_to(root)).replace("\\", "/"),
                           "sha256": _file_hash(path)})
    batch = {"schema_version": "real_provider_browser_batch.v1", "batch_id": "ORIG",
             "source_digest": source_digest, "model": "provider/model",
             "cases": case_paths, "call_cap": 12,
             "isolation_root": "tmp/orig", "report_path": "docs/audit/orig-report.json",
             "launcher_path": "scripts/acceptance/x.py", "launcher_sha256": _file_hash(root / "scripts/acceptance/x.py"),
             "supervisor_path": "scripts/acceptance/x.py", "supervisor_sha256": _file_hash(root / "scripts/acceptance/x.py")}
    batch_path = root / "docs/audit/orig-batch.json"
    batch_path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
    ledger = {"schema_version": 2, "batch_sha256": _file_hash(batch_path),
              "cases": [
                  {"id": "M01", "status": "closed",
                   "terminal_failure": {"code": "acceptance_server_closed"}, "real_calls": 2},
                  {"id": "M02", "status": "closed",
                   "terminal_failure": {"code": "provider_request_failed", "error_class": "quota_exhausted"},
                   "real_calls": 1},
              ], "real_calls": 3, "calls_started_observed": 3, "blocked_attempts": 0}
    ledger_path = root / "tmp/orig/provider-batch.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return batch_path, ledger_path, source_digest


def _file_hash(path: Path) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_derive_resume_batch_voids_quota_case_and_keeps_completed(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest", lambda r: source_digest)
    proposal = derive_resume_batch(root, batch_path, ledger_path,
                                   new_batch_id="RESUME-1", new_isolation_root="tmp/resume-1")
    assert proposal["resumes_from"]["completed_cases"] == ["M01"]
    assert proposal["resumes_from"]["voided_cases"] == ["M02"]
    new_batch = json.loads(Path(proposal["batch_path"]).read_text(encoding="utf-8"))
    assert [c["id"] for c in new_batch["cases"]] == ["M02", "M03"]
    assert new_batch["resumes_from"]["batch_id"] == "ORIG"
    assert new_batch["call_cap"] == 8  # 仅 void+未跑场景的 caps
    for entry in new_batch["cases"]:
        candidate = json.loads((root / entry["path"]).read_text(encoding="utf-8"))
        assert "tmp/resume-1/" in candidate["writes"]["workspace_dir"]
        assert candidate["source_digest"] == source_digest


def test_derive_resume_rejects_changed_source(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, _ = _write_minimal_batch(root, tmp_path)
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest",
                        lambda r: "sha256:" + "b" * 64)
    with pytest.raises(ValueError, match="source digest"):
        derive_resume_batch(root, batch_path, ledger_path,
                            new_batch_id="RESUME-1", new_isolation_root="tmp/resume-1")


def test_derive_resume_rejects_open_case(tmp_path, monkeypatch):
    root = tmp_path
    batch_path, ledger_path, source_digest = _write_minimal_batch(root, tmp_path)
    ledger = json.loads(ledger_path.read_text())
    ledger["cases"].append({"id": "M03", "status": "started"})
    ledger_path.write_text(json.dumps(ledger))
    monkeypatch.setattr("scripts.acceptance.resume_batch.release_source_digest", lambda r: source_digest)
    with pytest.raises(ValueError, match="closed"):
        derive_resume_batch(root, batch_path, ledger_path,
                            new_batch_id="RESUME-1", new_isolation_root="tmp/resume-1")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_resume_batch.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# scripts/acceptance/resume_batch.py
"""Mechanically derive a resume batch after a global-fatal batch stop.

A resume batch reuses the original frozen source digest, data, prompts,
oracles and per-case caps.  Cases closed by a global-fatal provider
error are voided (their receipts stay archived) and re-attempted once;
completed cases are not re-run.  Any source change forces a brand-new
batch instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.acceptance.real_provider_browser_batch import _GLOBAL_FATAL_CLASSES
from scripts.acceptance.real_provider_browser_server import (
    _canonical_json_hash, _normalized_file_hash,
)
from scripts.acceptance.release_source import release_source_digest


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("frozen path escapes repository")
    return path


def derive_resume_batch(root: Path, batch_path: Path, ledger_path: Path, *,
                        new_batch_id: str, new_isolation_root: str) -> dict:
    root = root.resolve()
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    if release_source_digest(root) != batch["source_digest"]:
        raise ValueError("source digest changed; a resume batch is not allowed")
    closed = {}
    for record in ledger["cases"]:
        if record.get("status") != "closed":
            raise ValueError("cannot resume a batch with an unclosed case: " + str(record.get("id")))
        closed[record["id"]] = record
    original_hash = _normalized_file_hash(Path(batch_path))
    if ledger.get("batch_sha256") != original_hash:
        raise ValueError("ledger does not match the original batch receipt")

    completed, voided, remaining = [], [], []
    for entry in batch["cases"]:
        case_id = entry["id"]
        record = closed.get(case_id)
        if record is None:
            remaining.append(entry)
            continue
        error_class = (record.get("terminal_failure") or {}).get("error_class")
        (voided if error_class in _GLOBAL_FATAL_CLASSES else completed).append(entry)

    new_entries, new_caps = [], 0
    for entry in voided + remaining:
        case = json.loads(_inside(root, entry["path"]).read_text(encoding="utf-8"))
        suffix = case["matrix_case_id"][1:]
        case["writes"] = {
            key: value.replace(f"tmp/{batch['isolation_root'].split('/', 1)[-1]}/",
                               f"{new_isolation_root}/")
            for key, value in case["writes"].items()
        }
        case["writes"]["report_path"] = \
            f"docs/audit/{new_batch_id.lower()}-{case['matrix_case_id'].lower()}-report.json"
        case["candidate_id"] = case["candidate_id"] + "_resume"
        new_name = f"{new_batch_id.lower()}-{case['matrix_case_id'].lower()}-candidate.json"
        new_path = root / "docs/audit" / new_name
        new_path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        new_entries.append({"id": case["matrix_case_id"],
                            "path": str(new_path.relative_to(root)).replace("\\", "/"),
                            "sha256": _normalized_file_hash(new_path)})
        new_caps += int(case["provider_policy"]["call_cap"])

    new_batch = dict(batch)
    new_batch.update({
        "batch_id": new_batch_id,
        "cases": new_entries,
        "call_cap": new_caps,
        "isolation_root": new_isolation_root,
        "resumes_from": {"batch_id": batch["batch_id"], "batch_sha256": original_hash,
                         "completed_cases": [e["id"] for e in completed],
                         "voided_cases": [e["id"] for e in voided]},
    })
    new_batch_path = root / "docs/audit" / f"{new_batch_id.lower()}-batch.json"
    new_batch_path.write_text(json.dumps(new_batch, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "batch_id": new_batch_id,
        "batch_sha256": _normalized_file_hash(new_batch_path),
        "batch_path": str(new_batch_path),
        "case_paths": [e["path"] for e in new_entries],
        "resumes_from": new_batch["resumes_from"],
        "authorization_required": "AUTHORIZED_BATCH_SHA256",
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_resume_batch.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/resume_batch.py tests/test_resume_batch.py
git commit -m "feat: derive resume batches after global-fatal provider stops

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: matrix_oracles 属性断言与观察缺口分离

**Files:**
- Create: `scripts/acceptance/matrix_oracles.py`
- Test: `tests/test_matrix_oracles.py`

**Interfaces:**
- Produces: `ORACLE_VERSION = "2026-09-05.1"`；`zero_semantics_violations(text: str) -> list[str]`；`OBSERVER_GAP_CHECKS = frozenset({"within_30s_completion_observation"})`。Task 10（run_batch 审计）消费；Task 12 冻结时在候选 oracle 字段写 `oracle_version`。

- [ ] **Step 1: 写失败测试（用 A04/A05R2 真实文本做正反例）**

```python
# tests/test_matrix_oracles.py
from scripts.acceptance.matrix_oracles import (
    OBSERVER_GAP_CHECKS, ORACLE_VERSION, zero_semantics_violations,
)

PUBLISHED_OK = (
    "首个 30 天窗口内未观测到的用户记为右删失：因未满 30 天出现结构性 0=右删失，"
    "系统判定为删失而非真实 0，不代表用户流失。拟合 R²=0.98，不可外推超出观测窗口。"
)
DOMAIN_CLAIM = "这属于游戏行业典型的幂律区间，收入必然向头部集中。"
CAUSAL_CLAIM = "发放代金券导致付费提升 12%，因此应扩大投放。"


def test_censoring_statements_are_allowed():
    assert zero_semantics_violations(PUBLISHED_OK) == []


def test_unsourced_domain_claim_is_flagged():
    violations = zero_semantics_violations(DOMAIN_CLAIM)
    assert violations and "游戏行业典型的幂律区间" in violations[0]


def test_unqualified_causal_claim_is_flagged():
    violations = zero_semantics_violations(CAUSAL_CLAIM)
    assert violations and "导致" in violations[0]


def test_version_and_observer_gaps_declared():
    assert ORACLE_VERSION == "2026-09-05.1"
    assert "within_30s_completion_observation" in OBSERVER_GAP_CHECKS
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_matrix_oracles.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# scripts/acceptance/matrix_oracles.py
"""Versioned, property-based oracle checks for the browser matrix.

Replaces per-batch tmp scripts whose exact-string blacklists could not
distinguish a property violation from a statistically correct statement.
"""
from __future__ import annotations

import re

ORACLE_VERSION = "2026-09-05.1"

OBSERVER_GAP_CHECKS = frozenset({"within_30s_completion_observation"})

# 统计上正确的删失/缺失语义表述：发布文本允许出现。
_CENSORING_ALLOW_PATTERNS = (
    re.compile(r"右删失"),
    re.compile(r"删失而非真实\s*0"),
    re.compile(r"结构性\s*0=右删失"),
    re.compile(r"未满\s*30\s*天出现结构性"),
)

# 属性 1：无溯源的领域断言（原 A04 黑名单条目的属性化）。
_DOMAIN_CLAIM_PATTERNS = (
    re.compile(r".{0,12}(典型的?幂律区间|行业惯例|业内公认).{0,12}"),
)

# 属性 2：未限定的因果断言（观察性数据不得声称因果）。
_CAUSAL_PATTERNS = (
    re.compile(r".{0,20}(导致|造成了|因此应).{0,20}"),
)

_QUALIFIER_MARKERS = ("可能", "或与", "相关而非因果", "关联", "在观测窗口内", "删失", "右删失")


def zero_semantics_violations(text: str) -> list[str]:
    violations: list[str] = []
    for pattern in _DOMAIN_CLAIM_PATTERNS:
        match = pattern.search(text)
        if match:
            violations.append(("domain_claim", match.group(0)))
    for pattern in _CAUSAL_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        window = match.group(0)
        if any(marker in window for marker in _QUALIFIER_MARKERS):
            continue  # 已有限定词/删失说明的表述不属于未限定因果
        violations.append(("unqualified_causal", window))
    return violations
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_matrix_oracles.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/matrix_oracles.py tests/test_matrix_oracles.py
git commit -m "feat: versioned property-based matrix oracles with observer-gap split

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 真实形状回放库种子

**Files:**
- Create: `scripts/acceptance/extract_replay_shapes.py`
- Create: `tests/replay/test_real_shape_projection.py`
- Create: `tests/replay/fixtures/`（由脚本生成，含 README 说明再生成命令）

**Interfaces:**
- Consumes: 已归档批次 `tmp/real-provider-browser-matrix-a05r2-diag/M0*/sessions/*/conversation.jsonl` 与 `tmp/real-provider-browser-matrix-a04-diag/M0*/...`；产品函数 `data_agent.tools.evidence_statistics.bind_computed_statistics(payload, receipts)`。
- Produces: fixtures JSON（结构：`{"case": "M01", "turns": [{"tool": "...", "structured_result": {...}, "receipt": {...}}]}`，字符串值截断 200 字符）；参数化回放测试。

- [ ] **Step 1: 写提取脚本**

```python
# scripts/acceptance/extract_replay_shapes.py
"""Extract sanitized real-model shapes from closed batch sessions.

Offline replay aims to stop each real batch discovering a new contract
layer: recorded tool-result shapes must pass evidence projection before
any new real batch is authorized.
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SOURCES = ("tmp/real-provider-browser-matrix-a05r2-diag", "tmp/real-provider-browser-matrix-a04-diag")
_TARGET = _ROOT / "tests/replay/fixtures"
_TRUNCATE = 200


def _sanitize(value):
    if isinstance(value, str):
        return value[:_TRUNCATE]
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:50]]
    return value


def extract() -> int:
    written = 0
    for source in _SOURCES:
        base = _ROOT / source
        if not base.is_dir():
            continue
        for case_dir in sorted(base.glob("M0*")):
            turns = []
            for conversation in sorted((case_dir / "sessions").glob("*/conversation.jsonl")):
                for line in conversation.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    message = json.loads(line)
                    if message.get("role") == "tool":
                        try:
                            payload = json.loads(message.get("content") or "{}")
                        except json.JSONDecodeError:
                            continue
                        turns.append({"tool": message.get("name") or "unknown",
                                      "structured_result": _sanitize(payload)})
            if not turns:
                continue
            target = _TARGET / f"{base.name}_{case_dir.name}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(
                {"case": case_dir.name, "batch": base.name, "turns": turns},
                ensure_ascii=False, indent=1), encoding="utf-8")
            written += 1
    return written


if __name__ == "__main__":
    print(json.dumps({"fixtures_written": extract()}))
```

- [ ] **Step 2: 生成 fixtures**

Run: `uv run python -m scripts.acceptance.extract_replay_shapes`
Expected: 输出 `{"fixtures_written": N}`（N≥1，A05R2 M01/M02 与 A04 各场景会话存在）；`tests/replay/fixtures/` 出现 JSON 文件。在 `tests/replay/fixtures/README.md` 写一行：`Regenerate: uv run python -m scripts.acceptance.extract_replay_shapes`

- [ ] **Step 3: 写回放测试**

```python
# tests/replay/test_real_shape_projection.py
"""Real-shape replay: recorded tool payloads must survive evidence binding.

These fixtures come from consumed real-Provider batches (see fixtures
README).  A projection crash or a dropped native statistics source here
is the offline signal that used to cost one real batch to discover.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_agent.tools.evidence_statistics import bind_computed_statistics

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))
pytestmark = pytest.mark.skipif(not FIXTURES, reason="no replay fixtures generated yet")


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
def test_recorded_shapes_bind_without_crashing(fixture, monkeypatch):
    import hashlib

    from data_agent.tools import result_reference

    recorded = json.loads(fixture.read_text(encoding="utf-8"))["turns"]
    lookup, receipts = {}, []
    for index, turn in enumerate(recorded):
        receipt_id = f"replay_{index:03d}"
        digest = hashlib.sha256(json.dumps(
            turn["structured_result"], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        lookup[f"tool_outputs/{receipt_id}_detail.json"] = (
            turn["structured_result"], {"receipt_id": receipt_id})
        receipts.append({"id": receipt_id, "tool_call_id": receipt_id,
                         "tool_name": turn["tool"], "arguments": {},
                         "structured_result_sha256": digest})
    # bind_computed_statistics 在函数体内 import，patch 模块属性即生效。
    monkeypatch.setattr(result_reference, "load_result_reference", lambda ref: lookup[ref])

    payload = {"claim": "replay", "metrics": {"reported": 1}}
    bind_computed_statistics(payload, receipts)
    assert payload["computed_statistics_sources"], \
        f"{fixture.stem}: recorded shapes must bind as evidence sources"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/replay/test_real_shape_projection.py -q`
Expected: 参数化用例 passed（fixtures 存在时）

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/extract_replay_shapes.py tests/replay/
git commit -m "test: seed real-shape replay library from consumed batches

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: 一键批次 run_batch 与预检探针

**Files:**
- Create: `scripts/acceptance/run_batch.py`
- Test: `tests/test_run_batch.py`

**Interfaces:**
- Consumes: `real_provider_browser_batch.main`（逐场景执行，签名 `main(*, root, batch_path, launcher_path)`）；`resume_batch.derive_resume_batch`；`matrix_oracles`；`StrictProviderCallGuard`（探针复用）。
- Produces: `run_probe(root: Path, *, model: str, api_base: str, api_key: str, receipt_path: Path) -> dict`（返回 `{"ok": bool, "error_class": str | None}`，探针 1 次调用、max_tokens=16、cap=1，独立收据）；CLI：`uv run python -m scripts.acceptance.run_batch --batch <path> --launcher <path>`（无授权时打印摘要退出；`--authorized` 时先探针后逐场景）。Task 12 消费。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_run_batch.py
import json

import pytest

from scripts.acceptance.run_batch import run_probe


class _ProbeCompletion:
    def __init__(self, responses):
        self._responses = list(responses)

    def __call__(self, **kwargs):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _probe_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_AGENT_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("DATA_AGENT_API_KEY", "sk-test")
    return tmp_path / "probe-receipt.json"


def test_probe_reports_quota_as_global_fatal(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)

    class _Quota(Exception):
        status_code = 400

        def __str__(self):
            return "Error code: 400 - Insufficient Balance"

    result = run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                       api_key="sk-test", receipt_path=receipt,
                       completion=_ProbeCompletion([_Quota()]), backoff_seconds=0.0)
    assert result["ok"] is False
    assert result["error_class"] == "quota_exhausted"
    saved = json.loads(receipt.read_text(encoding="utf-8"))
    assert saved["calls"][0]["error_class"] == "quota_exhausted"


def test_probe_success_returns_ok(tmp_path, monkeypatch):
    receipt = _probe_env(monkeypatch, tmp_path)
    result = run_probe(tmp_path, model="provider/model", api_base="https://example.invalid/v1",
                       api_key="sk-test", receipt_path=receipt,
                       completion=_ProbeCompletion([object()]), backoff_seconds=0.0)
    assert result["ok"] is True and result["error_class"] is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_run_batch.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# scripts/acceptance/run_batch.py
"""One-command batch orchestration: freeze-check, probe, run, audit.

The probe is one minimal authorized call (max_tokens=16, cap=1) with its
own receipt, spent before any scenario setup so credential or balance
failures do not burn scenario budgets.  Mid-batch exhaustion is handled
by resume batches, not by this probe.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.acceptance.provider_error_taxonomy import GLOBAL_FATAL_CLASSES, classify_provider_error
from scripts.acceptance.real_provider_browser_batch import preflight
from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard


def run_probe(root: Path, *, model: str, api_base: str, api_key: str, receipt_path: Path,
              completion=None, backoff_seconds: float = 5.0) -> dict:
    root = root.resolve()
    if completion is None:
        os.environ.setdefault("DATA_AGENT_API_BASE", api_base)
        os.environ.setdefault("DATA_AGENT_API_KEY", api_key)
        from data_agent.llm import client as llm_client
        completion = llm_client.completion
    guard = StrictProviderCallGuard(
        completion=completion, receipt_path=receipt_path, candidate_id="batch_probe",
        source_digest="probe", call_cap=1, expected_model=model,
        allowed_max_tokens={16}, temperature=0.0, timeout_seconds=30,
        retry_backoff_seconds=backoff_seconds,
    )
    try:
        guard.completion(model=model, max_tokens=16, stream=False,
                         messages=[{"role": "user", "content": "ping"}], api_base=api_base,
                         api_key=api_key)
    except BaseException as exc:  # probe failures are data, not crashes
        error_class = classify_provider_error(exc)
        return {"ok": False, "error_class": error_class,
                "global_fatal": error_class in GLOBAL_FATAL_CLASSES}
    return {"ok": True, "error_class": None, "global_fatal": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    batch, cases, checks = preflight(root, Path(args.batch), Path(args.launcher))
    if not args.authorized:
        print(json.dumps({
            "batch_id": batch["batch_id"],
            "authorize_with": "AUTHORIZED_BATCH_SHA256=" + checks["BATCH_SHA256"],
            "cases": [entry["id"] for entry in batch["cases"]],
        }, ensure_ascii=False, indent=2))
        return
    probe = run_probe(root, model=batch["model"], api_base=os.environ["DATA_AGENT_API_BASE"],
                      api_key=os.environ["DATA_AGENT_API_KEY"],
                      receipt_path=root / batch["isolation_root"] / "probe-receipt.json")
    print(json.dumps({"probe": probe}, ensure_ascii=False))
    if not probe["ok"]:
        raise SystemExit("probe failed: " + str(probe["error_class"]))
    from scripts.acceptance.real_provider_browser_batch import main as run_case
    for entry in batch["cases"]:
        run_case(root=root, batch_path=Path(args.batch), launcher_path=Path(args.launcher))


if __name__ == "__main__":
    main()
```

（注意：`real_provider_browser_batch.main` 通过 argparse 读取 `--case`，逐场景循环调用需改为直接复用其内部流程；实现时把 `main` 拆出 `run_case(root, batch_path, launcher_path, case_id)` 无 argparse 的内核函数，CLI `main` 保持兼容。）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_run_batch.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/acceptance/run_batch.py scripts/acceptance/real_provider_browser_batch.py tests/test_run_batch.py
git commit -m "feat: one-command batch runner with authorized credential probe

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: 故障注入综合回归

**Files:**
- Create: `tests/test_matrix_resilience_injection.py`

**Interfaces:**
- Consumes: Task 4 guard 重试、Task 6 `batch_stop_reason`、Task 7 `derive_resume_batch`、Task 8 oracle。全部离线，fake completion。

- [ ] **Step 1: 写集成场景测试**

```python
# tests/test_matrix_resilience_injection.py
"""Integrated fault-injection: the three flows the spec requires.

1. quota error stops the batch AND the batch is resumable;
2. rate limit retries once and the journey continues;
3. three consecutive same-signature failures stop the batch.
"""
from __future__ import annotations

import json

from scripts.acceptance.real_provider_browser_batch import batch_stop_reason
from scripts.acceptance.resume_batch import derive_resume_batch
from scripts.acceptance.strict_provider_guard import StrictProviderCallGuard


class _Flaky:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _QuotaError(Exception):
    status_code = 400

    def __str__(self):
        return "Error code: 400 - Insufficient Balance"


class _RateLimit(Exception):
    status_code = 429


def _guard(tmp_path, completion, cap=8):
    return StrictProviderCallGuard(
        completion=completion, receipt_path=tmp_path / "r.json", candidate_id="c",
        source_digest="sha256:s", call_cap=cap, expected_model="m",
        allowed_max_tokens={300}, temperature=0.0, timeout_seconds=30,
        retry_backoff_seconds=0.0,
    )


def test_flow_quota_stops_batch_and_resume_derives(tmp_path, monkeypatch):
    guard = _guard(tmp_path, _Flaky([_QuotaError()]))
    try:
        guard.completion(model="m", max_tokens=300, stream=False, messages=[])
    except _QuotaError:
        pass
    receipt = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    failure = receipt["terminal_failure"]
    assert failure["error_class"] == "quota_exhausted"
    assert batch_stop_reason([{"id": "M01", "status": "closed", "terminal_failure": failure}]) \
        == "provider_failure_global_fatal:quota_exhausted"
    # 恢复派生路径由 tests/test_resume_batch.py 覆盖；此处只验证停批触发条件与原因码。


def test_flow_rate_limit_retries_and_journey_continues(tmp_path):
    completion = _Flaky([_RateLimit(), object(), object()])
    guard = _guard(tmp_path, completion)
    guard.completion(model="m", max_tokens=300, stream=False, messages=[])
    receipt = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert receipt["terminal_failure"] is None
    assert [c["status"] for c in receipt["calls"]] == ["failed", "completed"]
    # 后续逻辑调用仍可继续（未熔断）。
    guard.completion(model="m", max_tokens=300, stream=False, messages=[])
    assert len(completion.calls) == 3


def test_flow_three_same_signature_scenarios_stop_batch(tmp_path):
    def failure(code, cls, status):
        return {"code": code, "error_class": cls, "http_status": status}

    records = [{"id": f"M0{i}", "status": "closed",
                "terminal_failure": failure("provider_request_failed", "content_rejected", 400)}
               for i in (1, 2, 3)]
    assert batch_stop_reason(records) == "consecutive_same_signature:content_rejected:400"
```

- [ ] **Step 2: 跑测试确认通过（本任务是聚合验证，实现已在前序任务）**

Run: `uv run pytest tests/test_matrix_resilience_injection.py -q`
Expected: 3 passed。若失败，说明前序任务接口不一致，回到对应任务修复后重跑。

- [ ] **Step 3: Commit**

```bash
git add tests/test_matrix_resilience_injection.py
git commit -m "test: integrated fault-injection for stop/retry/resume flows

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 12: 全量回归、A06 冻结与预检（运营 gate：等待用户授权）

**Files:**
- Create: `docs/audit/2026-09-05-matrix-a06-batch.json` 及六场景候选（由现有 prepare 流程生成，oracle 字段新增 `oracle_version: "2026-09-05.1"`、provider_policy 新增 retry_policy）

**Interfaces:**
- Consumes: Task 5 retry_policy 契约、Task 8 ORACLE_VERSION、Task 10 run_batch。

- [ ] **Step 1: 全量离线回归**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 全部 passed（含新增测试；失败则修复后再继续）

- [ ] **Step 2: 冻结 A06 批次**

以 `tmp/a05r2-preparation-01/prepare.py` 为模板生成 A06 候选（batch_id `MATRIX-A06-DIAG`，isolation `tmp/real-provider-browser-matrix-a06-diag`）：oracle 字段加 `"oracle_version": "2026-09-05.1"`；provider_policy 加 `"retry_policy": {"max_retry_attempts": 1, "backoff_seconds": 20, "retry_error_classes": ["rate_limited", "network_transient", "server_error"]}`；六场景、预算沿用 216 上限草案。
Run: `uv run python tmp/a06-preparation-01/prepare.py`
Expected: docs/audit 下生成 a06 批次与六候选 JSON

- [ ] **Step 3: 零调用预检**

Run: `uv run python -m scripts.acceptance.run_batch --batch docs/audit/2026-09-05-matrix-a06-batch.json --launcher scripts/acceptance/real_provider_browser_batch.py`
Expected: 打印 `authorize_with: AUTHORIZED_BATCH_SHA256=sha256:...` 与六场景清单；网络尝试 0

- [ ] **Step 4: 停下等待用户授权（不可自动继续）**

输出批次摘要给用户，明确：授权即同意 216 次调用上限与探针 1 次调用；A01-A05R2 授权不可复用。**此步骤是人工 gate，未获用户明确授权不得执行 `--authorized`。**

---

## Self-Review 记录

- 规格覆盖：S1→Task 2/3；S2→Task 6（含计划文档修订）；S3→Task 4/5；S4→Task 7；S5→Task 8（oracle_version 由 Task 12 冻结写入）；S6→Task 9；S7→Task 1；S8→Task 10；S9→Task 11/12。无缺口。
- 占位符扫描：Task 5 Step 1 的 `frozen_batch_factory` 标注了按既有夹具模式扩展的具体来源；Task 10 Step 3 明确了 `main` 拆 `run_case` 的兼容要求。无 TBD。
- 类型一致性：`error_class` 字段名、`batch_stop_reason` 返回格式（`provider_failure_global_fatal:<class>` / `consecutive_same_signature:<class>:<status>`）、`derive_resume_batch` 返回键在 Task 6/7/10/11 间一致；`retry_backoff_seconds` 构造器参数在 Task 4/5/10 一致。
