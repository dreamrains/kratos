"""L5: 可视化工具。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from data_agent.config import get_config
from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df
from data_agent.tools.chart_contract import validate_chart_request
from data_agent.tools.registry import registry


def _save_chart(fig: go.Figure, title: str = "chart", metadata: dict | None = None) -> str:
    """保存图表到当前会话的 output 目录，同时导出 PNG 静态图片用于 PDF 嵌入。"""
    from data_agent.session.history import session_charts_dir, register_artifact

    session_id = current_session_id()
    if session_id:
        output_dir = session_charts_dir(session_id)
        chart_id = f"{title.replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        path = output_dir / f"{chart_id}.html"
        fig.write_html(str(path), include_plotlyjs='/static/js/plotly-3.5.0.min.js')
        if metadata is not None:
            meta = dict(metadata)
            meta["chart_id"] = chart_id
            meta["filename"] = path.name
            (output_dir / f"{chart_id}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        # 导出 PNG 静态图片（用于 PDF 嵌入）
        try:
            png_path = output_dir / f"{chart_id}.png"
            fig.update_layout(width=800, height=450)
            png_path.write_bytes(fig.to_image(format="png", scale=1.5))
        except Exception:
            pass  # PNG 导出失败不影响主流程
        artifact_path = f"sessions/{session_id}/charts/{chart_id}.html"
        register_artifact(session_id, artifact_path, "chart", title)
        return f"Chart saved: {artifact_path}"
    else:
        cfg = get_config()
        output_dir = cfg.project_resolved / "charts"
        output_dir.mkdir(parents=True, exist_ok=True)
        chart_id = f"{title.replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        path = output_dir / f"{chart_id}.html"
        fig.write_html(str(path), include_plotlyjs='/static/js/plotly-3.5.0.min.js')
        if metadata is not None:
            meta = dict(metadata)
            meta["chart_id"] = chart_id
            meta["filename"] = path.name
            (output_dir / f"{chart_id}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return f"Chart saved: charts/{chart_id}.html"


# 当前会话 ID（由 Agent Loop 设置）
_current_session_id = ""


def set_chart_session(session_id: str):
    global _current_session_id
    _current_session_id = session_id


def current_session_id() -> str:
    try:
        from data_agent.agent.context import get_current_context
        ctx = get_current_context()
        if ctx is not None:
            return ctx.session_id
    except Exception:
        pass
    return _current_session_id


def _detect_axis_groups(df: pd.DataFrame, y_cols: list[str]) -> list[list[str]]:
    """根据各列数值量级自动分组 Y 轴。

    量级差异超过 50 倍的列分配到不同轴，最多 3 个轴。
    返回分组列表，每组一个 Y 轴。
    """
    if len(y_cols) <= 1:
        return [y_cols]

    max_vals = {}
    for col in y_cols:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            max_vals[col] = s.abs().max() if len(s) > 0 else 0

    if not max_vals:
        return [y_cols]

    # 按最大值排序
    sorted_cols = sorted(max_vals.keys(), key=lambda c: max_vals[c], reverse=True)

    groups: list[list[str]] = [[sorted_cols[0]]]
    for col in sorted_cols[1:]:
        placed = False
        for group in groups:
            group_max = max(max_vals[c] for c in group)
            val = max_vals[col]
            if val == 0 or group_max == 0:
                continue
            ratio = max(group_max / val, val / group_max)
            if ratio < 50:
                group.append(col)
                placed = True
                break
        if not placed:
            groups.append([col])

    # 最多 3 个轴，超出则合并到最近的组
    while len(groups) > 3:
        smallest = min(groups, key=len)
        groups.remove(smallest)
        groups[-1].extend(smallest)

    return groups


def _bar_chart_needs_normalization(df: pd.DataFrame, y_cols: list[str]) -> bool:
    if len(y_cols) <= 1:
        return False
    return len(_detect_axis_groups(df, y_cols)) > 1


def _plotly_axis_values(series: pd.Series) -> list:
    """Return Plotly-safe axis values while preserving readable bin labels."""
    return [
        str(value) if isinstance(value, pd.Interval) else value
        for value in series.tolist()
    ]


def _parsed_evidence_ids(evidence_ids: str) -> list[str]:
    return [item.strip() for item in (evidence_ids or "").split(",") if item.strip()]


def _first_present(row: dict, keys: tuple[str, ...]):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _funnel_step_is_amount(step: str) -> bool:
    label = str(step or "").lower()
    amount_terms = (
        "revenue",
        "income",
        "amount",
        "gmv",
        "sales",
        "cost",
        "spend",
        "roi",
        "ecpm",
        "\u6536\u5165",
        "\u91d1\u989d",
        "\u9500\u552e\u989d",
        "\u5356\u91cf\u6536\u5165",
        "\u82b1\u8d39",
        "\u6210\u672c",
        "\u5143",
        "\uffe5",
        "\u00a5",
    )
    return any(term in label for term in amount_terms)


def _normalize_funnel_rows(rows: list[dict]) -> tuple[list[dict], str | None]:
    normalized: list[dict] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            return [], "funnel data_json must be a list of objects"
        step = _first_present(row, ("step", "stage", "label", "name", "步骤", "阶段", "环节", "名称"))
        count = _first_present(row, ("count", "value", "数值", "数量", "次数", "count_value"))
        if step in (None, "") or count in (None, ""):
            return [], f"funnel row {idx + 1} must include a step/stage label and count/value"
        numeric_count = pd.to_numeric(pd.Series([count]), errors="coerce").iloc[0]
        if pd.isna(numeric_count):
            return [], f"funnel row {idx + 1} count/value must be numeric"
        if _funnel_step_is_amount(str(step)):
            return [], (
                "funnel stages must use comparable count metrics; "
                f"row {idx + 1} looks like a revenue or amount metric"
            )
        normalized.append({"step": str(step), "count": float(numeric_count)})
    if not normalized:
        return [], "funnel data_json must contain at least one step"
    if all(item["count"] == 0 for item in normalized):
        return [], "funnel count/value cannot all be zero"
    return normalized, None


def _chart_error(
    message: str,
    warnings: list[str],
    *,
    error_code: str = "chart_validation",
    recovery_options: list[dict[str, str]] | None = None,
) -> str:
    return json.dumps({
        "error": message,
        "error_type": "chart_validation",
        "error_code": error_code,
        "validation_warnings": warnings,
        "recovery_options": recovery_options or [],
    }, ensure_ascii=False)


def _looks_like_identifier(col: str, series: pd.Series) -> bool:
    name = col.lower()
    if any(token in name for token in ("id", "user", "uid", "account")):
        unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
        return unique_ratio > 0.7
    return False


def _is_date_like(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series):
        return False
    parsed = pd.to_datetime(series.dropna().astype(str), errors="coerce")
    return len(parsed) > 0 and parsed.notna().mean() >= 0.8


def _is_numeric_column(df: pd.DataFrame, col: str) -> bool:
    if col not in df.columns:
        return False
    numeric = pd.to_numeric(df[col], errors="coerce")
    return numeric.notna().sum() > 0


def _title_claims_rate(title: str) -> bool:
    title_l = (title or "").lower()
    return any(term in title_l for term in ("ctr", "rate", "ratio", "percent", "%", "率", "转化", "点击率"))


def _metric_names_claim_rate(y_cols: list[str]) -> bool:
    return any(_title_claims_rate(col) for col in y_cols)


def _refresh_chart_metadata(metadata: dict | None, df: pd.DataFrame, x_col: str, y_cols: list[str], aggregation: str = "") -> None:
    if metadata is None:
        return
    if aggregation:
        metadata["aggregation"] = aggregation
    metadata["row_count"] = int(len(df))
    metadata["missing_summary"] = {
        col: int(df[col].isna().sum())
        for col in ([x_col] if x_col else []) + y_cols
        if col in df.columns
    }


def _prepare_chart_dataframe(
    df: pd.DataFrame,
    chart_type: str,
    x_col: str,
    y_cols: list[str],
    color_col: str,
    metadata: dict | None,
    aggregation: str = "",
) -> pd.DataFrame:
    if not x_col or not y_cols or x_col not in df.columns:
        return df

    if chart_type == "line" and _is_date_like(df[x_col]):
        parsed = pd.to_datetime(df[x_col], errors="coerce")
        day_values = parsed.dt.normalize()
        plot_df = df.copy()
        plot_df[x_col] = day_values.dt.strftime("%Y-%m-%d")
        group_cols = [x_col] + ([color_col] if color_col else [])
        if parsed.notna().any() and plot_df.duplicated(subset=group_cols).any():
            plot_df = (
                plot_df.groupby(group_cols, sort=False, dropna=False)[y_cols]
                .agg(aggregation)
                .reset_index()
            )
            _refresh_chart_metadata(
                metadata,
                plot_df,
                x_col,
                y_cols,
                f"{aggregation}_by_day",
            )
            if metadata is not None:
                metadata.setdefault("transformations", []).append(
                    f"aggregation:{aggregation}"
                )
            return plot_df

    if chart_type in {"bar", "stacked_bar"}:
        group_cols = [x_col] + ([color_col] if color_col else [])
        if not df.duplicated(subset=group_cols).any():
            return df
        plot_df = (
            df.groupby(group_cols, sort=False, dropna=False)[y_cols]
            .agg(aggregation)
            .reset_index()
        )
        _refresh_chart_metadata(
            metadata,
            plot_df,
            x_col,
            y_cols,
            f"{aggregation}_by_x",
        )
        if metadata is not None:
            metadata.setdefault("transformations", []).append(
                f"aggregation:{aggregation}"
            )
        return plot_df

    return df


def _validate_chart_spec(
    df: pd.DataFrame,
    chart_type: str,
    data_name: str,
    title: str,
    x_col: str,
    y_col: str,
    color_col: str,
) -> tuple[dict | None, str | None]:
    warnings: list[str] = []
    y_cols = [c.strip() for c in y_col.split(",") if c.strip()]

    if x_col and x_col not in df.columns:
        return None, _chart_error(f"x_col '{x_col}' not found", [f"missing x_col: {x_col}"])
    for col in y_cols:
        if col not in df.columns:
            return None, _chart_error(f"y_col '{col}' not found", [f"missing y_col: {col}"])
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() == 0:
            return None, _chart_error(f"y_col '{col}' is empty or non-numeric", [f"invalid y_col: {col}"])

    if color_col and color_col not in df.columns:
        return None, _chart_error(f"color_col '{color_col}' not found", [f"missing color_col: {color_col}"])

    if chart_type == "scatter" and x_col and y_cols:
        bad_axes = [col for col in [x_col, y_cols[0]] if not _is_numeric_column(df, col)]
        if bad_axes:
            return None, _chart_error(
                "scatter chart requires numeric x_col and y_col",
                [f"non-numeric scatter axis: {', '.join(bad_axes)}"],
            )

    if chart_type == "histogram":
        hist_col = y_cols[0] if y_cols else x_col
        if hist_col and not _is_numeric_column(df, hist_col):
            return None, _chart_error(
                "histogram chart requires a numeric metric column",
                [f"non-numeric histogram column: {hist_col}"],
            )

    title_l = title.lower()
    time_terms = ("trend", "time", "daily", "weekly", "monthly", "趋势", "月度", "每日", "按月", "时间")
    if chart_type == "line" and x_col and any(term in title_l for term in time_terms):
        if not _is_date_like(df[x_col]) and _looks_like_identifier(x_col, df[x_col]):
            return None, _chart_error(
                "time trend chart cannot use an identifier-like x axis",
                [f"identifier-like x axis: {x_col}"],
            )
        if not _is_date_like(df[x_col]) and df[x_col].nunique(dropna=True) > 24:
            warnings.append(f"x axis '{x_col}' is not date-like or pre-aggregated")

    if x_col and df[x_col].nunique(dropna=True) > 50 and chart_type in {"bar", "line"}:
        warnings.append(f"x axis '{x_col}' has too many categories; aggregate or use Top N")

    if len(y_cols) > 1 and x_col:
        grouped = df.groupby(x_col, dropna=False)[y_cols].apply(lambda g: g.notna().all())
        missing_cols = sorted({col for _, row in grouped.iterrows() for col in y_cols if not bool(row[col])})
        if missing_cols:
            warnings.append(f"missing metric values by x group: {', '.join(missing_cols)}")
        if chart_type == "bar" and _bar_chart_needs_normalization(df, y_cols):
            warnings.append("multi-metric bar chart normalized divergent scales to avoid misleading overlaid axes")

    if y_cols and _title_claims_rate(title) and not _metric_names_claim_rate(y_cols):
        warnings.append("title mentions rate/CTR but y_col appears to be a count metric; verify numerator and denominator")

    if chart_type == "pie":
        pie_col = y_cols[0] if y_cols else x_col
        if pie_col and pie_col in df.columns and df[pie_col].nunique(dropna=True) > 10:
            warnings.append(f"pie chart has more than 10 categories in '{pie_col}'; only Top 10 slices are shown")

    metadata = {
        "title": title,
        "chart_type": chart_type,
        "dataset": data_name,
        "x_col": x_col,
        "y_cols": y_cols,
        "color_col": color_col,
        "aggregation": "",
        "filters": {},
        "row_count": int(len(df)),
        "missing_summary": {col: int(df[col].isna().sum()) for col in ([x_col] if x_col else []) + y_cols if col in df.columns},
        "evidence_ids": [],
        "validation_status": "warning" if warnings else "valid",
        "validation_warnings": warnings,
    }
    return metadata, None


@registry.register(
    name="create_chart",
    description=(
        "创建可视化图表。"
        "使用场景：展示趋势（line）、对比（bar）、分布（box/histogram）、关系（scatter/heatmap）、占比（pie）、转化（funnel）。"
        "不适用场景：数据尚未加载、需要精确数值对比（用表格输出更好）。"
        "参数说明：data 为数据集名称，y_col 支持逗号分隔多列（自动多轴），color_col 用于分组。"
        "常见错误：列名不存在、数值列包含非数字、x 轴类别过多（>50 时先聚合）。"
    ),
    recovery_hint=(
        "图表创建失败。常见原因："
        "1) x_col/y_col 列名不存在（用 preview_data 查看）"
        "2) 数值列包含非数字（用 describe_dataset 检查类型）"
        "3) 数据为空或过滤后无数据"
        "请修正参数或先用 transform_data 生成适合可视化的聚合数据；不要用未经验证的文本图替代数据图表。"
    ),
    schema_overrides={
        "chart_type": {"description": "图表类型", "enum": ["line", "bar", "stacked_bar", "scatter", "box", "histogram", "heatmap", "pie", "funnel"]},
        "data": {"description": "数据集名称"},
        "title": {"description": "图表标题"},
        "x_col": {"description": "X 轴列名"},
        "y_col": {"description": "Y 轴列名，逗号分隔支持多列"},
        "color_col": {"description": "颜色分组列"},
        "data_json": {"description": "JSON 格式数据（funnel 必须用此参数）"},
        "aggregation": {"description": "重复分组的聚合方式", "enum": ["", "sum", "mean", "median", "count"]},
        "scale_mode": {"description": "多指标尺度处理", "enum": ["", "raw", "normalize"]},
    },
)
def create_chart(
    chart_type: str,
    data: str = "",
    title: str = "Chart",
    x_col: str = "",
    y_col: str = "",
    color_col: str = "",
    data_json: str = "",
    purpose: str = "exploratory",
    evidence_ids: str = "",
    aggregation: str = "",
    scale_mode: str = "",
) -> str:
    fig = go.Figure()

    # 获取数据
    df = None
    data_name = data
    if data and data in workspace.list_datasets():
        df = workspace.get(data)
    elif data_json:
        try:
            from io import StringIO
            df = pd.read_json(StringIO(data_json))
        except Exception:
            pass

    if df is None and not data_json:
        # 尝试从工作空间取默认数据集
        datasets = workspace.list_datasets()
        if "main" in datasets:
            df = workspace.get("main")
            data_name = "main"
        elif datasets:
            # 选择行数最多的数据集作为最合理的默认值
            largest = max(datasets.items(), key=lambda kv: kv[1].get("rows", 0))
            df = workspace.get(largest[0])
            data_name = largest[0]

    if df is None:
        return "Error: 没有可用数据。请先加载数据或提供 data_json。"

    try:
        metadata, validation_error = _validate_chart_spec(df, chart_type, data_name, title, x_col, y_col, color_col)
        if validation_error:
            return validation_error
        if metadata is not None:
            allowed_purposes = {"exploratory", "evidence", "insight"}
            normalized_purpose = (purpose or "exploratory").strip().lower()
            if normalized_purpose not in allowed_purposes:
                return _chart_error(
                    f"invalid chart purpose: {purpose}",
                    [f"purpose must be one of {sorted(allowed_purposes)}"],
                )
            metadata["purpose"] = normalized_purpose
            metadata["evidence_ids"] = _parsed_evidence_ids(evidence_ids)
            if normalized_purpose in {"evidence", "insight"} and not metadata["evidence_ids"]:
                return _chart_error(
                    "purpose 'evidence' or 'insight' requires evidence_ids",
                    ["missing evidence_ids for evidence-backed chart"],
                )

        y_cols_for_plot = [c.strip() for c in y_col.split(",") if c.strip()]
        contract = validate_chart_request(
            df,
            chart_type,
            x_col,
            y_cols_for_plot,
            color_col,
            aggregation,
            scale_mode,
        )
        if not contract.valid:
            return _chart_error(
                contract.error,
                contract.warnings,
                error_code=contract.error_code,
                recovery_options=contract.recovery_options,
            )
        df = contract.dataframe
        if metadata is not None:
            metadata["semantic_roles"] = contract.semantic_roles
            metadata["transformations"] = contract.transformations
            metadata["category_count"] = (
                int(df[x_col].nunique(dropna=True))
                if x_col and x_col in df.columns
                else 0
            )
        df = _prepare_chart_dataframe(
            df,
            chart_type,
            x_col,
            y_cols_for_plot,
            color_col,
            metadata,
            aggregation,
        )

        if chart_type == "line":
            if x_col and y_col:
                y_cols = [c.strip() for c in y_col.split(",") if c.strip()]
                axis_groups = _detect_axis_groups(df, y_cols)
                use_multi_axis = len(axis_groups) > 1

                for axis_idx, group in enumerate(axis_groups):
                    yaxis_name = "y" if axis_idx == 0 else f"y{axis_idx + 1}"
                    for col in group:
                        if color_col:
                            for cat, group_df in df.groupby(color_col, sort=False, dropna=False):
                                trace_name = str(cat) if len(y_cols) == 1 else f"{cat} - {col}"
                                fig.add_trace(go.Scatter(
                                    x=_plotly_axis_values(group_df[x_col]),
                                    y=group_df[col],
                                    mode="lines+markers",
                                    name=trace_name,
                                    yaxis=yaxis_name,
                                ))
                        else:
                            fig.add_trace(go.Scatter(
                                x=_plotly_axis_values(df[x_col]), y=df[col], mode="lines+markers",
                                name=col, yaxis=yaxis_name,
                            ))

                if use_multi_axis:
                    for axis_idx in range(1, len(axis_groups)):
                        fig.update_layout(**{
                            f"yaxis{axis_idx + 1}": dict(
                                overlaying="y", side="right",
                                title=dict(text=", ".join(axis_groups[axis_idx])),
                            )
                        })
            else:
                numeric_cols = df.select_dtypes(include="number").columns[:3]
                for col in numeric_cols:
                    fig.add_trace(go.Scatter(y=df[col], mode="lines+markers", name=col))

        elif chart_type == "bar":
            if x_col and y_col:
                y_cols = [c.strip() for c in y_col.split(",") if c.strip()]
                if len(y_cols) > 1:
                    normalize = scale_mode == "normalize"
                    for col in y_cols:
                        values = pd.to_numeric(df[col], errors="coerce")
                        if normalize:
                            max_abs = values.abs().max()
                            plotted = values / max_abs * 100 if max_abs else values
                            fig.add_trace(go.Bar(
                                x=_plotly_axis_values(df[x_col]),
                                y=plotted,
                                name=col,
                                customdata=values,
                                hovertemplate=(
                                    f"{col}<br>%{{x}}<br>"
                                    "Normalized value=%{y:.2f}<br>"
                                    "Original value=%{customdata}<extra></extra>"
                                ),
                            ))
                        else:
                            fig.add_trace(go.Bar(
                                x=_plotly_axis_values(df[x_col]),
                                y=values,
                                name=col,
                            ))
                    fig.update_layout(
                        barmode="group",
                        yaxis_title="Normalized value (max=100)" if normalize else "Value",
                    )
                else:
                    if color_col:
                        for cat, group_df in df.groupby(color_col, sort=False, dropna=False):
                            fig.add_trace(go.Bar(
                                x=_plotly_axis_values(group_df[x_col]),
                                y=group_df[y_col],
                                name=str(cat),
                            ))
                        fig.update_layout(barmode="group")
                    else:
                        fig.add_trace(go.Bar(x=_plotly_axis_values(df[x_col]), y=df[y_col], name=y_col))
            else:
                numeric_cols = df.select_dtypes(include="number").columns[:5]
                for col in numeric_cols:
                    fig.add_trace(go.Bar(x=df.index, y=df[col], name=col))

        elif chart_type == "stacked_bar":
            if x_col and y_col and color_col:
                for cat in df[color_col].unique():
                    mask = df[color_col] == cat
                    fig.add_trace(go.Bar(x=df[mask][x_col], y=df[mask][y_col], name=str(cat)))
                fig.update_layout(barmode="stack")
            else:
                return "Error: stacked_bar 需要 x_col, y_col 和 color_col"

        elif chart_type == "scatter":
            if x_col and y_col:
                if color_col:
                    for cat, group_df in df.groupby(color_col, sort=False, dropna=False):
                        fig.add_trace(go.Scatter(
                            x=group_df[x_col],
                            y=group_df[y_col],
                            mode="markers",
                            name=str(cat),
                        ))
                else:
                    fig.add_trace(go.Scatter(
                        x=df[x_col], y=df[y_col], mode="markers",
                    ))
            else:
                numeric_cols = df.select_dtypes(include="number").columns
                if len(numeric_cols) >= 2:
                    fig.add_trace(go.Scatter(x=df[numeric_cols[0]], y=df[numeric_cols[1]], mode="markers"))

        elif chart_type == "box":
            if x_col and y_col:
                fig.add_trace(go.Box(
                    x=_plotly_axis_values(df[x_col]),
                    y=pd.to_numeric(df[y_col], errors="coerce").tolist(),
                    name=y_col,
                ))
            else:
                cols = list(df.select_dtypes(include="number").columns[:5])
                for col in cols:
                    fig.add_trace(go.Box(y=df[col].dropna(), name=col))

        elif chart_type == "histogram":
            col = y_col or x_col
            if col and col in df.columns:
                fig.add_trace(go.Histogram(x=df[col].dropna(), name=col))
            else:
                col = df.select_dtypes(include="number").columns[0]
                fig.add_trace(go.Histogram(x=df[col].dropna(), name=col))

        elif chart_type == "heatmap":
            numeric_df = df.select_dtypes(include="number")
            corr = numeric_df.corr()
            fig.add_trace(go.Heatmap(
                z=corr.values,
                x=list(corr.columns),
                y=list(corr.columns),
                colorscale="RdBu_r",
                zmin=-1, zmax=1,
            ))

        elif chart_type == "funnel":
            import plotly.express as px
            if data_json:
                try:
                    funnel_data = json.loads(data_json) if isinstance(data_json, str) else data_json
                except (json.JSONDecodeError, TypeError):
                    return "Error: funnel 图需要通过 data_json 提供 JSON 格式的步骤数据"
            elif df is not None:
                funnel_data = df.to_dict("records")
            else:
                return "Error: funnel 图需要通过 data_json 提供步骤数据，格式: [{\"step\": \"步骤名\", \"count\": 数量}]"

            funnel_data, funnel_error = _normalize_funnel_rows(funnel_data)
            if funnel_error:
                return _chart_error(f"invalid funnel data: {funnel_error}", [funnel_error])

            fig = go.Figure(go.Funnel(
                y=[s["step"] for s in funnel_data],
                x=[s["count"] for s in funnel_data],
                textinfo="value+percent initial+percent previous",
                marker={"color": px.colors.qualitative.Plotly[:len(funnel_data)]},
            ))

        elif chart_type == "pie":
            col = y_col or x_col
            if col and col in df.columns:
                counts = df[col].value_counts().head(10)
                fig.add_trace(go.Pie(labels=counts.index, values=counts.values))
            else:
                return "Error: pie 图需要指定一个列"

        else:
            return f"Error: 不支持的图表类型 '{chart_type}'。支持: line, bar, stacked_bar, scatter, box, histogram, heatmap, pie, funnel"

        fig.update_layout(title=title, template="plotly_white")
        if "identifier_to_category" in contract.transformations:
            fig.update_xaxes(type="category")
        path = _save_chart(fig, title, metadata)
        return path

    except Exception as e:
        return f"Error creating chart: {e}"


def get_chart_embed_html(session_id: str, chart_filename: str = "") -> str:
    """读取 session charts 目录中的 Plotly HTML 文件，提取可嵌入报告的 HTML 片段。"""
    import re
    from data_agent.session.history import session_charts_dir

    charts_dir = session_charts_dir(session_id)

    if chart_filename:
        files = [charts_dir / chart_filename]
    else:
        files = sorted(charts_dir.glob("*.html"))

    embeds = []
    for f in files:
        if not f.exists():
            continue
        raw = f.read_text(encoding="utf-8")

        # Extract the plotly-graph-div and its Plotly.newPlot script
        # Skip PlotlyConfig and CDN scripts (will be in report <head>)
        div_match = re.search(
            r'(<div[^>]*class="plotly-graph-div"[^>]*>.*?</div>)\s*(<script>.*?Plotly\.newPlot\(.*?</script>)',
            raw, re.DOTALL,
        )
        if div_match:
            chart_div = div_match.group(1)
            chart_script = div_match.group(2)
            # Derive a readable title from filename
            stem = f.stem
            title_part = stem.rsplit("_", 1)[0] if "_" in stem else stem
            embeds.append(
                f'<div class="chart-container">'
                f'<h4>{title_part}</h4>\n'
                f'{chart_div}\n{chart_script}\n'
                f'</div>'
            )

    return "\n".join(embeds)


def get_chart_entries(session_id: str) -> list[dict]:
    """返回 session 所有图表的结构化条目列表。

    每个条目含：
    - filename: 文件名（如 "DAU趋势_a1b2c3.html"）
    - title: 可读标题（如 "DAU趋势"）
    - html: 可嵌入的 HTML 片段
    """
    import re
    from data_agent.session.history import session_charts_dir

    charts_dir = session_charts_dir(session_id)
    entries = []
    for f in sorted(charts_dir.glob("*.html")):
        raw = f.read_text(encoding="utf-8")
        div_match = re.search(
            r'(<div[^>]*class="plotly-graph-div"[^>]*>.*?</div>)\s*(<script>.*?Plotly\.newPlot\(.*?</script>)',
            raw, re.DOTALL,
        )
        if div_match:
            chart_div = div_match.group(1)
            chart_script = div_match.group(2)
            stem = f.stem
            title_part = stem.rsplit("_", 1)[0] if "_" in stem else stem
            html = (
                f'<div class="chart-container">'
                f'<h4>{title_part}</h4>\n'
                f'{chart_div}\n{chart_script}\n'
                f'</div>'
            )
            entries.append({
                "filename": f.name,
                "title": title_part,
                "html": html,
            })
    return entries


def match_chart(entries: list[dict], keyword: str) -> Optional[dict]:
    """根据关键词匹配图表条目。支持中文/英文标题子串匹配。"""
    if not keyword or not entries:
        return None
    kw = keyword.lower().strip()
    for entry in entries:
        if kw in entry["title"].lower() or kw in entry["filename"].lower():
            return entry
    return None
