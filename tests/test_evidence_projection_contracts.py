"""Offline contracts for projecting structured analysis evidence."""
from __future__ import annotations

import json

import pandas as pd

from tests.test_artifact_publication_contracts import context


def _receipt(context, receipt_id, tool, result, arguments, dataset="analysis"):
    identity = context.workspace.get_data_identity(dataset)
    return {
        "id": receipt_id,
        "tool_call_id": receipt_id,
        "tool_name": tool,
        "structured_result_sha256": "sha256:validated",
        "arguments": arguments,
        "dataset_refs": [dataset],
        "data_identities": {dataset: identity},
    }, result


def test_time_series_shape_projects_complete_evidence(context, monkeypatch):
    from data_agent.tools.analysis_flow import _mark_statistical_detail_status
    from data_agent.tools.evidence_statistics import bind_computed_statistics

    context.workspace.add("analysis", pd.DataFrame({
        "date": pd.date_range("2021-03-01", periods=248, freq="D"),
        "video": range(248),
        "iap": range(1000, 1248),
        "banner": range(2000, 2248),
    }))
    receipts, results = [], {}
    for index, value_col in enumerate(("video", "iap", "banner"), start=1):
        receipt_id = f"r{index}"
        receipt, result = _receipt(
            context,
            receipt_id,
            "analyze_time_series",
            {
                "data_points": 248,
                "date_range": {"start": "2021-03-01T00:00:00", "end": "2021-11-03T00:00:00"},
                "statistics": {"mean": 271.187 + index, "std": 41.72},
                "trend": {"direction": "down", "slope": -0.14, "r_squared": 0.059,
                          "p_value": 0.000112, "significant": True},
                "change_points": [],
                "seasonality": {"likely_seasonal": True},
            },
            {"name": "analysis", "date_col": "date", "value_col": value_col},
        )
        receipts.append(receipt)
        results[receipt_id] = result
    monkeypatch.setattr(
        "data_agent.tools.result_reference.load_result_reference",
        lambda ref: (results[ref.split("/")[-1].split("_")[0]],
                     {"receipt_id": ref.split("/")[-1].split("_")[0]}),
    )

    payload = {}
    bind_computed_statistics(payload, receipts)
    _mark_statistical_detail_status(payload)

    assert payload["statistical_detail_status"] == "complete"
    assert payload["time_scope"] == {
        "start": "2021-03-01T00:00:00",
        "end": "2021-11-03T00:00:00",
    }
    assert payload["sample_size"] == 248
    assert payload["statistical_inference"] is True
    assert payload["significance"]["trend"]["p_value"] == 0.000112
    assert len(payload["metrics"]) == 3


def test_run_python_shape_uses_current_receipt_bound_dataset_window(context, monkeypatch):
    from data_agent.tools.analysis_flow import _mark_statistical_detail_status
    from data_agent.tools.evidence_statistics import bind_computed_statistics

    context.workspace.add("analysis", pd.DataFrame({
        "日期": pd.to_datetime(["2020-01-16", "2020-01-17", "2020-01-19"]),
        "公司": ["内部游戏", "外部游戏", "外部游戏"],
        "卖量收入": [100.0, None, 50.0],
    }))
    run_receipt, run_result = _receipt(
        context,
        "run",
        "run_python",
        {"result": "{'rows': 3, 'missing_rows': 1, 'observable_revenue': 150.0}"},
        {"code": 'df = get_dataset("analysis")\nresult = {"rows": len(df)}'},
    )
    transform_receipt, transform_result = _receipt(
        context,
        "transform",
        "transform_data",
        {"rows": 2},
        {"source": "analysis", "operation": "group_aggregate"},
    )
    results = {"run": run_result, "transform": transform_result}
    monkeypatch.setattr(
        "data_agent.tools.result_reference.load_result_reference",
        lambda ref: (results[ref.split("/")[-1].split("_")[0]],
                     {"receipt_id": ref.split("/")[-1].split("_")[0]}),
    )

    payload = {}
    bind_computed_statistics(payload, [run_receipt, transform_receipt])
    _mark_statistical_detail_status(payload)

    assert payload["statistical_detail_status"] == "complete"
    assert payload["time_scope_source"]["type"] == "current_receipt_bound_datasets"
    window = payload["time_scope"]["datasets"][0]
    assert window["dataset"] == "analysis"
    assert window["column"] == "日期"
    assert window["start"].startswith("2020-01-16")
    assert window["end"].startswith("2020-01-19")
    assert window["version_id"] == context.workspace.get_data_identity("analysis")["version_id"]


def test_supplemental_untyped_sandbox_output_does_not_erase_native_metrics(context, monkeypatch):
    from data_agent.tools.analysis_flow import _mark_statistical_detail_status
    from data_agent.tools.evidence_statistics import bind_computed_statistics

    context.workspace.add("analysis", pd.DataFrame({
        "日期": pd.date_range("2020-07-01", periods=3),
        "D1": [0.17, 0.16, 0.15],
    }))
    native, native_result = _receipt(
        context,
        "native",
        "curve_fitting",
        {
            "points": [{"x": 1, "y": 0.17}, {"x": 2, "y": 0.11}],
            "fits": [{"family": "power", "r_squared": 0.98}],
            "effective_n": 2,
        },
        {"name": "analysis", "series_columns": "D1"},
    )
    supplemental, supplemental_result = _receipt(
        context,
        "supplemental",
        "run_python",
        {
            "output": "rows=3; date range 2020-07-01 to 2020-07-03",
            "fallback_policy": {"role": "supplemental"},
        },
        {"code": 'df = get_dataset("analysis")\nprint(len(df))'},
    )
    values = {"native": native_result, "supplemental": supplemental_result}
    monkeypatch.setattr(
        "data_agent.tools.result_reference.load_result_reference",
        lambda ref: (values[ref.split("/")[-1].split("_")[0]],
                     {"receipt_id": ref.split("/")[-1].split("_")[0]}),
    )

    payload = {}
    bind_computed_statistics(payload, [native, supplemental])
    _mark_statistical_detail_status(payload)

    assert payload["statistical_detail_status"] == "complete"
    assert payload["metrics"]["curve_fitting"]["fits"][0]["r_squared"] == 0.98
    assert payload["statistical_projection_gaps"][0]["blocking"] is False


def test_rejected_publication_message_is_internal_to_provider_history():
    from data_agent.session.public_messages import assistant_replies

    messages = [
        {"role": "user", "content": "分析"},
        {"role": "assistant", "content": "零值一定代表未观测。", "publication_rejected": True},
        {"role": "system", "content": "rewrite"},
        {"role": "assistant", "content": "零值含义未知。"},
    ]
    replies = assistant_replies(messages, "session")

    assert len(replies) == 1
    assert replies[0]["content"] == "零值含义未知。"
    assert "未观测" not in json.dumps(replies, ensure_ascii=False)
