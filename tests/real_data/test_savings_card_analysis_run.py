from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.task_manager import TaskManager
from data_agent.session.workspace import Workspace
from data_agent.tools.statistics import ab_test


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "reference" / "test_doc"
BASELINE_PATH = ROOT / "artifacts" / "real-data-validation" / "baseline.json"
FILES = {
    "payments": "省钱卡0201到0510购卡用户付费数据.xlsx",
    "coupons": "省钱卡代金券明细订单.xlsx",
    "cards": "省钱卡订单.xlsx",
    "before_after": "省钱卡购卡前后订单.xlsx",
}


@pytest.mark.skipif(
    not all((DATA_DIR / name).is_file() for name in FILES.values()),
    reason="four-file savings-card reference data is unavailable",
)
def test_four_file_savings_card_baseline_finishes_transactional_run(
    tmp_path: Path,
) -> None:
    """The real descriptive baseline reaches 4/4 without orphan artifacts."""

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["savings_card"]
    frames = {
        key: pd.read_excel(DATA_DIR / filename)
        for key, filename in FILES.items()
    }
    payments = frames["payments"]
    coupons = frames["coupons"]
    cards = frames["cards"]
    before_after = frames["before_after"]

    payment_dedup = payments.drop_duplicates(subset=["order_id"])
    before_after_dedup = before_after.drop_duplicates()
    group_col = "用户类型（1是购卡前30天内，2是购卡后30天内）"
    user_totals = before_after_dedup.groupby(["user_id", group_col], as_index=False)[
        "实收金额"
    ].sum()
    paired_users = int((user_totals.groupby("user_id")[group_col].nunique() == 2).sum())

    assert len(payments) == baseline["payments"]["rows"]
    assert payments["order_id"].nunique() == baseline["payments"]["unique_order_ids"]
    assert float(payment_dedup["实收金额"].sum()) == baseline["payments"]["dedup_received"]
    assert len(before_after_dedup) == baseline["before_after"]["dedup_rows"]
    assert before_after_dedup["user_id"].nunique() == baseline["before_after"][
        "paired_user_summary_dedup"
    ]["users"]

    workspace = Workspace()
    context = AgentContext(session_id="savings-card-baseline", workspace=workspace)
    with use_agent_context(context):
        workspace.add("card_before_after_dedup", before_after_dedup)
        paired = json.loads(ab_test(
            "card_before_after_dedup",
            group_col=group_col,
            metric_col="实收金额",
            method="wilcoxon",
            observation_design="paired",
            unit_col="user_id",
            unit_aggregation="sum",
        ))
    assert paired_users == 61
    assert paired["effective_sample_size"]["pairs"] == paired_users
    assert paired["test"]["p_value"] == 0.030894
    assert paired["effect_estimate"]["value"] == -1195.57377049

    used = coupons["状态"].astype("string").eq("已使用")
    expected_paid = (
        pd.to_numeric(coupons["sdk订单金额(分)"], errors="coerce")
        - pd.to_numeric(coupons["代金券面值(分)"], errors="coerce")
    ) / 100
    assert int(used.sum()) == baseline["coupons"]["used_rows"]
    assert bool(((pd.to_numeric(coupons["实付"], errors="coerce") - expected_paid).abs()[used] <= 0.01).all())
    assert cards["user_id"].nunique() == baseline["card_orders"]["unique_users"]

    calculations = [
        ("payment_dedup", {"dedup_received": float(payment_dedup["实收金额"].sum())}),
        ("user_aggregation", {"users": int(before_after_dedup["user_id"].nunique())}),
        ("paired_difference", paired),
        ("coupon_and_card_quality", {"used_rows": int(used.sum()), "card_users": int(cards["user_id"].nunique())}),
    ]
    manager = TaskManager(tasks_dir=tmp_path / "tasks")
    plan = manager.create_plan(
        session_id="savings-card-baseline",
        project_name="savings-card",
        goal="deterministic descriptive four-file baseline",
        source="analysis_plan",
    )
    tasks = []
    for index, (claim_key, _) in enumerate(calculations, start=1):
        tasks.append(manager.create(
            f"Savings-card baseline step {index}",
            session_id="savings-card-baseline",
            project_name="savings-card",
            plan_id=plan["id"],
            plan_version=plan["version"],
            task_kind="plan_task",
            analysis_plan_id="savings-card-descriptive-baseline",
            step_id=f"step-{index}",
            required_claim_keys=[claim_key],
            analysis_requirement_ids=[f"requirement-{index}"],
        ))
    manager.materialize_analysis_run(
        session_id="savings-card-baseline",
        project_name="savings-card",
        plan_id=plan["id"],
        tasks=tasks,
    )

    for index, ((claim_key, result), task) in enumerate(zip(calculations, tasks), start=1):
        binding = manager.get_analysis_run_tool_binding(
            session_id="savings-card-baseline",
            project_name="savings-card",
            external_step_id=f"step-{index}",
        )
        assert binding is not None
        artifact = tmp_path / f"calculation-{index}.json"
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
        artifact.write_text(serialized, encoding="utf-8")
        receipt = manager.commit_analysis_computation_projection(
            session_id="savings-card-baseline",
            binding=binding,
            tool_call_id=f"tool-call-{index}",
            tool_name=f"deterministic_{claim_key}",
            tool_state="committed",
            capability=f"analysis.{claim_key}",
            computation_ref={
                "computation_ref_id": "cr_" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24],
                "artifact_path": str(artifact),
                "output_digest": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                "projection_status": "projected",
            },
            evidence_records=[{
                "id": f"evidence-{index}",
                "claim_key": claim_key,
                "requirement_ids": [f"requirement-{index}"],
                "result_summary": f"deterministic {claim_key} completed",
                "confidence": "high",
            }],
            complete_step=True,
        )
        assert receipt is not None
        assert manager.get(task["id"])["status"] == "completed"

    coordinator = manager._analysis_run_coordinator(create=False)
    run = coordinator.store.get_latest_run("savings-card-baseline")
    assert run.status.value == "completed"
    assert all(manager.get(task["id"])["status"] == "completed" for task in tasks)
    assert coordinator.store.computation_count(run.run_id) == 4
    assert coordinator.store.evidence_link_count(run.run_id) == 4
    assert coordinator.store.tool_outcome_count(run.run_id) == 4
    assert coordinator.store.list_replayable_computations(
        run_id=run.run_id,
        session_id="savings-card-baseline",
    ) == []
