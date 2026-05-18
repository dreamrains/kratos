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


def _plotly_axis_values(series: pd.Series) -> list:
    """Return Plotly-safe axis values while preserving readable bin labels."""
    return [
        str(value) if isinstance(value, pd.Interval) else value
        for value in series.tolist()
    ]


def _chart_error(message: str, warnings: list[str]) -> str:
    return json.dumps({
        "error": message,
        "error_type": "chart_validation",
        "validation_warnings": warnings,
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

    title_l = title.lower()
    time_terms = ("trend", "time", "daily", "weekly", "monthly", "趋势", "月度", "每日", "按月", "时间")
    if chart_type == "line" and x_col and any(term in title_l for term in time_terms):
        if _looks_like_identifier(x_col, df[x_col]):
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
            metadata["evidence_ids"] = [
                item.strip() for item in (evidence_ids or "").split(",") if item.strip()
            ]

        if chart_type == "line":
            if x_col and y_col:
                y_cols = [c.strip() for c in y_col.split(",") if c.strip()]
                axis_groups = _detect_axis_groups(df, y_cols)
                use_multi_axis = len(axis_groups) > 1

                for axis_idx, group in enumerate(axis_groups):
                    yaxis_name = "y" if axis_idx == 0 else f"y{axis_idx + 1}"
                    for col in group:
                        fig.add_trace(go.Scatter(
                            x=df[x_col], y=df[col], mode="lines+markers",
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
                    axis_groups = _detect_axis_groups(df, y_cols)
                    use_multi_axis = len(axis_groups) > 1

                    for axis_idx, group in enumerate(axis_groups):
                        yaxis_name = "y" if axis_idx == 0 else f"y{axis_idx + 1}"
                        for col in group:
                            fig.add_trace(go.Bar(
                                x=df[x_col], y=df[col], name=col, yaxis=yaxis_name,
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
                fig.add_trace(go.Scatter(
                    x=df[x_col], y=df[y_col], mode="markers",
                    marker_color=df[color_col] if color_col and color_col in df.columns else None,
                ))
            else:
                numeric_cols = df.select_dtypes(include="number").columns
                if len(numeric_cols) >= 2:
                    fig.add_trace(go.Scatter(x=df[numeric_cols[0]], y=df[numeric_cols[1]], mode="markers"))

        elif chart_type == "box":
            cols = [x_col, y_col] if x_col and y_col else list(df.select_dtypes(include="number").columns[:5])
            for col in cols:
                if col in df.columns:
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
            elif df is not None and "step" in df.columns and "count" in df.columns:
                funnel_data = [{"step": str(row.get("step", "")), "count": float(row.get("count", 0))} for row in df.to_dict("records")]
            else:
                return "Error: funnel 图需要通过 data_json 提供步骤数据，格式: [{\"step\": \"步骤名\", \"count\": 数量}]"

            fig = go.Figure(go.Funnel(
                y=[s.get("step", s.get("label", "")) for s in funnel_data],
                x=[s.get("count", s.get("value", 0)) for s in funnel_data],
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
