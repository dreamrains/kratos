"""Phase A systemic replay tests (Task 12).

The replay harness drives the REAL ``AgentLoop`` through the Tasks 6-11
pipeline using a scripted fake LLM. These four tests pin the contracts the
release gate relies on:

* Factor-analysis replay reaches the canonical analysis depth, converges to
  a terminal state, and publishes a Chinese, evidence-backed answer with at
  least one safe progress narration preceding it.
* Aggregate-profile replay cannot assert user-level dimensions the data
  does not support, and surfaces the missing-data boundary in the answer.
* Sandbox-heavy replay exercises preloaded imports and missing-dataset
  lookups without cascading through ``__import__``/``NoneType`` errors and
  stays inside the bounded identical-failure budget.
* Unicode replay survives a ``cp936`` console capture, keeping ``⚠️`` intact
  on both the persisted and the streamed/browser text paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the harness importable as ``replay_analysis_reliability``.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from replay_analysis_reliability import (  # noqa: E402
    run_deterministic_replay,
    run_sandbox_replay,
    run_unicode_replay,
)
from tests.fixtures.analysis_reliability import (  # noqa: E402
    build_aggregate_payment_frame,
    build_factor_relationship_frame,
    factor_relationship_prompt,
)
from tests.replay_assertions import assert_reliable_analysis_trace  # noqa: E402


def test_factor_session_replay_is_deep_bounded_and_publishable(tmp_path):
    result = run_deterministic_replay(
        frame=build_factor_relationship_frame(),
        prompt=factor_relationship_prompt(),
        root=tmp_path,
    )
    assert_reliable_analysis_trace(result.trace, require_inferential_attempt=True)
    assert result.completion_state in {"complete", "complete_with_limits"}
    assert result.evidence_records
    assert result.progress_events[0].sequence < result.final_answer_sequence
    assert result.final_answer.strip()
    assert result.final_answer_language == "zh"
    assert "Some requested analysis claims" not in result.final_answer


def test_aggregate_profile_replay_blocks_unavailable_user_claims(tmp_path):
    csv_root = tmp_path / "aggregate_data.csv"
    build_aggregate_payment_frame().to_csv(csv_root, index=False, encoding="utf-8-sig")
    from replay_analysis_reliability import _aggregate_responses, _AGGREGATE_FINAL_TEXT

    result = run_deterministic_replay(
        frame=build_aggregate_payment_frame(),
        prompt="请分析用户画像、复购和消费分布",
        responses=_aggregate_responses(csv_root),
        fallback_text=_AGGREGATE_FINAL_TEXT,
        root=tmp_path,
        session_id="aggregate_replay",
        project_name="aggregate_replay",
        dataset_name="aggregate_data",
    )
    assert "年龄" not in result.asserted_dimensions
    assert "个人复购" not in result.asserted_dimensions
    assert result.completion_state in {"complete_with_limits", "blocked_by_data"}
    assert "需要用户级字段" in result.final_answer


def test_sandbox_heavy_replay_has_no_import_or_none_cascade(tmp_path):
    result = run_sandbox_replay(tmp_path)
    # Negative: the sandbox boundary must not leak opaque cascades.
    assert "__import__ not found" not in result.serialized_trace
    assert "NoneType" not in result.serialized_trace
    # Positive: the failing run_python ACTUALLY executed inside the loop's
    # fallback budget and returned a STRUCTURED error token (Task 3), instead
    # of being silently blocked and leaving these assertions vacuously true.
    assert "dataset_not_found" in result.serialized_trace
    # The identical missing-dataset retry must be bounded (1..2): the lower
    # bound proves a real failure was traversed, the upper bound proves the
    # bounded-retry contract held.
    assert 1 <= result.max_identical_failure_attempts <= 2


def test_unicode_progress_replay_survives_cp936_and_keeps_browser_unicode(tmp_path):
    result = run_unicode_replay(tmp_path, console_encoding="cp936")
    assert result.turn_completed is True
    assert "⚠️" in result.persisted_text
    assert "⚠️" in result.browser_text
