"""L6: 报告生成 & 导出工具。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Template

from data_agent.config import get_config
from data_agent.tools.registry import registry


# ── Markdown → HTML ──────────────────────────────────────
import mistune

_md_renderer = mistune.create_markdown(plugins=["table", "strikethrough"])


def _markdown_to_html(md_text: str) -> str:
    if not md_text or not md_text.strip():
        return ""
    return _md_renderer(md_text)


# ── 置信度解析 ────────────────────────────────────────────

_CONFIDENCE_MAP_HIGH = ("high", "高", "非常高", "极高", "很高")
_CONFIDENCE_MAP_LOW = ("low", "低", "很低", "极低")
_CONFIDENCE_MAP_MEDIUM = ("medium", "中", "中等", "一般", "中高", "中低")


def _parse_confidence(raw: str) -> tuple[str, str]:
    """解析置信度字段为 (level, detail)。

    level: 'high' | 'medium' | 'low'
    detail: 原始文本（用于 tooltip）
    """
    if not raw:
        return "medium", ""
    raw_lower = raw.lower().strip()
    if raw_lower in ("high", "medium", "low"):
        return raw_lower, raw
    # 只检查分隔符前的部分，避免 "中 - ...较高..." 误匹配
    prefix = raw_lower.split("-")[0].split("—")[0].split("–")[0].strip()
    for kw in _CONFIDENCE_MAP_HIGH:
        if kw in prefix:
            return "high", raw
    for kw in _CONFIDENCE_MAP_LOW:
        if kw in prefix:
            return "low", raw
    for kw in _CONFIDENCE_MAP_MEDIUM:
        if kw in prefix:
            return "medium", raw
    return "medium", raw


def _extract_data_scope() -> str:
    """从 workspace 主数据集自动提取数据范围描述。"""
    try:
        from data_agent.session.workspace import workspace
        import pandas as pd

        datasets = workspace.list_datasets()
        if not datasets:
            return ""

        # 优先使用 main 数据集
        name = "main" if "main" in datasets else list(datasets.keys())[0]
        df = workspace.get(name)
        if df is None or df.empty:
            return ""

        parts = [f"{len(df)}行 × {len(df.columns)}列"]

        # 检测日期列范围
        date_cols = df.select_dtypes(include=["datetime64", "datetimetz"]).columns
        if len(date_cols) > 0:
            col = date_cols[0]
            mn = df[col].min()
            mx = df[col].max()
            if pd.notna(mn) and pd.notna(mx):
                days = (mx - mn).days + 1
                parts.insert(0, f"{mn.strftime('%Y-%m-%d')} ~ {mx.strftime('%Y-%m-%d')}（{days}天）")

        return ", ".join(parts)
    except Exception:
        return ""


# ── 模板 ──────────────────────────────────────────────────

REPORT_TEMPLATE_DETAILED = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
{% if has_charts %}
<script>
if (typeof Plotly === 'undefined') {
  document.write('<script src="/static/js/plotly-3.5.0.min.js"><\/script>');
}
if (typeof Plotly === 'undefined') {
  document.write('<script src="https://cdn.plot.ly/plotly-3.5.0.min.js" crossorigin="anonymous"><\/script>');
}
</script>
{% endif %}
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
       max-width: 960px; margin: 0 auto; padding: 40px 20px; color: #333; line-height: 1.7; }
h1 { color: #1a1a2e; border-bottom: 3px solid #16213e; padding-bottom: 12px; }
h2 { color: #16213e; border-bottom: 1px solid #e0e0e0; padding-bottom: 8px; margin-top: 48px; }
h3 { color: #0f3460; margin-top: 28px; }
h4 { color: #333; margin-bottom: 8px; }
.metadata { color: #999; font-size: 13px; margin-bottom: 24px; }

/* Markdown rendered content */
.md-content table { border-collapse: collapse; width: 100%; margin: 12px 0; }
.md-content th, .md-content td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
.md-content th { background: #f5f5f5; font-weight: 600; }
.md-content ul, .md-content ol { padding-left: 20px; margin: 8px 0; }
.md-content strong { color: #1a1a2e; }
.md-content p { margin: 6px 0; }

/* Section markers */
.part-marker { font-size: 14px; color: #666; text-transform: uppercase; letter-spacing: 2px;
               margin-bottom: 4px; border-bottom: none; }

/* Insight cards */
.insight-card { background: #f8f9fa; border-left: 4px solid #16213e; padding: 16px 20px;
                margin: 16px 0; border-radius: 4px; }
.insight-card.trend { border-left-color: #2196F3; }
.insight-card.anomaly { border-left-color: #f44336; }
.insight-card.contribution { border-left-color: #4CAF50; }
.insight-card.driver { border-left-color: #FF9800; }

/* Confidence badge */
.confidence-badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
                    font-size: 12px; font-weight: 600; margin-left: 8px; }
.confidence-badge.high { background: #c8e6c9; color: #2e7d32; }
.confidence-badge.medium { background: #fff9c4; color: #f57f17; }
.confidence-badge.low { background: #ffcdd2; color: #c62828; }

.method-inline { color: #666; font-style: italic; font-size: 13px; margin-top: 8px; }
.action { background: #e3f2fd; padding: 8px 12px; border-radius: 4px; margin-top: 8px; }

/* Chart containers */
.chart-container { margin: 24px 0; padding: 16px; background: #fff;
                   border: 1px solid #e0e0e0; border-radius: 8px; }

/* Data tables */
table.data-table { border-collapse: collapse; width: 100%; margin: 16px 0; }
table.data-table th, table.data-table td { border: 1px solid #ddd; padding: 10px; text-align: left; }
table.data-table th { background: #f5f5f5; }

/* Collapsible details */
details { margin-top: 8px; }
summary { cursor: pointer; color: #0f3460; font-size: 14px; }
</style>
</head>
<body>
<h1>{{ title }}</h1>
<div class="metadata">Generated: {{ date }}{% if data_scope %} | Data: {{ data_scope }}{% endif %}</div>

<!-- Part 1: Core Conclusions -->
<div class="part-marker">PART 1</div>
<h2>核心结论与摘要</h2>
{% if rendered_summary %}
<div class="md-content">
{{ rendered_summary }}
</div>
{% elif top_insights %}
<div class="md-content">
<p>基于数据分析的核心发现：</p>
<ul>
{% for insight in top_insights[:3] %}
<li><strong>{{ insight.title }}</strong> — {{ insight.description_html | replace('<div class=\"md-content\">', '') | replace('</div>', '') | striptags | truncate(120) }}</li>
{% endfor %}
</ul>
</div>
{% endif %}

{% if top_insights %}
{% for insight in top_insights %}
<div class="insight-card {{ insight.card_type }}">
  <strong>{{ insight.title }}</strong>
  <span class="confidence-badge {{ insight.confidence_level }}"
        {% if insight.confidence_detail %}title="{{ insight.confidence_detail }}"{% endif %}>
    {{ insight.confidence_level | upper }}
  </span>
  <div class="md-content">{{ insight.description_html }}</div>
  {% if insight.chart_html %}
  {{ insight.chart_html }}
  {% endif %}
  {% if insight.method %}
  <div class="method-inline">方法: {{ insight.method }}</div>
  {% endif %}
  {% if insight.recommended_action %}
  <div class="action"><strong>建议:</strong> {{ insight.recommended_action }}</div>
  {% endif %}
</div>
{% endfor %}
{% endif %}

<!-- Part 2: Key Findings & Recommendations -->
<div class="part-marker">PART 2</div>
<h2>关键发现与建议</h2>
{% for group_name, items in findings_by_type %}
<h3>{{ group_name }}</h3>
{% for item in items %}
<div class="insight-card {{ item.card_type }}">
  <strong>{{ item.title }}</strong>
  <span class="confidence-badge {{ item.confidence_level }}"
        {% if item.confidence_detail %}title="{{ item.confidence_detail }}"{% endif %}>
    {{ item.confidence_level | upper }}
  </span>
  <div class="md-content">{{ item.description_html }}</div>
  {% if item.chart_html %}
  {{ item.chart_html }}
  {% endif %}
  {% if item.method %}
  <div class="method-inline">方法: {{ item.method }}</div>
  {% endif %}
  {% if item.recommended_action %}
  <div class="action"><strong>建议:</strong> {{ item.recommended_action }}</div>
  {% endif %}
  {% if item.competing_html %}
  <details><summary>竞争假设</summary>{{ item.competing_html }}</details>
  {% endif %}
</div>
{% endfor %}
{% endfor %}

<!-- Part 3: Supporting Evidence -->
{% if charts_html or extra_data %}
<div class="part-marker">PART 3</div>
<h2>支撑证据与数据</h2>
{% if charts_html %}
<h3>图表与可视化</h3>
{{ charts_html }}
{% endif %}
{% if extra_data %}
{{ extra_data }}
{% endif %}
{% endif %}
</body>
</html>""")

REPORT_TEMPLATE_EXECUTIVE = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
{% if has_charts %}
<script>
if (typeof Plotly === 'undefined') {
  document.write('<script src="/static/js/plotly-3.5.0.min.js"><\/script>');
}
if (typeof Plotly === 'undefined') {
  document.write('<script src="https://cdn.plot.ly/plotly-3.5.0.min.js" crossorigin="anonymous"><\/script>');
}
</script>
{% endif %}
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
       max-width: 960px; margin: 0 auto; padding: 40px 20px; color: #333; line-height: 1.7; }
h1 { color: #1a1a2e; border-bottom: 3px solid #16213e; padding-bottom: 12px; }
h2 { color: #16213e; border-bottom: 1px solid #e0e0e0; padding-bottom: 8px; margin-top: 36px; }
.metadata { color: #999; font-size: 13px; margin-bottom: 24px; }
.md-content table { border-collapse: collapse; width: 100%; margin: 12px 0; }
.md-content th, .md-content td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
.md-content th { background: #f5f5f5; font-weight: 600; }
.md-content ul, .md-content ol { padding-left: 20px; margin: 8px 0; }
.md-content strong { color: #1a1a2e; }
.md-content p { margin: 6px 0; }
.insight-card { background: #f8f9fa; border-left: 4px solid #16213e; padding: 14px 18px;
                margin: 14px 0; border-radius: 4px; }
.insight-card.trend { border-left-color: #2196F3; }
.insight-card.anomaly { border-left-color: #f44336; }
.insight-card.contribution { border-left-color: #4CAF50; }
.insight-card.driver { border-left-color: #FF9800; }
.confidence-badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
                    font-size: 12px; font-weight: 600; margin-left: 8px; }
.confidence-badge.high { background: #c8e6c9; color: #2e7d32; }
.confidence-badge.medium { background: #fff9c4; color: #f57f17; }
.confidence-badge.low { background: #ffcdd2; color: #c62828; }
.action { background: #e3f2fd; padding: 8px 12px; border-radius: 4px; margin-top: 8px; }
.chart-container { margin: 20px 0; padding: 16px; background: #fff;
                   border: 1px solid #e0e0e0; border-radius: 8px; }
</style>
</head>
<body>
<h1>{{ title }}</h1>
<div class="metadata">Generated: {{ date }}</div>

{% if rendered_summary %}
<h2>Executive Summary</h2>
<div class="md-content">
{{ rendered_summary }}
</div>
{% endif %}

{% if all_insights %}
<h2>Key Findings</h2>
{% for item in all_insights %}
<div class="insight-card {{ item.card_type }}">
  <strong>{{ item.title }}</strong>
  <span class="confidence-badge {{ item.confidence_level }}"
        {% if item.confidence_detail %}title="{{ item.confidence_detail }}"{% endif %}>
    {{ item.confidence_level | upper }}
  </span>
  <div class="md-content">{{ item.description_html }}</div>
  {% if item.recommended_action %}
  <div class="action"><strong>Action:</strong> {{ item.recommended_action }}</div>
  {% endif %}
</div>
{% endfor %}
{% endif %}

{% if charts_html %}
<h2>Visualizations</h2>
{{ charts_html }}
{% endif %}
</body>
</html>""")


def _prepare_insight(item: dict, chart_entries: list = None, used_filenames: set = None) -> dict:
    """预处理单条 insight：解析置信度、渲染描述 markdown、匹配图表、构建竞争假设 HTML。"""
    confidence_level, confidence_detail = _parse_confidence(item.get("confidence", "medium"))
    card_type = item.get("type", "trend").lower()

    # Render description from markdown to HTML
    desc = item.get("description", "")
    description_html = _markdown_to_html(desc) if desc else ""

    # Match chart if chart keyword provided
    chart_html = ""
    chart_keyword = item.get("chart", "")
    if chart_keyword and chart_entries:
        from data_agent.tools.visualization import match_chart
        matched = match_chart(chart_entries, chart_keyword)
        if matched:
            chart_html = matched["html"]
            if used_filenames is not None:
                used_filenames.add(matched["filename"])

    # Build competing hypotheses HTML
    competing_html = ""
    hypotheses = item.get("competing_hypotheses")
    if hypotheses:
        lines = []
        for h in hypotheses:
            factor = h.get("factor", "?")
            if h.get("excluded"):
                lines.append(f"<li>{factor}: {h.get('excluded_reason', '排除')}</li>")
            else:
                lines.append(f"<li>{factor}: contribution {h.get('contribution', 'N/A')}</li>")
        competing_html = "<ul>" + "".join(lines) + "</ul>"

    return {
        "title": item.get("title", "Finding"),
        "card_type": card_type,
        "confidence_level": confidence_level,
        "confidence_detail": confidence_detail,
        "description_html": description_html,
        "chart_html": chart_html,
        "method": item.get("method", ""),
        "recommended_action": item.get("recommended_action", ""),
        "competing_html": competing_html,
    }


def _output_dir_for_session():
    """获取当前会话的报告输出目录。"""
    from data_agent.session.history import session_reports_dir
    from data_agent.tools.visualization import _current_session_id

    if _current_session_id:
        return session_reports_dir(_current_session_id), _current_session_id

    cfg = get_config()
    output_dir = cfg.project_resolved / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, None


@registry.register(
    name="generate_report",
    description=(
        "从洞察列表生成结构化分析报告（HTML格式）。"
        "insights 参数为 JSON 数组，每个元素含 title/type/description/confidence/method/recommended_action/chart。"
        "chart 字段为图表标题关键词，用于关联对应图表嵌入到洞察卡片旁。"
        "confidence 必须为 'high'/'medium'/'low' 三选一。"
        "description 支持 Markdown 格式（表格、列表、加粗）。"
        "图表会自动从当前会话嵌入，无需手动传递 charts_html。"
        "style: 'detailed'（默认，金字塔结构三段式）或 'executive'（精简执行摘要）。"
    ),
)
def generate_report(
    title: str = "Data Analysis Report",
    insights: str = "[]",
    charts_html: str = "",
    summary: str = "",
    style: str = "detailed",
    data_scope: str = "",
) -> str:
    output_dir, session_id = _output_dir_for_session()

    # 解析洞察
    try:
        insight_list = json.loads(insights) if isinstance(insights, str) else insights
    except json.JSONDecodeError:
        insight_list = []

    is_executive = style.strip().lower() == "executive"

    # 自动提取 data_scope（如果为空）
    if not data_scope:
        data_scope = _extract_data_scope()

    # Summary 兜底：从 insights 自动生成摘要
    if not summary and insight_list:
        summary_parts = []
        for item in insight_list[:5]:
            t = item.get("title", "")
            d = item.get("description", "")
            if t:
                summary_parts.append(f"- **{t}**: {d[:100]}" if d else f"- **{t}**")
        if summary_parts:
            summary = "### 核心发现\n\n" + "\n".join(summary_parts)

    # 渲染 summary markdown → HTML
    rendered_summary = _markdown_to_html(summary)

    # 收集图表条目（用于洞察-图表关联）
    chart_entries = []
    if session_id:
        from data_agent.tools.visualization import get_chart_entries
        chart_entries = get_chart_entries(session_id)

    # 预处理所有 insights，关联匹配图表
    used_filenames: set[str] = set()
    prepared = [_prepare_insight(item, chart_entries, used_filenames) for item in insight_list]

    # 剩余未关联的图表 → PART 3
    remaining_chart_html = "\n".join(
        entry["html"] for entry in chart_entries if entry["filename"] not in used_filenames
    )

    # 如果显式传了 charts_html，追加到剩余图表
    all_charts_html = (charts_html + "\n" + remaining_chart_html).strip() if charts_html else remaining_chart_html
    has_charts = bool(all_charts_html)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_title = re.sub(r'[^\w]', '_', title)[:40]

    if is_executive:
        html = REPORT_TEMPLATE_EXECUTIVE.render(
            title=title,
            date=timestamp,
            rendered_summary=rendered_summary,
            all_insights=prepared[:7],
            charts_html=all_charts_html,
            has_charts=has_charts,
        )
    else:
        # 金字塔结构：Part 1 取前 3-5 条，Part 2 取剩余按类型分组
        top_count = min(5, max(3, len(prepared) // 2))
        top_insights = prepared[:top_count]
        remaining = prepared[top_count:]

        # 按 type 分组
        by_type: dict[str, list] = {}
        for item in remaining:
            t = item["card_type"]
            by_type.setdefault(t, []).append(item)

        # 类型中文名映射
        type_names = {
            "trend": "趋势分析",
            "anomaly": "异常检测",
            "contribution": "贡献分析",
            "driver": "驱动分析",
            "correlation": "相关性分析",
            "distribution": "分布分析",
            "forecast": "预测分析",
        }
        findings_by_type = [(type_names.get(t, t.title() + " Analysis"), items) for t, items in by_type.items()]

        html = REPORT_TEMPLATE_DETAILED.render(
            title=title,
            date=timestamp,
            data_scope=data_scope,
            rendered_summary=rendered_summary,
            top_insights=top_insights,
            findings_by_type=findings_by_type,
            charts_html=all_charts_html,
            has_charts=has_charts,
            extra_data="",
        )

    # 写入文件
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{safe_title}_{ts}.html"
    filepath = output_dir / filename
    filepath.write_text(html, encoding="utf-8")

    # 注册到 artifact 清单
    if session_id:
        from data_agent.session.history import register_artifact
        artifact_path = f"sessions/{session_id}/reports/{filename}"
        register_artifact(session_id, artifact_path, "report", title)
        return f"Report generated: {artifact_path}"

    return f"Report generated: reports/{filename}"


@registry.register(
    name="export_report_markdown",
    description="将报告导出为 Markdown 格式。",
)
def export_report_markdown(
    title: str = "Data Analysis Report",
    insights: str = "[]",
    summary: str = "",
) -> str:
    output_dir, session_id = _output_dir_for_session()

    try:
        insight_list = json.loads(insights) if isinstance(insights, str) else insights
    except json.JSONDecodeError:
        insight_list = []

    md_lines = [f"# {title}", f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]

    # Part 1: Core Conclusions
    if summary:
        md_lines.append("## 核心结论与摘要\n")
        md_lines.append(summary)
        md_lines.append("")

    # Part 2: Key Findings
    if insight_list:
        md_lines.append("## 关键发现与建议\n")
        for ins in insight_list:
            md_lines.append(f"### {ins.get('title', 'Finding')}")
            md_lines.append(f"- **Type**: {ins.get('type', 'N/A')}")
            conf_level, conf_detail = _parse_confidence(ins.get("confidence", "medium"))
            md_lines.append(f"- **Confidence**: {conf_level.upper()}" + (f" ({conf_detail})" if conf_detail else ""))
            md_lines.append(f"- **Description**: {ins.get('description', '')}")
            if ins.get("method"):
                md_lines.append(f"- **Method**: {ins['method']}")
            if ins.get("recommended_action"):
                md_lines.append(f"- **Recommendation**: {ins['recommended_action']}")
            md_lines.append("")

    # Part 3: Chart references
    if session_id:
        from data_agent.session.history import session_charts_dir
        charts_dir = session_charts_dir(session_id)
        chart_files = sorted(charts_dir.glob("*.html"))
        if chart_files:
            md_lines.append("## 支撑证据：图表\n")
            for cf in chart_files:
                stem = cf.stem.rsplit("_", 1)[0] if "_" in cf.stem else cf.stem
                md_lines.append(f"- [{stem}](../charts/{cf.name})")
            md_lines.append("")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}.md"
    filepath = output_dir / filename
    filepath.write_text("\n".join(md_lines), encoding="utf-8")

    if session_id:
        from data_agent.session.history import register_artifact
        artifact_path = f"sessions/{session_id}/reports/{filename}"
        register_artifact(session_id, artifact_path, "report_md", title)
        return f"Markdown report: {artifact_path}"

    return f"Markdown report: reports/{filename}"


def _generate_chart_images(charts_dir: Path) -> dict[str, str]:
    """读取 charts 目录中的 PNG 静态图片，返回 {html_filename: base64_data_uri}。"""
    import base64

    images = {}
    for png_file in sorted(charts_dir.glob("*.png")):
        try:
            b64 = base64.b64encode(png_file.read_bytes()).decode("ascii")
            # PNG 与 HTML 同名但后缀不同
            html_name = png_file.stem + ".html"
            images[html_name] = f"data:image/png;base64,{b64}"
        except Exception:
            continue
    return images


@registry.register(
    name="export_report_pdf",
    description="将 HTML 报告转换为 PDF（内嵌静态图表）。",
)
def _cjk_pdf_css() -> str:
    """返回 CJK 兼容的 CSS 片段，注入 HTML 用于 PDF 渲染。

    xhtml2pdf 内置了 STSong-Light（宋体）CID 字体映射，
    直接使用即可渲染中文，无需额外字体文件。
    """
    return (
        '<style>'
        'body, p, div, span, td, th, li, h1, h2, h3, h4, h5, h6, strong, b, em, i {'
        '  font-family: STSong-Light, sans-serif;'
        '}'
        '</style>'
    )


def export_report_pdf(html_path: str = "") -> str:
    try:
        from xhtml2pdf import pisa

        output_dir, session_id = _output_dir_for_session()

        if html_path:
            source = output_dir / html_path
        else:
            html_files = sorted(output_dir.glob("*.html"), reverse=True)
            if not html_files:
                return "Error: 没有 HTML 报告可转换"
            source = html_files[0]

        if not source.exists():
            return f"Error: 文件不存在: {source}"

        pdf_path = source.with_suffix(".pdf")

        html_content = source.read_text(encoding="utf-8")

        # 注入 CJK 字体 CSS（STSong-Light CID font，xhtml2pdf 内置支持）
        html_content = html_content.replace("</head>", f"{_cjk_pdf_css()}\n</head>", 1)

        # 移除 Plotly CDN script 标签（PDF 不需要 JS）
        html_content = re.sub(
            r'<script[^>]*plotly[^>]*\.js[^>]*></script>',
            '', html_content, flags=re.IGNORECASE,
        )
        html_content = re.sub(
            r'<script>window\.PlotlyConfig.*?</script>',
            '', html_content, flags=re.DOTALL,
        )

        # 尝试生成静态图表图片
        if session_id:
            from data_agent.session.history import session_charts_dir
            charts_dir = session_charts_dir(session_id)
            chart_images = _generate_chart_images(charts_dir)

            if chart_images:
                # 将 Plotly chart-container 替换为静态图片
                def _replace_chart_with_img(match):
                    container = match.group(0)
                    for filename, data_uri in chart_images.items():
                        stem = filename.rsplit("_", 1)[0] if "_" in filename else filename.replace(".html", "")
                        if stem in container:
                            return (
                                f'<div class="chart-container">'
                                f'<h4>{stem}</h4>'
                                f'<img src="{data_uri}" style="max-width:100%;height:auto;" />'
                                f'</div>'
                            )
                    # 如果无法匹配，使用占位文字
                    return (
                        '<div class="chart-container">'
                        '<p style="color:#999;text-align:center;">[图表，请在浏览器中查看 HTML 版本]</p>'
                        '</div>'
                    )

                html_content = re.sub(
                    r'<div class="chart-container">.*?</div>\s*(?:<script>.*?</script>\s*)*</div>',
                    _replace_chart_with_img,
                    html_content, flags=re.DOTALL,
                )
            else:
                # 无法生成图片，使用占位文字
                html_content = re.sub(
                    r'<div class="chart-container">.*?</div>\s*(?:<script>.*?</script>\s*)*</div>',
                    '<div class="chart-container"><p style="color:#999;text-align:center;">'
                    '[图表，请在浏览器中查看 HTML 版本]</p></div>',
                    html_content, flags=re.DOTALL,
                )
        else:
            # 无 session，移除所有 script 标签和 Plotly 内容
            html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL)

        with open(pdf_path, "wb") as f:
            pisa_status = pisa.CreatePDF(html_content, dest=f)

        if pisa_status.err:
            return f"PDF 导出完成（有 {pisa_status.err} 个警告）: reports/{pdf_path.name}"

        result_msg = f"PDF exported: reports/{pdf_path.name}"
        if session_id:
            from data_agent.session.history import register_artifact
            artifact_path = f"sessions/{session_id}/reports/{pdf_path.name}"
            register_artifact(session_id, artifact_path, "report_pdf", pdf_path.stem)
            result_msg = f"PDF exported: {artifact_path}"

        return result_msg
    except ImportError:
        return "Error: xhtml2pdf 未安装，请运行 pip install xhtml2pdf"
    except Exception as e:
        return f"Error exporting PDF: {e}"


@registry.register(
    name="export_conversation",
    description=(
        "将当前对话中的分析结果导出为 HTML 或 Markdown 格式。"
        "自动提取对话中的分析结论、数据表格和图表，生成结构化文档。"
        "format 参数: 'html'（默认）或 'markdown'。"
    ),
)
def export_conversation(
    title: str = "Analysis Export",
    format: str = "html",
    include_charts: bool = True,
) -> str:
    from data_agent.session.history import (
        _session_dir,
        list_artifacts,
        register_artifact,
    )
    from data_agent.tools.visualization import _current_session_id

    session_id = _current_session_id
    if not session_id:
        return "Error: 无当前会话，无法导出"

    output_dir = _session_dir(session_id) / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 读取对话历史
    conv_path = _session_dir(session_id) / "conversation.json"
    if not conv_path.exists():
        return "Error: 当前会话无对话记录"

    messages = json.loads(conv_path.read_text(encoding="utf-8"))

    # 提取 assistant 分析内容（过滤 tool call，只保留文本回复）
    analysis_blocks = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        # 跳过纯工具调用结果（通常是简短的状态消息）
        if len(content.strip()) > 30:
            analysis_blocks.append(content.strip())

    if not analysis_blocks:
        return "Error: 当前对话中没有分析结果可导出"

    # 收集图表
    charts_html = ""
    if include_charts:
        from data_agent.tools.visualization import get_chart_embed_html
        charts_html = get_chart_embed_html(session_id)

    has_charts = bool(charts_html and charts_html.strip())

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if format.strip().lower() == "markdown":
        # Markdown 导出
        md_lines = [f"# {title}", f"\n_Generated: {timestamp}_\n"]
        for i, block in enumerate(analysis_blocks, 1):
            md_lines.append(f"## 分析 {i}\n")
            md_lines.append(block)
            md_lines.append("")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"conversation_{ts}.md"
        filepath = output_dir / filename
        filepath.write_text("\n".join(md_lines), encoding="utf-8")
        artifact_path = f"sessions/{session_id}/reports/{filename}"
        register_artifact(session_id, artifact_path, "conversation_md", title)
        return f"Conversation exported: {artifact_path}"

    # HTML 导出
    rendered_blocks = []
    for block in analysis_blocks:
        rendered_blocks.append(f'<div class="md-content">{_markdown_to_html(block)}</div>')

    html = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
{% if has_charts %}
<script>
if (typeof Plotly === 'undefined') {
  document.write('<script src="/static/js/plotly-3.5.0.min.js"><\/script>');
}
if (typeof Plotly === 'undefined') {
  document.write('<script src="https://cdn.plot.ly/plotly-3.5.0.min.js" crossorigin="anonymous"><\/script>');
}
</script>
{% endif %}
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
       max-width: 960px; margin: 0 auto; padding: 40px 20px; color: #333; line-height: 1.7; }
h1 { color: #1a1a2e; border-bottom: 3px solid #16213e; padding-bottom: 12px; }
h2 { color: #16213e; border-bottom: 1px solid #e0e0e0; padding-bottom: 8px; margin-top: 36px; }
.metadata { color: #999; font-size: 13px; margin-bottom: 24px; }
.md-content table { border-collapse: collapse; width: 100%; margin: 12px 0; }
.md-content th, .md-content td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
.md-content th { background: #f5f5f5; font-weight: 600; }
.md-content ul, .md-content ol { padding-left: 20px; margin: 8px 0; }
.md-content strong { color: #1a1a2e; }
.md-content p { margin: 6px 0; }
.analysis-block { margin: 20px 0; padding: 16px 20px; background: #fafafa;
                  border-left: 3px solid #16213e; border-radius: 4px; }
.chart-container { margin: 24px 0; padding: 16px; background: #fff;
                   border: 1px solid #e0e0e0; border-radius: 8px; }
</style>
</head>
<body>
<h1>{{ title }}</h1>
<div class="metadata">Generated: {{ date }}</div>
{% for block in blocks %}
<div class="analysis-block">
{{ block }}
</div>
{% endfor %}
{% if charts_html %}
<h2>Charts</h2>
{{ charts_html }}
{% endif %}
</body>
</html>""").render(
        title=title,
        date=timestamp,
        blocks=rendered_blocks,
        charts_html=charts_html,
        has_charts=has_charts,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"conversation_{ts}.html"
    filepath = output_dir / filename
    filepath.write_text(html, encoding="utf-8")

    artifact_path = f"sessions/{session_id}/reports/{filename}"
    register_artifact(session_id, artifact_path, "conversation_html", title)
    return f"Conversation exported: {artifact_path}"
