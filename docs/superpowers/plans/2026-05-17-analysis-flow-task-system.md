# Analysis Flow and Task System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix analysis intent/readiness classification, add same-turn load-then-analyze safeguards, and correct task scoping/readiness behavior.

**Architecture:** Keep the existing `AnalysisFlowController`, `AnalysisSessionState`, and `TaskManager`, but strengthen their contracts. Intent answers "what does the user want"; execution readiness answers "can we run now"; task records remain durable workflow items, not runtime jobs.

**Tech Stack:** Python, pytest, Flask blueprints, Alpine frontend JavaScript.

---

## File Map

- Modify: `src/data_agent/agent/intent.py`
  - Add `ExecutionReadiness`.
  - Add file/data-reference detection.
  - Stop downgrading clear analysis intent to `data_requirement` just because `data_state == "no_data"`.
  - Add `load_then_analyze` recommended action.

- Modify: `src/data_agent/agent/analysis_flow_controller.py`
  - Respect `execution_readiness`.
  - Create specs/tasks when readiness becomes executable.
  - Keep real data-requirement behavior for missing data and "what data do I need?" questions.

- Modify: `src/data_agent/agent/loop.py`
  - Track turn intent/readiness and tools used.
  - Replan after successful `load_data`.
  - Add final-answer guard for overview-only completion.

- Modify: `src/data_agent/session/task_manager.py`
  - Make scoped listing strict by default.
  - Add explicit global inclusion.
  - Add ready-task helpers.

- Modify: `src/data_agent/web/blueprints/tasks.py`
  - Expose `include_global`, `ready_only`, and `active_only` query options.

- Modify: `src/data_agent/web/static/js/app.js`
  - Reduce polling when no active task exists.
  - Keep refresh on session switch, explicit refresh, report/artifact completion, and `task_update` SSE.

- Modify tests:
  - `tests/test_intent_classification.py`
  - `tests/test_method_playbooks.py`
  - `tests/test_comprehensive_analysis_flow.py`
  - `tests/test_web_workbench_parity.py`
  - add `tests/test_task_manager_scope.py` if the existing task tests become too crowded.

---

### Task 1: Add Intent/Readiness Failing Tests

**Files:**
- Modify: `tests/test_intent_classification.py`

- [ ] **Step 1: Add tests for clear analysis plus file references**

Add tests near the existing `plan_turn_intent` cases:

```python
def test_clear_analysis_with_file_paths_is_pending_load_directed_analysis():
    text = (
        "Please analyze revenue decline and retention change in these files:\n"
        "D:\\Project\\Daily\\data\\orders.xlsx\n"
        "D:\\Project\\Daily\\data\\payments.csv\n"
        "Focus on trend, driver decomposition, and limitations."
    )

    result = plan_turn_intent(text, "")

    assert result.intent_type == "directed_analysis"
    assert result.clarity == "clear"
    assert result.data_state == "no_data"
    assert result.execution_readiness == "pending_load"
    assert result.recommended_action == "load_then_analyze"


def test_hypothetical_csv_preparation_question_is_data_requirement():
    text = "What csv files should I prepare if I want to analyze revenue decline?"

    result = plan_turn_intent(text, "")

    assert result.intent_type == "data_requirement"
    assert result.execution_readiness == "missing_data"
    assert result.recommended_action == "request_data"


def test_clear_analysis_without_data_source_is_missing_data():
    result = plan_turn_intent("Analyze why revenue declined by channel", "")

    assert result.intent_type == "directed_analysis"
    assert result.execution_readiness == "missing_data"
    assert result.recommended_action == "request_data"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_intent_classification.py -q
```

Expected: FAIL because `TurnIntent` has no `execution_readiness`, and current analysis keywords with no loaded data return `data_requirement`.

---

### Task 2: Implement Intent/Readiness Model

**Files:**
- Modify: `src/data_agent/agent/intent.py`
- Modify: `tests/test_intent_classification.py`

- [ ] **Step 1: Add readiness and action types**

In `src/data_agent/agent/intent.py`, add:

```python
ExecutionReadiness = Literal["ready", "pending_load", "missing_data", "insufficient_data"]
```

Add `"load_then_analyze"` to `RecommendedAction`.

Extend `TurnIntent`:

```python
execution_readiness: ExecutionReadiness = "missing_data"
```

- [ ] **Step 2: Add conservative data-reference detection**

Add helper functions:

```python
_DATA_FILE_EXTENSIONS = (".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet", ".feather")
_HYPOTHETICAL_DATA_PHRASES = (
    "what csv", "which csv", "what files", "which files", "what data",
    "need to prepare", "should i prepare", "should we prepare",
)


def has_loadable_data_reference(text: str) -> bool:
    lowered = (text or "").lower()
    if any(phrase in lowered for phrase in _HYPOTHETICAL_DATA_PHRASES):
        return False
    return any(ext in lowered for ext in _DATA_FILE_EXTENSIONS)


def infer_execution_readiness(user_input: str, session_context: str = "") -> ExecutionReadiness:
    data_state = infer_data_state(session_context)
    if data_state == "data_loaded":
        return "ready"
    if has_loadable_data_reference(user_input):
        return "pending_load"
    return "missing_data"
```

- [ ] **Step 3: Update `plan_turn_intent` to compute readiness once**

Inside `plan_turn_intent`:

```python
readiness = infer_execution_readiness(user_input, session_context)
fast_result = _try_fast_path(text, data_state, readiness)
```

When building LLM fallback and default fallback, pass readiness into `_stage_for`, `_action_for`, and `_make`.

- [ ] **Step 4: Update `_try_fast_path`**

Change the signature:

```python
def _try_fast_path(text: str, data_state: DataState, readiness: ExecutionReadiness) -> TurnIntent | None:
```

For analysis keywords, return directed analysis regardless of loaded data:

```python
if any(k in text for k in _ANALYSIS_KEYWORDS):
    return _make(
        "directed_analysis",
        "clear",
        data_state,
        _stage_for("directed_analysis", data_state, readiness),
        _action_for("directed_analysis", data_state, readiness),
        "User asked a specific analysis question.",
        execution_readiness=readiness,
    )
```

Keep `_DATA_REQUIREMENT_KEYWORDS` higher priority so explicit "what data do I need?" questions remain data requirements.

- [ ] **Step 5: Update `_stage_for`, `_action_for`, and `_make`**

Use readiness for directed analysis:

```python
def _stage_for(intent_type: str, data_state: str, readiness: str = "missing_data") -> str:
    if intent_type == "directed_analysis":
        return "execute" if readiness == "ready" else "scope"
    if intent_type == "comprehensive_report":
        return "report" if readiness == "ready" else "scope"
    ...


def _action_for(intent_type: str, data_state: str, readiness: str = "missing_data") -> str:
    if intent_type == "directed_analysis":
        if readiness == "ready":
            return "run_analysis"
        if readiness == "pending_load":
            return "load_then_analyze"
        return "request_data"
    ...
```

Update `_make` to accept `execution_readiness`.

- [ ] **Step 6: Run intent tests**

Run:

```bash
pytest tests/test_intent_classification.py tests/test_method_playbooks.py -q
```

Expected: PASS after updating any tests that directly call `_stage_for` or `_action_for` with old assumptions.

---

### Task 3: Add Flow Regression Tests for Load-Then-Analyze

**Files:**
- Modify: `tests/test_comprehensive_analysis_flow.py`

- [ ] **Step 1: Add fake-client regression test**

Add a test near `test_turn1_load_data_turn2_analyze`:

```python
def test_same_turn_file_plus_analysis_does_not_end_after_profile(self, tmp_path, clean_workspace):
    from data_agent.llm.client import Response, ToolCall
    from data_agent.agent.loop import AgentLoop
    from data_agent.session.workspace import workspace

    df = _make_df(50)
    csv_path = tmp_path / "sales.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools=None, system=""):
            self.calls += 1
            if self.calls == 1:
                return Response(tool_calls=[
                    ToolCall(id="tc_load", name="load_data", arguments={"source": str(csv_path), "name": "sales"})
                ])
            if self.calls == 2:
                return Response(tool_calls=[
                    ToolCall(id="tc_desc", name="describe_dataset", arguments={"name": "sales"})
                ])
            if self.calls == 3:
                return Response(text="The dataset has 50 rows. Suggested next analyses: trend and channel comparison.")
            return Response(text="Final analysis with evidence.")

    loop = AgentLoop(client=FakeClient(), session_id="same_turn_load_analyze")
    loop._get_system_prompt = lambda: ""

    reply = loop.run_turn(f"Analyze revenue decline by channel using {csv_path}. Include limitations.")

    assert "Suggested next analyses" not in reply
    assert "Final analysis" in reply
    assert workspace.list_datasets()
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_comprehensive_analysis_flow.py::TestConversationFlow::test_same_turn_file_plus_analysis_does_not_end_after_profile -q
```

Expected: FAIL because current loop accepts the overview-only final answer.

---

### Task 4: Implement Post-Load Replan and Final-Answer Guard

**Files:**
- Modify: `src/data_agent/agent/loop.py`

- [ ] **Step 1: Persist turn intent/readiness in `_prepare_analysis_turn`**

After computing intent, store it:

```python
self.context.turn_intent = intent
self._last_turn_intent = intent
```

Keep existing return value for activated groups.

- [ ] **Step 2: Add per-turn tracking**

At the start of `run_turn`, `run_turn_structured`, and `stream_turn`, initialize:

```python
self._turn_tools_used = []
self._turn_loaded_data = False
self._turn_final_guard_injected = False
```

- [ ] **Step 3: Record tools and successful data loads**

In `_execute_single_tool` and `_process_tool_calls`, after compacting tool output:

```python
self._turn_tools_used.append(tc.name)
if tc.name == "load_data" and not tool_msg_content.startswith('{"error":'):
    self._turn_loaded_data = True
```

For `_execute_tools_parallel`, record the tool names when appending tool messages.

- [ ] **Step 4: Add post-load replan helper**

Add:

```python
def _maybe_replan_after_data_load(self, user_input: str) -> None:
    if not getattr(self, "_turn_loaded_data", False):
        return
    self._turn_loaded_data = False
    self._prompt_cache_dirty = True
    with use_agent_context(self.context):
        self._prepare_analysis_turn(user_input)
```

Call it after each full batch of tool calls in `_loop_impl` and `stream_turn`, before the next LLM round.

- [ ] **Step 5: Add final-answer guard helper**

Add:

```python
_PROFILING_TOOLS = {"load_data", "list_data", "preview_data", "describe_dataset", "quick_profile", "detect_data_quality", "interpret_dataset"}
_SUBSTANTIVE_TOOLS = {"record_analysis_spec", "record_analysis_plan", "record_evidence_record", "record_insight_record", "compare_periods", "analyze_time_series", "funnel_analysis", "correlation_analysis", "ab_test", "generate_report", "generate_analysis_brief", "generate_formal_report", "run_python"}


def _should_continue_for_analysis_quality(self, user_input: str, final_text: str) -> bool:
    if getattr(self, "_turn_final_guard_injected", False):
        return False
    intent = getattr(self, "_last_turn_intent", None)
    if intent is None or intent.intent_type not in ("directed_analysis", "comprehensive_report"):
        return False
    if getattr(intent, "execution_readiness", "") not in ("ready", "pending_load"):
        return False
    tools_used = set(getattr(self, "_turn_tools_used", []))
    if tools_used & _SUBSTANTIVE_TOOLS:
        return False
    if not tools_used or not tools_used <= _PROFILING_TOOLS:
        return False
    return True
```

- [ ] **Step 6: Continue the loop instead of finalizing overview-only answers**

Before returning on `not response.has_tool_calls` in `_loop_impl` and `stream_turn`, call the guard:

```python
if self._should_continue_for_analysis_quality(user_input, final_text):
    self._turn_final_guard_injected = True
    self.messages.append({"role": "user", "content": (
        "<analysis_quality_guard>\n"
        "The user requested analysis, but this turn has only loaded or profiled data. "
        "Continue by creating or applying an AnalysisSpec, running relevant analysis steps, "
        "and recording evidence before giving the final answer.\n"
        "</analysis_quality_guard>"
    )})
    continue
```

Use the same pattern in streaming, yielding a paragraph separator if needed.

- [ ] **Step 7: Run flow tests**

Run:

```bash
pytest tests/test_comprehensive_analysis_flow.py::TestConversationFlow -q
```

Expected: PASS.

---

### Task 5: Add Task Manager Scope and Ready Tests

**Files:**
- Create: `tests/test_task_manager_scope.py`
- Modify: `tests/test_web_workbench_parity.py`

- [ ] **Step 1: Add task manager tests**

Create `tests/test_task_manager_scope.py`:

```python
from data_agent.session.task_manager import TaskManager


def test_list_for_scope_is_strict_by_default(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    current = mgr.create("Current", session_id="s1")
    mgr.create("Other", session_id="s2")
    mgr.create("Global")

    tasks = mgr.list_for_scope(session_id="s1")

    assert [t["id"] for t in tasks] == [current["id"]]


def test_list_for_scope_can_include_global(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    current = mgr.create("Current", session_id="s1")
    global_task = mgr.create("Global")

    tasks = mgr.list_for_scope(session_id="s1", include_global=True)

    assert {t["id"] for t in tasks} == {current["id"], global_task["id"]}


def test_list_ready_excludes_blocked_and_non_pending(tmp_path):
    mgr = TaskManager(tasks_dir=tmp_path / "tasks")
    blocker = mgr.create("Blocker", session_id="s1")
    blocked = mgr.create("Blocked", session_id="s1")
    ready = mgr.create("Ready", session_id="s1")
    done = mgr.create("Done", session_id="s1")

    mgr.update(blocked["id"], addBlockedBy=[blocker["id"]])
    mgr.update(done["id"], status="completed")

    ready_tasks = mgr.list_ready(session_id="s1")

    assert [t["id"] for t in ready_tasks] == [blocker["id"], ready["id"]]
```

- [ ] **Step 2: Update web parity expectation**

In `tests/test_web_workbench_parity.py`, change:

```python
assert {t["session_id"] for t in tasks} == {"s_current", "s_other"}
```

to:

```python
assert {t["session_id"] for t in tasks} == {"s_current"}
```

Add an explicit global/include test if needed:

```python
listed_global = client.get("/api/tasks?session_id=s_current&include_global=true")
assert listed_global.status_code == 200
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
pytest tests/test_task_manager_scope.py tests/test_web_workbench_parity.py -q
```

Expected: FAIL until `TaskManager` and API are updated.

---

### Task 6: Implement Task Scope, Ready Helpers, and API Filters

**Files:**
- Modify: `src/data_agent/session/task_manager.py`
- Modify: `src/data_agent/web/blueprints/tasks.py`

- [ ] **Step 1: Add ready helpers and strict scope**

Update `TaskManager`:

```python
def is_ready(self, task: dict) -> bool:
    task = self._normalize(dict(task))
    return task.get("status") == "pending" and not task.get("blockedBy")


def list_for_scope(self, session_id: str = "", project_name: str = "", include_global: bool = False) -> list[dict]:
    tasks = self.list_all()
    if not session_id and not project_name:
        return tasks

    scoped = [
        t for t in tasks
        if (session_id and t.get("session_id") == session_id)
        or (project_name and t.get("project_name") == project_name)
    ]
    if include_global:
        scoped.extend([
            t for t in tasks
            if not t.get("session_id") and not t.get("project_name")
        ])
    return scoped


def list_ready(self, session_id: str = "", project_name: str = "", include_global: bool = False) -> list[dict]:
    return [
        t for t in self.list_for_scope(session_id=session_id, project_name=project_name, include_global=include_global)
        if self.is_ready(t)
    ]
```

Update `format_list()` to pass `include_global=False` by default.

- [ ] **Step 2: Update API query parsing**

In `src/data_agent/web/blueprints/tasks.py`:

```python
def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}
```

Update `list_tasks()`:

```python
include_global = _truthy(request.args.get("include_global"))
ready_only = _truthy(request.args.get("ready_only"))
active_only = _truthy(request.args.get("active_only"))

if ready_only:
    tasks = mgr.list_ready(session_id=session_id, project_name=project_name, include_global=include_global)
elif session_id or project_name:
    tasks = mgr.list_for_scope(session_id=session_id, project_name=project_name, include_global=include_global)
else:
    tasks = mgr.list_all()

if active_only:
    tasks = [t for t in tasks if t.get("status") in ("pending", "in_progress")]

return jsonify(tasks)
```

- [ ] **Step 3: Run task/API tests**

Run:

```bash
pytest tests/test_task_manager_scope.py tests/test_web_workbench_parity.py tests/test_method_playbooks.py -q
```

Expected: PASS.

---

### Task 7: Update Frontend Polling Behavior

**Files:**
- Modify: `src/data_agent/web/static/js/app.js`
- Modify: `tests/test_web_overhaul.py` or add a static assertion in `tests/test_v91.py`

- [ ] **Step 1: Add polling interval policy**

In `app.js`, replace the binary active/slow logic with:

```javascript
        _desiredTaskPollMs() {
            if (!this.currentSessionId || this.currentSessionId === '_pending_') return 0;
            if (this.activeTasks.some(t => t.status === 'in_progress')) return 5000;
            if (this.activeTasks.some(t => t.status === 'pending')) return 30000;
            return 0;
        },
```

- [ ] **Step 2: Update interval reset**

Use a stored `_taskPollMs`:

```javascript
        _updateTaskPollInterval() {
            const desired = this._desiredTaskPollMs();
            if (this._taskPollMs === desired) return;
            clearInterval(this._taskPollInterval);
            this._taskPollInterval = null;
            this._taskPollMs = desired;
            if (desired > 0) {
                this._taskPollInterval = setInterval(() => {
                    if (!document.hidden && this.currentSessionId && this.currentSessionId !== '_pending_') {
                        this.loadTasks();
                    }
                }, desired);
            }
        },
```

Keep `loadTasks()` calls on init, session switch, visibility change, explicit refresh, and `task_update`.

- [ ] **Step 3: Add static frontend assertion**

Add or update a test:

```python
def test_task_polling_can_stop_when_no_active_tasks():
    js = Path("src/data_agent/web/static/js/app.js").read_text(encoding="utf-8")
    assert "_desiredTaskPollMs" in js
    assert "return 0;" in js
    assert "task_update" in js
```

- [ ] **Step 4: Run frontend/static tests**

Run:

```bash
pytest tests/test_web_overhaul.py tests/test_v91.py -q
```

Expected: PASS or update static assertions that intentionally depended on permanent 30-second polling.

---

### Task 8: Run Focused Regression Suite

**Files:**
- No source changes unless tests reveal a regression.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_intent_classification.py tests/test_method_playbooks.py tests/test_comprehensive_analysis_flow.py::TestConversationFlow tests/test_task_manager_scope.py tests/test_web_workbench_parity.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader quality tests**

Run:

```bash
pytest tests/test_golden_scenarios.py tests/test_execution_control.py tests/test_analysis_state_v2.py -q
```

Expected: PASS. If a golden scenario changes, confirm it is due to stricter analysis routing, not a loss of data-requirement behavior.

- [ ] **Step 3: Inspect current session regression manually**

Use a short script to verify the old session state remains explainable:

```bash
.venv\Scripts\python.exe -c "from data_agent.agent.intent import plan_turn_intent; text='Analyze revenue decline using D:\\Project\\Daily\\data\\orders.xlsx'; i=plan_turn_intent(text,''); print(i)"
```

Expected: `directed_analysis`, `pending_load`, and `load_then_analyze`.

---

### Task 9: Final Verification and Handoff

**Files:**
- No source changes.

- [ ] **Step 1: Check git diff**

Run:

```bash
git diff -- src/data_agent/agent/intent.py src/data_agent/agent/loop.py src/data_agent/agent/analysis_flow_controller.py src/data_agent/session/task_manager.py src/data_agent/web/blueprints/tasks.py src/data_agent/web/static/js/app.js tests
```

Expected: Only intended files changed.

- [ ] **Step 2: Summarize behavioral changes**

Include these points in the final handoff:

```text
- Clear analysis plus file references now starts as directed_analysis with pending_load.
- load_data success triggers same-turn replanning.
- Overview-only final answers are guarded for directed analysis.
- Task session scope is strict by default.
- Ready tasks are explicit.
- Frontend polling stops or slows when no active scoped tasks exist.
```

- [ ] **Step 3: Record any deferred work**

Mention deferred phase 2:

```text
- RuntimeJobManager
- event-sourced task/job updates
- worker ready handshake
- admin views for global tasks
```

