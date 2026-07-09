# 黄金最终答案质量测量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible final-answer quality regression harness that drives the agent on real-data golden business questions and scores answers with two tiers — deterministic fatal gates plus an LLM-judge soft-dimension layer (absolute baseline + pairwise before/after).

**Architecture:** A measurement-only layer that reuses the existing trust substrate. Deterministic pieces (`answer_quality.py`) extract material claims from the answer and feed them to the existing `score_analysis_quality` rubric plus the agent's own `verification_reports` for fatal blockers. The LLM judge (`quality_judge.py`) scores five soft dimensions (rigor, insight depth, guidance, data explanation, direction expansion) via a dedicated judge client. A runner module (`golden_answer_runner.py`) drives the real `AgentLoop` on each manifest scenario, captures `final_text` + `AnalysisSessionState`, and evaluates. A CLI script writes auditable artifacts and manages a pinned baseline for pairwise regression. Nothing here enters the agent runtime decision path.

**Tech Stack:** Python, pytest, pandas, litellm (via existing `LLMClient`), existing `data_agent.agent` contracts (`AgentLoop`, `AnalysisSessionState`, `score_analysis_quality`, `build_user_data_brief`), `reference/test_doc` real-data fixtures.

## Global Constraints

- **Measurement layer only.** New modules must not be imported by `loop.py` / `synthesis_policy.py` / runtime synthesis. They are evaluation + offline-script only. (Spec §1, §3.)
- **No total score.** Soft dimensions stay separate; fatal blockers stay separate. No weighted sum. (Spec §5, evidence-synthesis decision.)
- **Two-tier hardness.** Fatal blockers block "claim delivery ready"; soft dimensions never block, only record before/after. (Spec §5.)
- **Judge isolation.** Judge uses a configurable `quality_judge_model`, default falls back to `MODEL_ID`; `temperature=0`; structured JSON output. (Spec §6.)
- **No auto-join.** Savings-card scenarios must not join by `user_id`; relationship evidence is diagnostic only. (Spec §4, §12.)
- **Runner not in CI by default.** Only deterministic meta-tests run under `pytest`; live agent + live judge are `skipif`-guarded. (Spec §8.)
- **Windows.** No `signal`-based timeouts; reuse thread-join timeout pattern if needed. (CLAUDE.md.)
- **Reuse before rebuilding.** Extend `score_analysis_quality`; reuse `LLMClient`, `load_data`, `build_user_data_brief`, the `run_scenario` harness pattern from `tests/test_golden_scenarios.py`. (Spec §11.)

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `tests/real_data/golden_answer_manifest.json` | Create | Declarative S1–S4 golden scenarios (files, business question, focus dims, fatal expectations). |
| `tests/real_data/scenario_manifest.json` | Modify | Replace deleted savings-card filenames so the readiness suite stays green. |
| `src/data_agent/config.py` | Modify | Add `quality_judge_model` setting. |
| `src/data_agent/llm/client.py` | Modify | Add optional `temperature` to `LLMClient`. |
| `.env.example` | Modify | Document `QUALITY_JUDGE_MODEL`. |
| `src/data_agent/agent/answer_quality.py` | Create | Deterministic: `SOFT_DIMENSIONS` rubric, `extract_material_claims`, `is_supported_by_evidence`, `evaluate_fatal`, `build_judge_context`. No LLM. |
| `src/data_agent/agent/quality_judge.py` | Create | LLM judge: judge client, prompt builders, `judge_absolute`, `judge_pairwise`, `_extract_json`. |
| `src/data_agent/agent/golden_answer_runner.py` | Create | Orchestration: `evaluate_answer` (fatal + soft), `drive_agent_for_scenario` (real loop + load_data), `run_golden_manifest`, baseline IO. |
| `scripts/run_golden_answer_quality.py` | Create | CLI: `generate` / `evaluate` / `--update-baseline`, writes artifacts. |
| `tests/real_data/test_golden_answer_quality.py` | Create | Deterministic meta-tests (fatal, judge stub, end-to-end fixtures) + `skipif` live smoke. |

---

## Task 1: Golden manifest + loader/validator

**Files:**
- Create: `tests/real_data/golden_answer_manifest.json`
- Create: `src/data_agent/agent/golden_answer_runner.py` (loader only this task)
- Test: `tests/real_data/test_golden_answer_quality.py`

**Interfaces:**
- Produces: `load_golden_manifest(path: Path) -> dict` and `GOLDEN_MANIFEST_SCHEMA = "golden_answer_scenarios.v1"` in `golden_answer_runner.py`. Raises `GoldenManifestError(ValueError)` on malformed input.

- [ ] **Step 1: Write the manifest file**

Create `tests/real_data/golden_answer_manifest.json`:

```json
{
  "schema_version": "golden_answer_scenarios.v1",
  "forbidden_auto_join_by": ["user_id"],
  "scenarios": [
    {
      "id": "savings_card_business_overview",
      "description": "Multi-file savings-card business overview; tests insight depth vs number description without joining.",
      "required_files": [
        "省钱卡订单.xlsx",
        "省钱卡0201到0510购卡用户付费数据.xlsx",
        "省钱卡代金券明细订单.xlsx",
        "省钱卡购卡前后订单.xlsx"
      ],
      "business_question": "省钱卡业务整体表现如何？购卡用户买卡前后消费有什么变化？代金券有没有拉动消费？整体是赚还是亏、值不值得继续推广？",
      "analysis_mode": "independent_then_synthesis",
      "soft_dimension_focus": ["rigor", "insight_depth", "guidance", "data_explanation", "direction_expansion", "synthesis"],
      "fatal_expectations": {
        "no_unsupported_material_claim": true,
        "no_invalid_relationship_use": true,
        "before_after_grain_must_match": true
      }
    },
    {
      "id": "game_a_multimetric_synthesis",
      "description": "Same-game different-metric synthesis across banner, IAP, rewarded video.",
      "required_files": [
        "游戏Abanner汇总数据.xlsx",
        "游戏A内购数据.xlsx",
        "游戏A激励视频汇总数据报表.xlsx"
      ],
      "business_question": "综合判断游戏A的banner、内购、激励视频这几种方式里，哪种推广/付费方式效果最好？依据是什么？",
      "analysis_mode": "independent_then_synthesis",
      "soft_dimension_focus": ["rigor", "insight_depth", "guidance", "data_explanation", "direction_expansion", "synthesis"],
      "fatal_expectations": {
        "no_unsupported_material_claim": true,
        "no_invalid_relationship_use": true
      }
    },
    {
      "id": "game_b_retention_depth",
      "description": "Single-file retention curve depth.",
      "required_files": ["游戏B留存.xlsx"],
      "business_question": "游戏B的留存曲线有什么特征和拐点？意味着什么？如果想改善留存，应该关注什么？",
      "analysis_mode": "independent",
      "soft_dimension_focus": ["rigor", "insight_depth", "guidance", "data_explanation", "direction_expansion"],
      "fatal_expectations": {
        "no_unsupported_material_claim": true
      }
    },
    {
      "id": "unrelated_files_false_join_prevention",
      "description": "Must not infer a join between unrelated datasets.",
      "required_files": ["游戏B留存.xlsx", "省钱卡订单.xlsx"],
      "business_question": "这两个文件能合起来一起分析吗？如果能，怎么结合；如果不能，为什么？",
      "analysis_mode": "independent",
      "soft_dimension_focus": ["rigor", "insight_depth"],
      "fatal_expectations": {
        "no_invalid_relationship_use": true
      }
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/real_data/test_golden_answer_quality.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_agent.agent.golden_answer_runner import (
    load_golden_manifest,
    GoldenManifestError,
)

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = next(
    (
        p
        for p in (
            WORKTREE_ROOT / "reference" / "test_doc",
            WORKTREE_ROOT.parents[1] / "reference" / "test_doc",
        )
        if p.is_dir()
    ),
    None,
)
MANIFEST = WORKTREE_ROOT / "tests" / "real_data" / "golden_answer_manifest.json"


def test_load_golden_manifest_valid():
    manifest = load_golden_manifest(MANIFEST)
    assert manifest["schema_version"] == "golden_answer_scenarios.v1"
    ids = [s["id"] for s in manifest["scenarios"]]
    assert ids == [
        "savings_card_business_overview",
        "game_a_multimetric_synthesis",
        "game_b_retention_depth",
        "unrelated_files_false_join_prevention",
    ]
    for scenario in manifest["scenarios"]:
        assert scenario["business_question"]
        assert isinstance(scenario["required_files"], list) and scenario["required_files"]


def test_load_golden_manifest_rejects_missing_schema(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    with pytest.raises(GoldenManifestError):
        load_golden_manifest(bad)


@pytest.mark.skipif(DATA_DIR is None, reason="reference/test_doc not found")
def test_golden_manifest_files_exist():
    manifest = load_golden_manifest(MANIFEST)
    for scenario in manifest["scenarios"]:
        for name in scenario["required_files"]:
            assert (DATA_DIR / name).is_file(), f"missing {name} for {scenario['id']}"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: data_agent.agent.golden_answer_runner`.

- [ ] **Step 4: Implement the loader**

Create `src/data_agent/agent/golden_answer_runner.py`:

```python
"""Golden final-answer quality measurement harness.

Measurement-only layer. Not imported by agent runtime synthesis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GOLDEN_MANIFEST_SCHEMA = "golden_answer_scenarios.v1"
ALLOWED_SOFT_DIMENSIONS = {
    "rigor",
    "insight_depth",
    "guidance",
    "data_explanation",
    "direction_expansion",
    "synthesis",
}


class GoldenManifestError(ValueError):
    pass


def load_golden_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GoldenManifestError(f"malformed golden manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise GoldenManifestError("golden manifest root must be an object")
    if manifest.get("schema_version") != GOLDEN_MANIFEST_SCHEMA:
        raise GoldenManifestError(
            f"golden manifest schema_version must be {GOLDEN_MANIFEST_SCHEMA}"
        )
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise GoldenManifestError("golden manifest scenarios must be a non-empty list")
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
            raise GoldenManifestError(f"scenario {index} requires a string id")
        required_files = scenario.get("required_files")
        if not isinstance(required_files, list) or not all(
            isinstance(name, str) and name for name in required_files
        ):
            raise GoldenManifestError(
                f"scenario {scenario['id']} has invalid required_files"
            )
        if not isinstance(scenario.get("business_question"), str) or not scenario["business_question"]:
            raise GoldenManifestError(
                f"scenario {scenario['id']} requires a business_question"
            )
        focus = scenario.get("soft_dimension_focus", [])
        if not isinstance(focus, list) or not set(focus).issubset(ALLOWED_SOFT_DIMENSIONS):
            raise GoldenManifestError(
                f"scenario {scenario['id']} has invalid soft_dimension_focus"
            )
    return manifest
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: PASS (4 tests; the `files_exist` test runs only when `reference/test_doc` is present).

- [ ] **Step 6: Commit**

```bash
git add tests/real_data/golden_answer_manifest.json tests/real_data/test_golden_answer_quality.py src/data_agent/agent/golden_answer_runner.py
git commit -m "feat(golden-quality): add golden answer manifest and loader"
```

---

## Task 2: Repair old readiness manifest's deleted savings-card references

**Why:** The user replaced the two old savings-card files; `tests/real_data/scenario_manifest.json` still names `省钱卡用户最近流水_20260511.xlsx` and `省钱卡订单_20260507.xlsx`, so `tests/real_data/test_multifile_real_data_scenarios.py` now fails (files missing).

**Files:**
- Modify: `tests/real_data/scenario_manifest.json`
- Test: `tests/real_data/test_multifile_real_data_scenarios.py` (existing)

**Interfaces:** None new. The two savings-card scenarios must reference existing files only.

- [ ] **Step 1: Confirm the existing test currently fails**

Run: `uv run pytest tests/real_data/test_multifile_real_data_scenarios.py -v`
Expected: FAIL — at least one scenario reports `status: missing_required_files` for the deleted names.

- [ ] **Step 2: Update the manifest**

In `tests/real_data/scenario_manifest.json`, replace the `savings_card_relationship_diagnostic` scenario's `required_files` with two of the new files that share `user_id` (preserving the relationship-diagnostic intent), and fix the `unrelated_files_false_join_prevention` scenario's deleted reference:

```json
{
  "id": "savings_card_relationship_diagnostic",
  "description": "Inspect savings-card relationship value and risk without materializing a join.",
  "required_files": [
    "省钱卡订单.xlsx",
    "省钱卡0201到0510购卡用户付费数据.xlsx"
  ],
  "analysis_mode": "relationship_diagnostic_only",
  "executed_join": false,
  "relationship_check": {
    "left_key": "user_id",
    "right_key": "user_id",
    "required_outputs": [
      "cardinality",
      "row_coverage",
      "distinct_key_coverage",
      "null_rate",
      "row_multiplier",
      "time_scope"
    ]
  }
},
```

And in `unrelated_files_false_join_prevention`, change `"省钱卡订单_20260507.xlsx"` to `"省钱卡订单.xlsx"`.

- [ ] **Step 3: Run the readiness test to verify it passes**

Run: `uv run pytest tests/real_data/test_multifile_real_data_scenarios.py -v`
Expected: PASS — all scenarios `ready_for_execution`, no missing files.

- [ ] **Step 4: Commit**

```bash
git add tests/real_data/scenario_manifest.json
git commit -m "fix(real-data): point readiness manifest at current savings-card files"
```

---

## Task 3: Config + LLMClient prerequisites for the judge

**Files:**
- Modify: `src/data_agent/config.py` (add `quality_judge_model`)
- Modify: `src/data_agent/llm/client.py` (add `temperature`)
- Modify: `.env.example` (document `QUALITY_JUDGE_MODEL`)
- Test: `tests/test_config_judge_model.py`

**Interfaces:**
- Produces: `AgentConfig.quality_judge_model: Optional[str]` (env `QUALITY_JUDGE_MODEL`, default `None`).
- Produces: `LLMClient(model_id=None, api_base=None, api_key=None, max_tokens=None, timeout=None, temperature=None)`; when `temperature is not None` it is added to the litellm kwargs.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_judge_model.py`:

```python
from __future__ import annotations

from unittest.mock import patch

from data_agent.config import AgentConfig


def test_quality_judge_model_field_defaults_none():
    cfg = AgentConfig()
    assert getattr(cfg, "quality_judge_model", None) is None


def test_llm_client_forwards_temperature():
    from data_agent.llm import client as client_module
    from types import SimpleNamespace

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        msg = SimpleNamespace(content="{}", tool_calls=None, reasoning_content="")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    with patch.object(client_module, "completion", fake_completion):
        c = client_module.LLMClient(model_id="test/model", temperature=0.0, max_tokens=10)
        try:
            # Temperature is captured at the completion() call site, before any
            # response parsing; swallow parse-time mismatches from the stub shape.
            c.chat(messages=[{"role": "user", "content": "hi"}], system="x")
        except Exception:
            pass
    assert captured.get("temperature") == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_judge_model.py -v`
Expected: FAIL — `quality_judge_model` attribute missing / `temperature` kwarg not forwarded.

- [ ] **Step 3: Add the config field**

In `src/data_agent/config.py`, in the LLM block (after the `max_tokens` Field), add:

```python
quality_judge_model: Optional[str] = Field(alias="QUALITY_JUDGE_MODEL", default=None)
```

- [ ] **Step 4: Add temperature to LLMClient**

In `src/data_agent/llm/client.py`, add `temperature` to `LLMClient.__init__` signature and store it:

```python
def __init__(
    self,
    model_id: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
    temperature: Optional[float] = None,
):
    cfg = get_config()
    self.model_id = model_id or cfg.model_id
    self.api_base = api_base or cfg.api_base
    self.api_key = api_key or cfg.api_key
    self.max_tokens = max_tokens or cfg.max_tokens
    self.timeout = timeout or self._DEFAULT_TIMEOUT
    self.temperature = temperature
```

Then in `_base_kwargs` (the method that builds the litellm kwargs), append:

```python
if self.temperature is not None:
    kwargs["temperature"] = self.temperature
```

(Place this alongside the existing kwargs assembly so it applies to every call path.)

- [ ] **Step 5: Document the env var**

In `.env.example`, under the `# LLM 配置` block, append:

```
# QUALITY_JUDGE_MODEL=                 # 质量评估专用模型，留空则复用 MODEL_ID
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_config_judge_model.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/data_agent/config.py src/data_agent/llm/client.py .env.example tests/test_config_judge_model.py
git commit -m "feat(config): add quality_judge_model and LLMClient temperature"
```

---

## Task 4: Deterministic answer-quality layer (rubric + fatal gates)

**Files:**
- Create: `src/data_agent/agent/answer_quality.py`
- Test: `tests/real_data/test_golden_answer_quality.py` (append)

**Interfaces:**
- Produces:
  - `SOFT_DIMENSIONS: dict[str, dict]` — dimension key → `{name, what, anchor_1, anchor_3, anchor_5}`.
  - `SCENARIO_EXTRA_DIMENSIONS: dict[str, dict]` — currently `{"synthesis": {...}}`.
  - `extract_material_claims(answer_text: str) -> list[dict]` — each `{"claim_key", "text", "material"}`.
  - `is_supported_by_evidence(claim_text: str, evidence_records: list[dict]) -> bool`.
  - `evaluate_fatal(answer_text: str, state) -> dict` — wraps `score_analysis_quality`; also folds in `state.verification_reports[-1]`. Returns `{"claim_delivery_ready", "global_publish_gate", "blockers", "dimensions"}`.
  - `build_judge_context(state, question: str) -> dict` — data brief + question for the judge (no raw rows).

- [ ] **Step 1: Write the failing tests**

Append to `tests/real_data/test_golden_answer_quality.py`:

```python
from data_agent.agent import answer_quality as aq


def test_soft_dimensions_complete():
    keys = set(aq.SOFT_DIMENSIONS)
    assert keys == {"rigor", "insight_depth", "guidance", "data_explanation", "direction_expansion"}
    for spec in aq.SOFT_DIMENSIONS.values():
        assert all(k in spec for k in ("name", "what", "anchor_1", "anchor_3", "anchor_5"))


def test_extract_material_claims_marks_numeric_sentences():
    text = "整体收入增长了20%。其中复购贡献最大。请注意数据范围。"
    claims = aq.extract_material_claims(text)
    material = [c for c in claims if c["material"]]
    non_material = [c for c in claims if not c["material"]]
    assert any("20%" in c["text"] for c in material)
    assert any("数据范围" in c["text"] for c in non_material)
    assert all("claim_key" in c and "text" in c for c in claims)


def test_is_supported_by_evidence():
    evidence = [{"claim": "复购贡献最大", "result_summary": "老客收入+18%"}]
    assert aq.is_supported_by_evidence("复购贡献最大", evidence) is True
    assert aq.is_supported_by_evidence("优惠券导致复购提升", evidence) is False


class _FakeState:
    def __init__(self, evidence, verification_reports=None):
        self.evidence_records = evidence
        self.verification_reports = verification_reports or []
        self.route_proposals = []
        self.cleaning_logs = []
        self.file_relationships = []
        self.data_understanding_bundles = []


def test_evaluate_fatal_blocks_unsupported_material_claim():
    state = _FakeState(evidence=[{"claim": "留存下降", "result_summary": "D7 较低"}])
    result = aq.evaluate_fatal(
        "买卡后消费提升了50%，是省钱卡直接导致的。", state
    )
    assert result["claim_delivery_ready"] is False
    assert any(b.startswith("unsupported_material_claim") for b in result["blockers"])


def test_evaluate_fatal_passes_when_claim_supported():
    state = _FakeState(evidence=[{"claim": "买卡后消费提升50%", "result_summary": "前后对比 +50%"}])
    result = aq.evaluate_fatal("买卡后消费提升了50%。", state)
    assert result["claim_delivery_ready"] is True
    assert result["blockers"] == []


def test_evaluate_fatal_folds_in_failed_agent_verification():
    state = _FakeState(
        evidence=[{"claim": "x", "result_summary": "x"}],
        verification_reports=[{"overall_status": "fail", "failed_count": 1, "downgraded_count": 0}],
    )
    result = aq.evaluate_fatal("x。", state)
    assert result["claim_delivery_ready"] is False
    assert "agent_verification_failed" in result["blockers"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: data_agent.agent.answer_quality`.

- [ ] **Step 3: Implement answer_quality.py**

Create `src/data_agent/agent/answer_quality.py`:

```python
"""Deterministic answer-quality measurement primitives (no LLM).

Measurement-only. Extends the existing analysis-quality rubric with
answer-text claim extraction and agent-verification folding.
"""

from __future__ import annotations

import re
from typing import Any

from data_agent.agent.analysis_quality_rubric import score_analysis_quality

SOFT_DIMENSIONS: dict[str, dict[str, str]] = {
    "rigor": {
        "name": "严谨与可信",
        "what": "结论可辩护、证据充分、不夸大、主动声明局限与口径",
        "anchor_1": "结论缺证据支撑，或含未声明的强断言/因果夸大",
        "anchor_3": "主要结论有证据，但对局限/口径交代不充分",
        "anchor_5": "每个关键结论可辩护，主动声明数据局限与口径陷阱（如前后对比不能排除自然增长）",
    },
    "insight_depth": {
        "name": "洞察深度",
        "what": "超越数值描述，给出业务含义、机制假设、横向对比",
        "anchor_1": "基本是数值罗列与描述，缺少业务解读",
        "anchor_3": "对部分数值有解读，但缺乏机制或对比",
        "anchor_5": "给出业务机制/因果假设，并结合横向对比与异常点",
    },
    "guidance": {
        "name": "引导与可行动性",
        "what": "明确的建议、下一步与决策含义",
        "anchor_1": "没有可行动建议",
        "anchor_3": "有方向性建议但不够具体或可执行",
        "anchor_5": "给出具体、可执行、与决策直接挂钩的建议",
    },
    "data_explanation": {
        "name": "数据说明清晰度",
        "what": "数值/口径/图表解释清楚，讲清含义而非堆数",
        "anchor_1": "堆砌数字，不解释含义或口径",
        "anchor_3": "解释了部分数字，但口径/单位/时间范围交代不全",
        "anchor_5": "数值、口径、单位、时间范围交代清楚，并与结论对应",
    },
    "direction_expansion": {
        "name": "分析方向拓展",
        "what": "主动提出值得继续深挖的分析方向",
        "anchor_1": "没有提出后续分析方向",
        "anchor_3": "提出了方向但宽泛或不切题",
        "anchor_5": "提出具体、切题、能带来新决策价值的深挖方向",
    },
}

SCENARIO_EXTRA_DIMENSIONS: dict[str, dict[str, str]] = {
    "synthesis": {
        "name": "多文件综合性",
        "what": "把多个文件/指标的发现串成连贯的业务图景",
        "anchor_1": "各文件结论各自孤立，没有综合",
        "anchor_3": "有简单串联，但缺乏整合判断",
        "anchor_5": "跨文件口径对齐，给出整合的业务判断与边界",
    }
}

_SENTENCE_SPLIT = re.compile(r"[^。！？\n]+[。！？]?")
# Terms that, when present, make a sentence a "material" claim.
_MATERIAL_HINTS = re.compile(r"\d|上升|下降|增长|降低|比|高于|低于|导致|因为|由于|主要|贡献|建议|应该|值得|推荐")


def extract_material_claims(answer_text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, raw in enumerate(_SENTENCE_SPLIT.findall(answer_text or "")):
        text = raw.strip()
        if not text:
            continue
        material = bool(_MATERIAL_HINTS.search(text))
        claims.append({"claim_key": f"claim_{index + 1}", "text": text, "material": material})
    return claims


def _char_bigrams(text: str) -> set[str]:
    chars = re.sub(r"[\s0-9，。、！？：；,.!?;:\"'()\[\]]", "", text or "")
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[i : i + 2] for i in range(len(chars) - 1)}


def is_supported_by_evidence(claim_text: str, evidence_records: list[dict[str, Any]]) -> bool:
    # Character-bigram overlap is robust for Chinese without word segmentation
    # (handles particle differences like 提升 vs 提升了).
    claim_ng = _char_bigrams(claim_text)
    if not claim_ng:
        return False
    for record in evidence_records or []:
        hay = " ".join(
            str(record.get(field, ""))
            for field in ("claim", "result_summary", "metrics", "method")
        )
        hay_ng = _char_bigrams(hay)
        if hay_ng and len(claim_ng & hay_ng) / len(claim_ng) >= 0.4:
            return True
    return False


def _relationship_uses_from_state(state) -> list[dict[str, Any]]:
    uses: list[dict[str, Any]] = []
    for index, rel in enumerate(getattr(state, "file_relationships", []) or []):
        uses.append(
            {
                "relationship_id": str(rel.get("relationship_id") or f"relationship_{index + 1}"),
                "used_for_claim": bool(rel.get("used_for_claim")),
                "validation_status": str(rel.get("validation_status") or rel.get("status") or "unknown"),
                "time_scope_compatible": rel.get("time_scope_compatible"),
            }
        )
    return uses


def evaluate_fatal(answer_text: str, state) -> dict[str, Any]:
    claims_in = [
        {
            "claim_key": c["claim_key"],
            "material": c["material"],
            "supported": is_supported_by_evidence(c["text"], getattr(state, "evidence_records", []) or [])
            if c["material"]
            else True,
        }
        for c in extract_material_claims(answer_text)
    ]
    result = score_analysis_quality(
        claims=claims_in,
        relationship_uses=_relationship_uses_from_state(state),
    )
    blockers = list(result.get("blockers") or [])
    reports = getattr(state, "verification_reports", []) or []
    if reports and reports[-1].get("overall_status") == "fail":
        blockers.append("agent_verification_failed")
    unique = list(dict.fromkeys(blockers))
    ready = not unique
    result["blockers"] = unique
    result["claim_delivery_ready"] = ready
    result["global_publish_gate"] = ready
    return result


def build_judge_context(state, question: str) -> dict[str, Any]:
    bundles = getattr(state, "data_understanding_bundles", []) or []
    from data_agent.agent.data_understanding import build_user_data_brief

    brief = build_user_data_brief(bundles[-1]) if bundles else {"datasets": [], "relationships": []}
    return {"question": question, "data_brief": brief}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/answer_quality.py tests/real_data/test_golden_answer_quality.py
git commit -m "feat(golden-quality): deterministic answer-quality rubric and fatal gates"
```

---

## Task 5: LLM judge (absolute + pairwise)

**Files:**
- Create: `src/data_agent/agent/quality_judge.py`
- Test: `tests/real_data/test_golden_answer_quality.py` (append)

**Interfaces:**
- Produces:
  - `judge_absolute(answer_text, question, data_brief, dimensions, client=None) -> dict[str, dict]` — `{dim_key: {"score": 1-5, "rationale": str}}`. Returns `{}` on failure.
  - `judge_pairwise(baseline_answer, new_answer, question, data_brief, dimensions, client=None) -> dict[str, dict]` — `{dim_key: {"verdict": "better"|"same"|"worse", "rationale": str}}`.
  - Both accept an injected `client` (for tests); default `_get_judge_client()`.

- [ ] **Step 1: Write the failing tests (stub client)**

Append to `tests/real_data/test_golden_answer_quality.py`:

```python
from data_agent.agent import quality_judge as qj


class _StubClient:
    def __init__(self, payload: str):
        self._payload = payload

    def chat(self, messages, tools=None, system=None):
        from data_agent.llm.client import Response

        return Response(text=self._payload)


def test_judge_absolute_parses_scores(monkeypatch):
    payload = '{"insight_depth": {"score": 4, "rationale": "解读到位"}, "rigor": {"score": 3, "rationale": "口径略缺"}}'
    out = qj.judge_absolute(
        answer_text="买卡后消费+50%，主要来自复购。",
        question="省钱卡表现如何？",
        data_brief={"datasets": [], "relationships": []},
        dimensions=["insight_depth", "rigor"],
        client=_StubClient(payload),
    )
    assert out["insight_depth"]["score"] == 4
    assert out["rigor"]["score"] == 3


def test_judge_absolute_returns_empty_on_garbage():
    out = qj.judge_absolute(
        answer_text="x",
        question="q",
        data_brief={"datasets": []},
        dimensions=["insight_depth"],
        client=_StubClient("not json at all"),
    )
    assert out == {}


def test_judge_pairwise_parses_verdicts():
    payload = '{"insight_depth": {"verdict": "worse", "rationale": "新答案更浅"}}'
    out = qj.judge_pairwise(
        baseline_answer="深答案",
        new_answer="浅答案",
        question="q",
        data_brief={"datasets": []},
        dimensions=["insight_depth"],
        client=_StubClient(payload),
    )
    assert out["insight_depth"]["verdict"] == "worse"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: data_agent.agent.quality_judge`.

- [ ] **Step 3: Implement quality_judge.py**

Create `src/data_agent/agent/quality_judge.py`:

```python
"""LLM judge for golden answer soft dimensions.

Measurement-only. Uses a configurable judge model at temperature 0 and
parses structured JSON. Mirrors the one-shot pattern in llm_intent.py.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from data_agent.agent.answer_quality import SOFT_DIMENSIONS, SCENARIO_EXTRA_DIMENSIONS

_judge_client: Optional[Any] = None


def _all_dimension_specs() -> dict[str, dict[str, str]]:
    merged = dict(SOFT_DIMENSIONS)
    merged.update(SCENARIO_EXTRA_DIMENSIONS)
    return merged


def _get_judge_client():
    global _judge_client
    if _judge_client is None:
        from data_agent.config import get_config
        from data_agent.llm.client import LLMClient

        cfg = get_config()
        _judge_client = LLMClient(
            model_id=cfg.quality_judge_model,  # None -> default MODEL_ID
            max_tokens=800,
            temperature=0.0,
        )
    return _judge_client


def _extract_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _rubric_block(dimensions: list[str]) -> str:
    specs = _all_dimension_specs()
    lines = []
    for key in dimensions:
        spec = specs.get(key)
        if not spec:
            continue
        lines.append(
            f"- {key}（{spec['name']}）: {spec['what']}。"
            f"1分={spec['anchor_1']}；3分={spec['anchor_3']}；5分={spec['anchor_5']}。"
        )
    return "\n".join(lines)


_SYSTEM = (
    "你是一位资深数据分析评审。只返回 JSON，不要任何额外文字。"
    "评估的是面向业务决策的中文数据分析最终答案的质量。"
)


def _absolute_user_prompt(answer_text, question, data_brief, dimensions) -> str:
    return (
        f"业务问题：{question}\n"
        f"数据概况（非原始行）：{json.dumps(data_brief, ensure_ascii=False)}\n"
        f"待评答案：\n{answer_text}\n\n"
        f"按以下维度逐项打 1-5 分（整数），并给一句话理由。\n"
        f"{_rubric_block(dimensions)}\n"
        f'只返回 JSON，形如 {{"维度key": {{"score": 1, "rationale": "..."}}}}。'
    )


def _pairwise_user_prompt(baseline_answer, new_answer, question, data_brief, dimensions) -> str:
    return (
        f"业务问题：{question}\n"
        f"数据概况（非原始行）：{json.dumps(data_brief, ensure_ascii=False)}\n"
        f"答案A（baseline）：\n{baseline_answer}\n\n"
        f"答案B（new）：\n{new_answer}\n\n"
        f"按以下维度逐项判断 B 相对 A 是更好/持平/更差，并给一句话理由。\n"
        f"{_rubric_block(dimensions)}\n"
        f'只返回 JSON，形如 {{"维度key": {{"verdict": "better|same|worse", "rationale": "..."}}}}。'
    )


def _judge(user_prompt: str, client) -> dict[str, dict]:
    cli = client or _get_judge_client()
    try:
        resp = cli.chat(messages=[{"role": "user", "content": user_prompt}], system=_SYSTEM)
    except Exception:
        return {}
    parsed = _extract_json(getattr(resp, "text", "") or "")
    if not isinstance(parsed, dict):
        return {}
    return {str(k): v for k, v in parsed.items() if isinstance(v, dict)}


def judge_absolute(answer_text, question, data_brief, dimensions, client=None) -> dict[str, dict]:
    return _judge(_absolute_user_prompt(answer_text, question, data_brief, dimensions), client)


def judge_pairwise(baseline_answer, new_answer, question, data_brief, dimensions, client=None) -> dict[str, dict]:
    return _judge(_pairwise_user_prompt(baseline_answer, new_answer, question, data_brief, dimensions), client)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/quality_judge.py tests/real_data/test_golden_answer_quality.py
git commit -m "feat(golden-quality): LLM judge for absolute and pairwise soft dimensions"
```

---

## Task 6: Orchestration — evaluate_answer + agent driver + baseline IO

**Files:**
- Modify: `src/data_agent/agent/golden_answer_runner.py` (add functions)
- Test: `tests/real_data/test_golden_answer_quality.py` (append)

**Interfaces:**
- Produces:
  - `evaluate_answer(answer_text, state, question, dimensions, *, baseline_answer=None, judge_client=None) -> dict` — returns `{"fatal": {...}, "soft": {"absolute": {...}, "pairwise": {...} or None}}`.
  - `drive_agent_for_scenario(scenario, data_dir, *, client=None) -> tuple[str, AnalysisSessionState]` — loads files via `load_data`, runs `loop.run_turn(business_question)`, returns `(final_text, state)`.
  - `run_golden_manifest(manifest_path, data_dir, output_root, *, mode="generate", baseline_dir=None, judge_client=None, agent_client=None) -> Path` — full run; writes `results.json`; returns result path.
  - `read_baseline(baseline_dir, scenario_id) -> Optional[str]`; `write_baseline(baseline_dir, scenario_id, answer_text) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/real_data/test_golden_answer_quality.py`:

```python
from data_agent.agent import golden_answer_runner as gar


def test_evaluate_answer_composes_fatal_and_soft():
    state = _FakeState(evidence=[{"claim": "买卡后消费提升50%", "result_summary": "前后对比 +50%"}])
    payload = '{"insight_depth": {"score": 2, "rationale": "基本是数值描述"}}'
    out = gar.evaluate_answer(
        answer_text="买卡后消费提升了50%。",
        state=state,
        question="省钱卡表现？",
        dimensions=["insight_depth"],
        judge_client=_StubClient(payload),
    )
    assert out["fatal"]["claim_delivery_ready"] is True
    assert out["soft"]["absolute"]["insight_depth"]["score"] == 2
    assert out["soft"]["pairwise"] is None


def test_evaluate_answer_pairwise_when_baseline_given():
    state = _FakeState(evidence=[{"claim": "x", "result_summary": "x"}])
    payload = '{"insight_depth": {"verdict": "worse", "rationale": "更浅"}}'
    out = gar.evaluate_answer(
        answer_text="新答案",
        state=state,
        question="q",
        dimensions=["insight_depth"],
        baseline_answer="旧答案",
        judge_client=_StubClient(payload),
    )
    assert out["soft"]["pairwise"]["insight_depth"]["verdict"] == "worse"


def test_baseline_roundtrip(tmp_path):
    assert gar.read_baseline(tmp_path, "s1") is None
    gar.write_baseline(tmp_path, "s1", "旧答案")
    assert gar.read_baseline(tmp_path, "s1") == "旧答案"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: FAIL — `evaluate_answer` / `read_baseline` not defined.

- [ ] **Step 3: Implement the orchestration**

Append to `src/data_agent/agent/golden_answer_runner.py`:

```python
import uuid
from datetime import datetime, timezone

from data_agent.agent.answer_quality import evaluate_fatal, build_judge_context
from data_agent.agent.quality_judge import judge_absolute, judge_pairwise


def evaluate_answer(
    answer_text: str,
    state,
    question: str,
    dimensions: list[str],
    *,
    baseline_answer: str | None = None,
    judge_client=None,
) -> dict[str, Any]:
    fatal = evaluate_fatal(answer_text, state)
    context = build_judge_context(state, question)
    data_brief = context["data_brief"]
    soft: dict[str, Any] = {
        "absolute": judge_absolute(answer_text, question, data_brief, dimensions, client=judge_client),
        "pairwise": None,
    }
    if baseline_answer is not None:
        soft["pairwise"] = judge_pairwise(
            baseline_answer, answer_text, question, data_brief, dimensions, client=judge_client
        )
    return {"fatal": fatal, "soft": soft}


def read_baseline(baseline_dir: Path, scenario_id: str) -> str | None:
    path = baseline_dir / f"{scenario_id}.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def write_baseline(baseline_dir: Path, scenario_id: str, answer_text: str) -> None:
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / f"{scenario_id}.txt").write_text(answer_text, encoding="utf-8")


def drive_agent_for_scenario(scenario: dict[str, Any], data_dir: Path, *, client=None) -> tuple[str, Any]:
    from data_agent.tools import discover_tools  # ensure tools registered
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.analysis_state import load_analysis_state
    from data_agent.session.workspace import workspace
    from data_agent.tools.data_io import load_data

    discover_tools()
    project_name = f"golden_{scenario['id']}"
    session_id = uuid.uuid4().hex[:12]
    loop = AgentLoop(client=client, session_id=session_id, project_name=project_name)
    with use_agent_context(loop.context):
        for index, name in enumerate(scenario["required_files"]):
            load_data(str((data_dir / name).resolve()), name=f"{project_name}_ds{index}")
        final_text = loop.run_turn(scenario["business_question"])
    state = load_analysis_state(session_id, project_name)
    return final_text, state


def run_golden_manifest(
    manifest_path: Path,
    data_dir: Path,
    output_root: Path,
    *,
    mode: str = "generate",
    baseline_dir: Path | None = None,
    judge_client=None,
    agent_client=None,
) -> Path:
    manifest = load_golden_manifest(manifest_path)
    generated_at = datetime.now(timezone.utc)
    scenario_results: list[dict[str, Any]] = []
    for scenario in manifest["scenarios"]:
        missing = [n for n in scenario["required_files"] if not (data_dir / n).is_file()]
        if missing:
            scenario_results.append({"id": scenario["id"], "status": "missing_required_files", "missing_files": missing})
            continue
        if mode == "generate":
            answer_text, state = drive_agent_for_scenario(scenario, data_dir, client=agent_client)
        else:
            raise GoldenManifestError("evaluate mode requires stored answers; use the CLI evaluator")
        baseline = read_baseline(baseline_dir, scenario["id"]) if baseline_dir else None
        evaluation = evaluate_answer(
            answer_text,
            state,
            scenario["business_question"],
            scenario.get("soft_dimension_focus", []),
            baseline_answer=baseline,
            judge_client=judge_client,
        )
        scenario_results.append(
            {
                "id": scenario["id"],
                "status": "evaluated",
                "question": scenario["business_question"],
                "answer_text": answer_text,
                "evaluation": evaluation,
            }
        )
    result = {
        "schema_version": "golden_quality_results.v1",
        "generated_at": generated_at.isoformat(),
        "mode": mode,
        "manifest": str(manifest_path.resolve()),
        "data_dir": str(data_dir.resolve()),
        "scenarios": scenario_results,
    }
    result_dir = output_root / generated_at.strftime("%Y%m%dT%H%M%S.%fZ")
    result_dir.mkdir(parents=True, exist_ok=False)
    result_path = result_dir / "results.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/golden_answer_runner.py tests/real_data/test_golden_answer_quality.py
git commit -m "feat(golden-quality): answer evaluation, agent driver, and baseline IO"
```

---

## Task 7: CLI runner script

**Files:**
- Create: `scripts/run_golden_answer_quality.py`
- Test: `tests/real_data/test_golden_answer_quality.py` (append a CLI smoke)

**Interfaces:** CLI flags `--manifest`, `--data-dir`, `--output-root`, `--baseline-dir`, `--update-baseline`. `generate` drives the agent and writes `results.json`; `--update-baseline` also writes each scenario's answer into `--baseline-dir`.

- [ ] **Step 1: Write the failing test (CLI smoke, skipif data)**

Append to `tests/real_data/test_golden_answer_quality.py`:

```python
import subprocess
import sys


@pytest.mark.skipif(DATA_DIR is None, reason="reference/test_doc not found")
def test_cli_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.run_golden_answer_quality", "--help"],
        cwd=WORKTREE_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--manifest" in proc.stdout
    assert "--update-baseline" in proc.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py::test_cli_help_exits_zero -v`
Expected: FAIL — module not found / no `--update-baseline`.

- [ ] **Step 3: Implement the CLI**

Create `scripts/run_golden_answer_quality.py`:

```python
"""Run golden final-answer quality measurement.

generate: drive the agent on each golden scenario, evaluate, write artifacts.
--update-baseline: also persist each scenario answer into --baseline-dir.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MANIFEST = ROOT / "tests" / "real_data" / "golden_answer_manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "golden-quality"
DEFAULT_BASELINE_DIR = ROOT / "artifacts" / "golden-quality" / "baseline"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--update-baseline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    from data_agent.agent.golden_answer_runner import (
        load_golden_manifest,
        run_golden_manifest,
        write_baseline,
    )

    result_path = run_golden_manifest(
        manifest_path=args.manifest,
        data_dir=args.data_dir,
        output_root=args.output_root,
        mode="generate",
        baseline_dir=args.baseline_dir if args.update_baseline else None,
    )
    if args.update_baseline:
        manifest = load_golden_manifest(args.manifest)
        run = json.loads(result_path.read_text(encoding="utf-8"))
        ids_present = {s["id"] for s in manifest["scenarios"]}
        for scenario in run["scenarios"]:
            if scenario.get("status") == "evaluated" and scenario["id"] in ids_present:
                write_baseline(args.baseline_dir, scenario["id"], scenario["answer_text"])
    print(result_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py::test_cli_help_exits_zero -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_golden_answer_quality.py tests/real_data/test_golden_answer_quality.py
git commit -m "feat(golden-quality): CLI runner with generate and baseline update"
```

---

## Task 8: Regression meta-tests (deterministic, end-to-end fixtures)

**Goal:** A small deterministic suite that ties fatal + soft + pairwise together on fixture answers, so a future code change that weakens the evaluator is caught without a live LLM. Also one `skipif` live smoke that runs the real pipeline on one scenario.

**Files:**
- Modify: `tests/real_data/test_golden_answer_quality.py` (append)

- [ ] **Step 1: Write the fixture-driven regression tests**

Append:

```python
def test_shallow_answer_scores_low_on_insight_depth():
    state = _FakeState(evidence=[{"claim": "消费提升50%", "result_summary": "+50%"}])
    shallow = "买卡后消费提升了50%。代金券使用1075次。订单71单。"
    payload = '{"insight_depth": {"score": 1, "rationale": "纯数值描述"}}'
    out = gar.evaluate_answer(
        shallow, state, "省钱卡表现？", ["insight_depth"], judge_client=_StubClient(payload)
    )
    assert out["soft"]["absolute"]["insight_depth"]["score"] == 1


def test_unsupported_causal_claim_is_fatal():
    state = _FakeState(evidence=[{"claim": "留存", "result_summary": "留存下降"}])
    out = gar.evaluate_answer(
        "省钱卡直接导致了复购提升30%。", state, "q", ["insight_depth"],
        judge_client=_StubClient('{"insight_depth": {"score": 5, "rationale": "x"}}'),
    )
    assert out["fatal"]["claim_delivery_ready"] is False


def test_pairwise_detects_regression():
    state = _FakeState(evidence=[{"claim": "x", "result_summary": "x"}])
    out = gar.evaluate_answer(
        "浅答案", state, "q", ["insight_depth"],
        baseline_answer="深答案",
        judge_client=_StubClient('{"insight_depth": {"verdict": "worse", "rationale": "新答案更浅"}}'),
    )
    assert out["soft"]["pairwise"]["insight_depth"]["verdict"] == "worse"


@pytest.mark.skipif(
    DATA_DIR is None or not __import__("data_agent.config", fromlist=["get_config"]).get_config().api_key,
    reason="reference/test_doc or API_KEY not configured",
)
def test_live_smoke_single_scenario(tmp_path):
    """Live LLM smoke: drives the real agent on one scenario. Not run in default CI."""
    manifest = load_golden_manifest(MANIFEST)
    scenario = manifest["scenarios"][2]  # game_b_retention_depth (single file, cheapest)
    answer_text, state = gar.drive_agent_for_scenario(scenario, DATA_DIR)
    assert answer_text
    out = gar.evaluate_answer(
        answer_text, state, scenario["business_question"], scenario["soft_dimension_focus"]
    )
    assert "fatal" in out and "soft" in out
    assert isinstance(out["soft"]["absolute"], dict)
```

- [ ] **Step 2: Run the deterministic subset**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py -v -k "not live_smoke"`
Expected: PASS (all deterministic tests).

- [ ] **Step 3: Verify the live smoke is correctly skipped by default**

Run: `uv run pytest tests/real_data/test_golden_answer_quality.py::test_live_smoke_single_scenario -v`
Expected: SKIPPED (no API key in default env), not collected-error.

- [ ] **Step 4: Run the full real_data + golden subset together (regression)**

Run: `uv run pytest tests/real_data/ tests/test_golden_scenarios.py -v -k "not live_smoke"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/real_data/test_golden_answer_quality.py
git commit -m "test(golden-quality): deterministic regression fixtures and live smoke gate"
```

---

## Execution Order

Tasks are sequential: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Task 2 (manifest repair) can run in parallel with 3–5 if desired, since it touches only the old readiness manifest and its own existing test.

## Completion Criteria

- `tests/real_data/test_golden_answer_quality.py` deterministic tests all green; live smoke skips cleanly when unconfigured.
- `tests/real_data/test_multifile_real_data_scenarios.py` green again (manifest repaired).
- `scripts/run_golden_answer_quality.py --help` works; a live `generate` run on ≥1 scenario produces `artifacts/golden-quality/<ts>/results.json` with schema `golden_quality_results.v1`.
- No new src module is imported by `loop.py` / `synthesis_policy.py` / runtime synthesis (non-slippage: `rg "import.*golden_answer_runner|import.*quality_judge|import.*answer_quality" src/data_agent/agent/loop.py src/data_agent/agent/synthesis_policy.py` returns nothing).
- Savings-card scenarios never auto-join by `user_id`.

## Self-Review Notes

- **Spec coverage:** §4 scenarios → Task 1 manifest; §5.1 fatal gates → Task 4 (`evaluate_fatal` reuses `score_analysis_quality` + agent verification); §5.2 soft dimensions → Task 4 rubric + Task 5 judge; §6 judge mechanism → Task 5 + Task 3 prerequisites; §7 runner generate/evaluate/baseline → Tasks 6–7; §8 non-determinism → temp=0 (Task 3) + pairwise relative judgment (Task 5) + skipif gating (Task 8); §9 meta-tests → Task 8; §10 decision triggers are documentation (spec), not code.
- **evaluate mode:** `run_golden_manifest` raises on `mode="evaluate"` in-process; full evaluate-from-stored-answers is intentionally deferred (generate covers regression needs). The CLI exposes generate + `--update-baseline` only. This matches spec §7.2 (evaluate is a lighter mode) without over-building.
- **Type consistency:** `evaluate_answer` returns `{"fatal", "soft": {"absolute", "pairwise"}}`; `results.json` scenarios embed that under `evaluation`; `quality_judge` returns `{dim: {score|verdict, rationale}}`; `SOFT_DIMENSIONS` keys match manifest `soft_dimension_focus` values. Verified consistent.
