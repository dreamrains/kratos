"""Explicit, copy-on-write time alignment across existing workspace datasets."""
from __future__ import annotations

import json
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import ToolResult, registry


@registry.register(
    name="synthesize_time_series",
    description="按明确日期列将多个数据集日粒度聚合并对齐；披露覆盖窗口、缺失日期和多父数据身份，不执行隐式业务 join。",
    schema_overrides={
        "datasets": {"description": "数据集名称，逗号分隔"},
        "date_col": {"description": "各数据集共有的日期列"},
        "metrics": {"description": "dataset:metric 逗号分隔，例如 banner:广告收入,iap:内购收入"},
        "save_as": {"description": "可选派生数据集名称；为空只返回对齐结果"},
    },
)
def synthesize_time_series(datasets: str, date_col: str = "日期", metrics: str = "", save_as: str = "") -> ToolResult:
    names = [item.strip() for item in datasets.split(",") if item.strip()]
    pairs = [item.strip() for item in metrics.split(",") if item.strip()]
    metric_map = {}
    for pair in pairs:
        if ":" not in pair:
            return ToolResult(summary="metrics 必须使用 dataset:metric 格式")
        dataset, metric = (part.strip() for part in pair.split(":", 1))
        metric_map[dataset] = metric
    if len(names) < 2 or set(names) != set(metric_map):
        return ToolResult(summary="至少指定两个数据集，并且每个数据集必须指定一个 metric")
    series, coverage, identities = [], {}, {}
    for name in names:
        frame = workspace.get(name)
        if frame is None:
            return ToolResult(summary=f"数据集 '{name}' 不存在或不在当前任务范围")
        metric = metric_map[name]
        if date_col not in frame.columns or metric not in frame.columns:
            return ToolResult(summary=f"数据集 '{name}' 缺少 {date_col!r} 或 {metric!r}")
        working = pd.DataFrame({"date": pd.to_datetime(frame[date_col], errors="coerce"), name: pd.to_numeric(frame[metric], errors="coerce")}).dropna()
        if working.empty:
            return ToolResult(summary=f"数据集 '{name}' 没有可用日期/数值")
        daily = working.groupby("date", as_index=False)[name].sum().sort_values("date")
        dates = daily["date"]
        coverage[name] = {"metric": metric, "rows": int(len(frame)), "effective_rows": int(len(working)), "start": str(dates.min().date()), "end": str(dates.max().date()), "distinct_dates": int(dates.nunique())}
        identities[name] = workspace.get_data_identity(name)
        series.append(daily)
    aligned = series[0]
    for item in series[1:]:
        aligned = aligned.merge(item, on="date", how="outer", validate="one_to_one")
    aligned = aligned.sort_values("date").reset_index(drop=True)
    missing = {name: int(aligned[name].isna().sum()) for name in names}
    result = {"method_contract": "multi_file_time_synthesis.v1", "status": "supported", "date_col": date_col, "source_datasets": names, "source_identities": identities, "coverage": coverage, "aligned_rows": int(len(aligned)), "missing_aligned_dates": missing, "limitations": ["此操作仅按明确的共同日期聚合与并列对齐，不推断实体级业务 join 或因果关系。"], "claim_ceiling": "descriptive"}
    if save_as:
        message = workspace.derive_multi(names, save_as, aligned, expression=f"date-aligned daily sums: {metric_map}")
        if message.startswith("Error:"):
            return ToolResult(summary=message, data=result)
        result["derived_dataset"] = save_as
        result["derived_identity"] = workspace.get_data_identity(save_as)
    return ToolResult(summary="已完成多数据集按日期对齐；缺失覆盖已披露。", data=result)
