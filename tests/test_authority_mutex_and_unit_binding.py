"""Codex review hardening (2026-09-21): mutex for plan authority, receipt-bound
unit enforcement.

1. Tool calls in one block execute in a ThreadPoolExecutor (loop.py, up to 3
   workers), so record_analysis_plan and task_create genuinely interleave. The
   plan-authority check-then-act must be serialized inside TaskManager, not
   left to sequential good luck.
2. The currency guard silently passed "120 块" because scopes carried no
   ``unit_status`` key at all: missing unit metadata must DEFAULT to unknown
   (receipt-bound fact pollution is blocking-grade, not a style advisory).
"""

from __future__ import annotations

import threading

import pytest

from data_agent.session.task_manager import task_manager


class TestPlanAuthorityMutex:
    def test_authority_guard_serializes_concurrent_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr(task_manager, "_dir", tmp_path / "tasks")
        monkeypatch.setattr(task_manager, "_next_id_val", 0)
        counter = {"inside": 0, "max": 0}
        lock = threading.Lock()

        def worker():
            with task_manager.authority_guard("s", ""):
                with lock:
                    counter["inside"] += 1
                    counter["max"] = max(counter["max"], counter["inside"])
                import time
                time.sleep(0.05)
                with lock:
                    counter["inside"] -= 1

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert counter["max"] == 1

    def test_concurrent_llm_plan_cannot_supersede_live_stage_plan(self, tmp_path, monkeypatch):
        monkeypatch.setattr(task_manager, "_dir", tmp_path / "tasks2")
        monkeypatch.setattr(task_manager, "_next_id_val", 0)
        # Establish a live stage plan first.
        stage_plan = task_manager.create_plan(
            session_id="race", goal="g", source="analysis_plan"
        )
        task_manager.create(
            "S1", session_id="race", plan_id=stage_plan["id"],
            analysis_plan_id="ap1", step_id="S1",
        )
        task_manager.start_next_ready_stage3c0b_task(session_id="race", project_name="")

        violations: list[str] = []

        def try_llm_plan(round_index: int) -> None:
            try:
                task_manager.create_plan(
                    session_id="race", goal=f"llm {round_index}", source="llm_plan"
                )
            except RuntimeError:
                return
            # If an llm plan was created, the live stage plan must have been
            # retired first; otherwise the supersede was a silent race.
            current = task_manager.get_active_plan_id("race", "")
            if current != stage_plan["id"] and task_manager.get(stage_plan and 1):
                pass  # active changed; verify below via invariant check
            violations.append(current)

        threads = [
            threading.Thread(target=try_llm_plan, args=(i,)) for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert task_manager.get_active_plan_id("race", "") == stage_plan["id"]


class TestUnitPollutionIsReceiptBound:
    def _issues(self, text: str, scopes: list[dict]):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from data_agent.agent.publication_synthesis import _currency_unit_issues
        return _currency_unit_issues(text, scopes)

    def test_missing_unit_status_key_defaults_to_unknown_and_blocks_kuai(self):
        issues = self._issues("当前订单合计约 120 块。", [{"tool": "aggregate"}])
        assert issues and issues[0]["code"] == "unconfirmed_currency_unit", issues

    def test_declared_unknown_blocks_currency_attachment(self):
        issues = self._issues("合计 120 元。", [{"tool": "aggregate", "unit_status": "unknown"}])
        assert issues, issues

    def test_confirmed_unit_allows_currency(self):
        issues = self._issues("合计 120 元。", [{"tool": "aggregate", "unit_status": "confirmed"}])
        assert issues == []

    def test_plain_number_without_currency_token_passes(self):
        issues = self._issues("合计 120（单位未声明）。", [{"tool": "aggregate"}])
        assert issues == []

    def test_non_currency_word_elements_do_not_trigger(self):
        issues = self._issues("数据含 3 元素列。", [{"tool": "aggregate"}])
        assert issues == [], issues
