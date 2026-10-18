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
from tests.test_trusted_publication_semantics import engine


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
    """Unknown real units cannot inherit a bare model 'confirmed' flag.

    The old currency-positive status-only mechanism is retired by PUB-02/08.
    Current raw business confirmation establishes column meaning, not CNY.
    Fixed audit decisions below test composition only, not semantic quality.
    """
    def _snapshot(self,engine,confirm=False):
        import pandas as pd
        from tests.test_trusted_publication_runtime import request
        from tests.test_trusted_publication_semantics import execute
        from data_agent.agent.publication.runtime import snapshot_for_turn
        loop,cfg=engine
        loop.context.workspace.add("orders",pd.DataFrame({"amount":[10]*12}))
        request(loop,"计算金额并解释单位",{'kind': 'measurement', 'scope': {'datasets': ['orders'], 'metrics': ['amount'], 'quantity': 'sum'}},kind="result",purposes=["interpretation"])
        if confirm:
            from data_agent.agent.confirmation.runtime import build_action_registry,build_measurement_mapping_candidate
            from data_agent.agent.confirmation.service import ConfirmationService
            from data_agent.session.history import load_canonical_history
            h=load_canonical_history(loop.session_id)
            candidate=build_measurement_mapping_candidate(session_id=loop.session_id,turn_id="runtime_turn",workspace=loop.context.workspace,canonical_history=h,
                source_message_ref=h.messages[-1]["request_id"],exact_span="金额",dataset="orders",column="amount")
            service=ConfirmationService(cfg.sessions_resolved,action_registry=build_action_registry());service.request(candidate)
            service.respond(loop.session_id,candidate.confirmation_id,"raw",service.checkpoint(loop.session_id).version,"raw-choice")
        execute(loop,"describe_dataset",{"name":"orders"})
        snapshot=snapshot_for_turn(loop)
        claim=next(c for c in snapshot.as_dict()["claims"] if c["target"].get("metric")=="amount" and c["target"].get("statistic")=="sum")
        assert claim["value"]==120 and claim["unit"] is None
        return snapshot,claim

    def _answer(self,snapshot,claim,text,disposition,extra=None):
        from data_agent.agent.publication.service import PublicationService
        from data_agent.agent.publication.contracts import encode
        row=snapshot.as_dict()["requirements"][0]
        parts=[{"kind":"claim","ref":claim["id"]},{"kind":"text","purpose":"interpretation","text":text,"claim_refs":[claim["id"]]}]
        if extra:parts[0].update(extra)
        calls=[]
        def audit(q):
            calls.append(q)
            return {"schema":"publication_audit.v2","snapshot_digest":q["snapshot_digest"],"draft_digest":q["draft_digest"],
                "decisions":[{"part_id":p["part_id"],"disposition":disposition,"reason":"frozen original unit oracle","evidence_refs":p["requirement_ids"]+p["claim_refs"]} for p in q["parts"]]}
        answer=PublicationService(snapshot,auditor=audit).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,
            "sections":[{"requirement_ids":[row["id"]],"parts":parts}]})).as_dict()
        assert answer["source_snapshot"]["claims"]==snapshot.as_dict()["claims"]
        assert any(t["ref"]==claim["id"] and t["disposition"]=="accepted" for t in answer["render_trace"])
        return answer,calls

    def test_missing_unit_status_key_defaults_to_unknown_and_blocks_kuai(self,engine):
        snapshot,claim=self._snapshot(engine)
        answer,calls=self._answer(snapshot,claim,"当前订单合计约 120 块。","reject")
        assert len(calls)==1 and "120 块" not in answer["body"] and "单位未知" in answer["body"]
        answer,calls=self._answer(snapshot,claim,"当前订单合计约 120 块。","reject",{"unit":"CNY"})
        assert len(calls)==1 and any(i["code"]=="invalid_fields" and i["part_id"]=="s0p0" for i in answer["issues"])
        assert claim["unit"] is None and "120 块" not in answer["body"]

    def test_declared_unknown_blocks_currency_attachment(self,engine):
        snapshot,claim=self._snapshot(engine)
        answer,calls=self._answer(snapshot,claim,"合计 120 元。","reject")
        assert len(calls)==1 and "120 元" not in answer["body"]

    def test_confirmed_unit_allows_currency(self,engine):
        # Historical name retained; a real raw choice is not a currency grant.
        snapshot,claim=self._snapshot(engine,confirm=True)
        assert snapshot.as_dict()["confirmation_refs"][0]["response"]=="raw"
        answer,calls=self._answer(snapshot,claim,"合计 120 元。","reject",{"unit_status":"confirmed"})
        assert len(calls)==1 and any(i["code"]=="invalid_fields" and i["part_id"]=="s0p0" for i in answer["issues"])
        assert claim["unit"] is None and "120 元" not in answer["body"]

    def test_plain_number_without_currency_token_passes(self,engine):
        snapshot,claim=self._snapshot(engine)
        text="合计 120（单位未声明）。"
        answer,calls=self._answer(snapshot,claim,text,"accept")
        assert len(calls)==1 and text in answer["body"] and not answer["issues"]

    def test_non_currency_word_elements_do_not_trigger(self,engine):
        from tests.test_trusted_publication_runtime import request
        from data_agent.agent.publication.runtime import snapshot_for_turn
        from data_agent.agent.publication.service import PublicationService
        from data_agent.agent.publication.contracts import encode
        loop,_=engine
        request(loop,"说明数据列与数组元素的区别",kind="knowledge")
        snapshot=snapshot_for_turn(loop);row=snapshot.as_dict()["requirements"][0]
        text="示例数组包含 3 元素，与业务币种无关。"
        answer=PublicationService(snapshot).publish(encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,
            "sections":[{"requirement_ids":[row["id"]],"parts":[{"kind":"text","purpose":"knowledge","text":text,"claim_refs":[]}]}]})).as_dict()
        assert text in answer["body"] and answer["source_snapshot"]["claims"]==[]
        assert answer["audit_status"]=="not_applicable" and not answer["issues"]
