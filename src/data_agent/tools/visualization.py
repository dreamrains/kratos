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


def _save_chart(fig: go.Figure, title: str = "chart") -> str:
    """保存图表到当前会话的 output 目录，同时导出 PNG 静态图片用于 PDF 嵌入。"""
    from data_agent.session.history import session_charts_dir, register_artifact

    session_id = _current_session_id
    if session_id:
        output_dir = session_charts_dir(session_id)
        chart_id = f"{title.replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        path = output_dir / f"{chart_id}.html"
        fig.write_html(str(path), include_plotlyjs="cdn")
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
        fig.write_html(str(path), include_plotlyjs="cdn")
        return f"Chart saved: charts/{chart_id}.html"


# 当前会话 ID（由 Agent Loop 设置）
_current_session_id = ""


def set_chart_session(session_id: str):
    global _current_session_id
    _current_session_id = session_id


@registry.register(
    name="create_chart",
    description="创建图表。chart_type: line/bar/stacked_bar/scatter/box/histogram/heatmap/pie。data_json 为 JSON 数据或数据集名称。",
)
def create_chart(
    chart_type: str,
    data: str = "",
    title: str = "Chart",
    x_col: str = "",
    y_col: str = "",
    color_col: str = "",
    data_json: str = "",
) -> str:
    fig = go.Figure()

    # 获取数据
    df = None
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
        elif datasets:
            df = workspace.get(list(datasets.keys())[0])

    if df is None:
        return "Error: 没有可用数据。请先加载数据或提供 data_json。"

    try:
        if chart_type == "line":
            if x_col and y_col:
                fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode="lines+markers", name=y_col))
            else:
                numeric_cols = df.select_dtypes(include="number").columns[:3]
                for col in numeric_cols:
                    fig.add_trace(go.Scatter(y=df[col], mode="lines+markers", name=col))

        elif chart_type == "bar":
            if x_col and y_col:
                fig.add_trace(go.Bar(x=df[x_col], y=df[y_col], name=y_col))
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

        elif chart_type == "pie":
            col = y_col or x_col
            if col and col in df.columns:
                counts = df[col].value_counts().head(10)
                fig.add_trace(go.Pie(labels=counts.index, values=counts.values))
            else:
                return "Error: pie 图需要指定一个列"

        else:
            return f"Error: 不支持的图表类型 '{chart_type}'。支持: line, bar, stacked_bar, scatter, box, histogram, heatmap, pie"

        fig.update_layout(title=title, template="plotly_white")
        path = _save_chart(fig, title)
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
