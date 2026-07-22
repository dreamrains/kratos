"""Evidence-backed report and conversation export tools."""

from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import mistune
from jinja2 import Template

from data_agent.config import get_config
from data_agent.tools.registry import registry


_md_renderer = mistune.create_markdown(plugins=["table", "strikethrough"])
_STAT_DETAIL_FIELDS = [
    "metrics",
    "sample_size",
    "time_scope",
    "calculation_method",
    "method_detail",
    "denominator",
    "missingness",
    "estimand",
    "effect_estimate",
    "sample_adequacy",
    "time_frequency",
    "missing_intervals",
    "window_comparability",
    "autocorrelation_awareness",
    "significance",
    "correlation",
    "confidence_interval",
]


def _expected_statistical_fields(record: dict[str, Any]) -> list[str]:
    from data_agent.tools.analysis_flow import statistical_detail_fields

    return statistical_detail_fields(record)


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _session_id() -> str:
    try:
        from data_agent.agent.context import get_current_context

        ctx = get_current_context()
        if ctx is not None:
            return ctx.session_id
    except Exception:
        pass
    try:
        from data_agent.tools.visualization import current_session_id

        return current_session_id()
    except Exception:
        return ""


def _analysis_state():
    try:
        from data_agent.agent.analysis_state import current_analysis_state

        return current_analysis_state()
    except Exception:
        return None


def _report_dirs(session_id: str) -> tuple[Path, str]:
    from data_agent.session.history import session_reports_dir

    out_dir = session_reports_dir(session_id)
    return out_dir, f"sessions/{session_id}/reports"


def _write_report_artifact(
    session_id: str,
    title: str,
    content: str,
    suffix: str,
    artifact_type: str,
    prefix: str,
) -> str:
    from data_agent.session.history import register_artifact

    out_dir, artifact_prefix = _report_dirs(session_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", title).strip("_")[:48] or prefix
    filename = f"{prefix}_{safe_title}_{ts}.{suffix}"
    path = out_dir / filename
    path.write_text(content, encoding="utf-8")
    artifact_path = f"{artifact_prefix}/{filename}"
    register_artifact(session_id, artifact_path, artifact_type, title)
    return artifact_path


def _sanitize_export_markdown(markdown: str) -> str:
    cleaned = re.sub(
        r"\s+on[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "",
        markdown or "",
        flags=re.IGNORECASE,
    )
    return re.sub(r"(?i)javascript\s*:", "#", cleaned)


def _markdown_to_html(markdown: str) -> str:
    if not markdown:
        return ""
    return _md_renderer(_sanitize_export_markdown(markdown))


def _chart_marker(kind: str, key: str) -> str:
    return f"[[chart-{kind}:{key}]]"


def _inject_chart_markers(body: str, chart_entries: list[dict[str, Any]] | None = None) -> tuple[str, set[str]]:
    if not chart_entries:
        return body, set()

    by_id: dict[str, list[dict[str, Any]]] = {}
    by_evidence: dict[str, list[dict[str, Any]]] = {}
    for entry in chart_entries:
        chart_id = str(entry.get("chart_id") or "")
        if chart_id:
            by_id.setdefault(chart_id, []).append(entry)
        for evidence_id in entry.get("metadata", {}).get("evidence_ids") or []:
            by_evidence.setdefault(str(evidence_id), []).append(entry)

    used: set[str] = set()
    markers = sorted(set(re.findall(r"\[\[chart-(id|evidence):([^\]\n]+)\]\]", body)))
    for kind, key in markers:
        entries = by_id.get(key, []) if kind == "id" else by_evidence.get(key, [])
        html = "\n".join(entry["html"] for entry in entries)
        for entry in entries:
            if entry.get("chart_id"):
                used.add(str(entry["chart_id"]))
        marker = _chart_marker(kind, key)
        body = body.replace(f"<p>{marker}</p>", html)
        body = body.replace(marker, html)
    return body, used


def _html_from_markdown(
    title: str,
    markdown: str,
    charts_html: str = "",
    chart_entries: list[dict[str, Any]] | None = None,
) -> str:
    body = _markdown_to_html(markdown)
    if chart_entries:
        body, used_chart_ids = _inject_chart_markers(body, chart_entries)
        supplemental = [
            entry["html"]
            for entry in chart_entries
            if str(entry.get("chart_id") or "") not in used_chart_ids
        ]
        charts_html = "\n".join(supplemental)
    return Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
{% if charts_html %}<script>if (typeof Plotly === 'undefined') { document.write('<script src="/static/js/plotly-3.5.0.min.js"><\\/script>'); }</script>{% endif %}
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;max-width:1040px;margin:0 auto;padding:40px 22px;color:#243042;line-height:1.72}
h1{border-bottom:3px solid #1f3a5f;padding-bottom:12px;color:#172033}
h2{border-bottom:1px solid #d9e2ef;padding-bottom:8px;margin-top:34px;color:#1f3a5f}
h3{margin-top:22px;color:#284766}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{border:1px solid #d8dee9;padding:8px 10px;text-align:left;vertical-align:top}
th{background:#eef3f9}
.analysis-block,.evidence-card,.chart-container{margin:18px 0;padding:14px 18px;border:1px solid #d8dee9;border-radius:6px;background:#fff}
.evidence-card{border-left:4px solid #2b6cb0;background:#f8fbff}
.warning{color:#8a5a00;background:#fff8e1;padding:8px 10px;border-radius:4px}
.metadata{color:#667085;font-size:13px}
code{background:#eef2f7;padding:2px 5px;border-radius:4px}
</style>
</head>
<body>
<h1>{{ title }}</h1>
<div class="analysis-block">{{ body }}</div>
{{ charts_html }}
</body>
</html>""").render(
        title=escape(title),
        body=body,
        charts_html=charts_html,
    )


def _export_pdf_from_html(session_id: str, html_artifact_path: str, title: str) -> dict[str, Any]:
    out_dir, _ = _report_dirs(session_id)
    html_path = get_config().sessions_resolved.parent / html_artifact_path
    pdf_name = Path(html_artifact_path).with_suffix(".pdf").name
    pdf_path = out_dir / pdf_name
    try:
        from xhtml2pdf import pisa
    except Exception as exc:
        return {
            "status": "degraded",
            "format": "pdf",
            "reason": f"PDF dependency unavailable: {exc}",
            "fallback_artifact_path": html_artifact_path,
        }
    try:
        with pdf_path.open("wb") as f:
            status = pisa.CreatePDF(html_path.read_text(encoding="utf-8"), dest=f)
        if status.err:
            return {
                "status": "degraded",
                "format": "pdf",
                "reason": f"PDF render returned {status.err} errors",
                "fallback_artifact_path": html_artifact_path,
            }
    except Exception as exc:
        return {
            "status": "degraded",
            "format": "pdf",
            "reason": f"PDF render failed: {exc}",
            "fallback_artifact_path": html_artifact_path,
        }

    from data_agent.session.history import register_artifact

    artifact_path = f"sessions/{session_id}/reports/{pdf_name}"
    register_artifact(session_id, artifact_path, "report_pdf", title)
    return {"status": "exported", "format": "pdf", "artifact_path": artifact_path}


def _records_to_markdown(title: str, goal: str, records: list[dict[str, Any]], brief: bool = False) -> str:
    lines = [f"# {title}", "", f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]
    if goal:
        lines.extend([f"Goal: {goal}", ""])
    heading = "## Key Conclusions" if brief else "## One-Page Conclusion"
    lines.extend([heading, ""])
    for record in records:
        lines.extend([
            f"### {record.get('claim', 'Untitled finding')}",
            f"- Evidence ID: `{record.get('id', '-')}`",
            f"- Dataset: {record.get('dataset', '-')}",
            f"- Method: {record.get('method', '-')}",
            f"- Result: {record.get('result_summary', '-')}",
            f"- Confidence: {record.get('confidence', '-')}",
            f"- Limitations: {record.get('limitations', '-')}",
            "",
        ])
        if not brief:
            _append_statistical_details(lines, record)
    if not brief:
        lines.extend(_statistical_gap_lines(records))
    return "\n".join(lines)


def _append_statistical_details(lines: list[str], record: dict[str, Any]) -> None:
    lines.extend(["#### Core Metrics And Statistical Details", ""])
    details = []
    for field in _STAT_DETAIL_FIELDS:
        value = record.get(field)
        if value in (None, "", [], {}):
            continue
        rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        details.append((field, rendered))
    if details:
        lines.extend(["| Field | Value |", "| --- | --- |"])
        for field, rendered in details:
            lines.append(f"| {field} | {rendered} |")
        lines.append("")
    else:
        lines.extend(["No structured statistical details recorded.", ""])


def _statistical_gap_lines(records: list[dict[str, Any]]) -> list[str]:
    missing = sorted({
        field
        for record in records
        for field in _expected_statistical_fields(record)
        if record.get(field) in (None, "", [], {})
    })
    if not missing:
        return []
    return ["## Statistical Detail Gaps / 统计说明缺口", "", "These fields are not yet recorded in EvidenceRecord and should be treated cautiously:", "", *[f"- `{field}`" for field in missing], ""]

def _statistical_quality_lines(records: list[dict[str, Any]]) -> list[str]:
    lines = ["## Statistical Explanation Quality", ""]
    for record in records:
        gaps = record.get("statistical_detail_gaps")
        if gaps is None:
            gaps = [
                field
                for field in _expected_statistical_fields(record)
                if record.get(field) in (None, "", [], {})
            ]
        status = "complete" if not gaps else "needs supplementation"
        lines.append(f"- `{record.get('id', '-')}` {record.get('claim', '')}: {status}")
        if gaps:
            lines.append(f"  - Missing: {', '.join(str(gap) for gap in gaps)}")
    lines.append("")
    return lines

def _formal_markdown(
    title: str,
    goal: str,
    records: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    *,
    include_chart_markers: bool = False,
) -> str:
    lines = [f"# {title}", "", f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]
    if goal:
        lines.extend([f"Goal: {goal}", ""])
    lines.extend(["## One-Page Conclusion / 一页结论摘要", ""])
    for record in records[:5]:
        lines.append(f"- **{record.get('claim', 'Untitled finding')}**: {record.get('result_summary', '')} (confidence: {record.get('confidence', '-')})")
    lines.append("")
    lines.extend(["## Expert Insights / 核心结论与业务含义", ""])
    for insight in insights:
        conclusion = insight.get("conclusion") or insight.get("title") or "Insight"
        business_meaning = insight.get("business_meaning") or insight.get("summary") or ""
        recommendation_confidence = insight.get("recommendation_confidence") or insight.get("confidence") or "-"
        next_analysis = insight.get("next_analysis") or []
        if isinstance(next_analysis, str):
            next_analysis = [next_analysis]
        lines.extend([
            f"### {conclusion}",
            business_meaning,
            f"- Statistical explanation: {insight.get('statistical_explanation', '-')}",
            f"- Recommendation: {insight.get('recommendation', '-')}",
            f"- Recommendation confidence: {recommendation_confidence}",
            f"- Limitations: {insight.get('limitations', '-')}",
            f"- Next analysis: {', '.join(str(item) for item in next_analysis) if next_analysis else '-'}",
            "",
        ])
        if include_chart_markers:
            for chart_id in insight.get("chart_ids") or []:
                lines.extend([_chart_marker("id", str(chart_id)), ""])
            for evidence_id in insight.get("evidence_ids") or []:
                lines.extend([_chart_marker("evidence", str(evidence_id)), ""])
    if not insights:
        for record in records:
            lines.extend([f"### {record.get('claim', 'Conclusion')}", record.get("result_summary", ""), ""])
            if include_chart_markers and record.get("id"):
                lines.extend([_chart_marker("evidence", str(record.get("id"))), ""])
    lines.extend(["## Core Metrics And Statistical Explanation", ""])
    for record in records:
        lines.append(f"### Evidence `{record.get('id', '-')}`")
        _append_statistical_details(lines, record)
    lines.extend(_statistical_quality_lines(records))
    lines.extend(["## Evidence Chain And Charts", ""])
    for record in records:
        lines.extend([
            f"- `{record.get('id', '-')}` {record.get('claim', '')}",
            f"  - Dataset: {record.get('dataset', '-')}",
            f"  - Tools: {', '.join(record.get('tool_calls') or [])}",
        ])
    lines.append("")
    lines.extend(["## Limitations, Reliability, And Boundaries / 限制、可靠性与不能下结论的部分", ""])
    for record in records:
        lines.append(f"- `{record.get('id', '-')}` {record.get('limitations', '-')}; confidence={record.get('confidence', '-')}")
    lines.append("")
    lines.extend(["## Recommendations And Next Analysis", "", "- Prioritize statistical gaps, metric definitions, and needed validation data.", ""])
    lines.extend(["## Appendix: Methods, Data Scope, EvidenceRecord Index", ""])
    for record in records:
        lines.append(f"- `{record.get('id', '-')}` method={record.get('method', '-')}, dataset={record.get('dataset', '-')}")
    lines.append("")
    lines.extend(_statistical_gap_lines(records))
    return "\n".join(lines)


def _evidence_to_insights(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    insights = []
    for record in records:
        insights.append({
            "conclusion": record.get("claim", "Conclusion"),
            "business_meaning": record.get("result_summary", ""),
            "title": record.get("claim", "Conclusion"),
            "summary": record.get("result_summary", ""),
            "evidence_ids": [record.get("id")] if record.get("id") else [],
            "chart_ids": [],
            "statistical_explanation": record.get("method_detail") or record.get("calculation_method") or "",
            "recommendation": "Define the next validation or action from this evidence.",
            "recommendation_confidence": record.get("confidence", "medium"),
            "limitations": record.get("limitations", ""),
            "confidence": record.get("confidence", ""),
            "next_analysis": [],
            "output_type": "finding",
        })
    return insights

def _validated_chart_entries(
    session_id: str,
    evidence_ids: set[str] | None = None,
    *,
    include_exploratory: bool = False,
) -> list[dict[str, Any]]:
    from data_agent.session.history import session_charts_dir

    charts_dir = session_charts_dir(session_id)
    entries: list[dict[str, Any]] = []
    for meta_path in sorted(charts_dir.glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if meta.get("validation_status") not in {"valid", "warning"}:
            continue
        allowed_purposes = {"evidence", "insight"}
        if include_exploratory:
            allowed_purposes.add("exploratory")
        if meta.get("purpose") not in allowed_purposes:
            continue
        chart_evidence_ids = set(meta.get("evidence_ids") or [])
        if evidence_ids and chart_evidence_ids and not chart_evidence_ids.intersection(evidence_ids):
            continue
        html_path = meta_path.with_suffix(".html")
        if not html_path.exists():
            continue
        html = html_path.read_text(encoding="utf-8")
        warning = ""
        if meta.get("validation_status") == "warning":
            warning = "<p class=\"warning\">Chart warning: " + escape("; ".join(meta.get("validation_warnings") or [])) + "</p>"
        purpose = str(meta.get("purpose") or "")
        section_label = "Supplemental chart / 补充图表" if purpose == "exploratory" else "Evidence chart / 证据图表"
        entries.append({
            "chart_id": meta.get("chart_id") or meta_path.stem,
            "title": meta.get("title") or meta_path.stem,
            "html": (
                f"<div class=\"chart-container\"><p class=\"metadata\">{section_label}</p>"
                f"<h3>{escape(str(meta.get('title') or meta_path.stem))}</h3>{warning}{html}</div>"
            ),
            "metadata": meta,
        })
    return entries


def _create_gap_task(session_id: str, goal: str) -> list[int]:
    from data_agent.session.task_manager import task_manager

    task = task_manager.create(
        subject="补齐正式报告所需证据",
        description=f"Formal report for '{goal or session_id}' requires EvidenceRecord before generation.",
        session_id=session_id,
        stage="report",
        node_type="evidence",
        expected_output="EvidenceRecord with claim, method, result_summary, limitations, confidence, and statistical details where available.",
        required_capability="artifact.evidence_record",
    )
    return [task["id"]]


@registry.register(
    name="generate_analysis_brief",
    description="Generate a lightweight evidence-backed analysis brief. format: html, markdown, pdf.",
)
def generate_analysis_brief(title: str = "Analysis Brief", format: str = "html") -> str:
    session_id = _session_id()
    if not session_id:
        return _json_result({"error": "No active session", "error_type": "no_session"})
    state = _analysis_state()
    records = list(getattr(state, "evidence_records", []) or [])
    if not records:
        return _json_result({"error": "No evidence records", "error_type": "insufficient_evidence", "missing": ["evidence_records"]})
    goal = getattr(state, "goal", "") or title
    markdown = _records_to_markdown(title, goal, records, brief=True)
    fmt = "markdown" if format in {"md", "markdown"} else format
    if fmt == "markdown":
        artifact_path = _write_report_artifact(session_id, title, markdown, "md", "report_md", "brief")
        return _json_result({"status": "exported", "type": "brief", "format": "markdown", "artifact_path": artifact_path})
    html = _html_from_markdown(title, markdown)
    html_path = _write_report_artifact(session_id, title, html, "html", "report", "brief")
    if fmt == "pdf":
        result = _export_pdf_from_html(session_id, html_path, title)
        result.update({"type": "brief"})
        return _json_result(result)
    return _json_result({"status": "exported", "type": "brief", "format": "html", "artifact_path": html_path})


@registry.register(
    name="generate_formal_report",
    description="Generate a formal pyramid-structured report from EvidenceRecord, InsightRecord, and validated charts.",
)
def generate_formal_report(title: str = "Formal Analysis Report", format: str = "html") -> str:
    session_id = _session_id()
    if not session_id:
        return _json_result({"error": "No active session", "error_type": "no_session"})
    state = _analysis_state()
    goal = getattr(state, "goal", "") or title
    records = list(getattr(state, "evidence_records", []) or [])
    if not records:
        tasks_created = _create_gap_task(session_id, goal)
        return _json_result({
            "error": "Formal report requires EvidenceRecord before generation",
            "error_type": "insufficient_evidence",
            "missing": ["evidence_records"],
            "tasks_created": tasks_created,
        })
    insights = (list(getattr(state, "expert_insights", []) or []) or list(getattr(state, "insight_records", []) or []) or _evidence_to_insights(records))
    evidence_ids = {record.get("id") for record in records if record.get("id")}
    chart_entries = _validated_chart_entries(session_id, evidence_ids, include_exploratory=True)
    fmt = "markdown" if format in {"md", "markdown"} else format
    markdown = _formal_markdown(
        title,
        goal,
        records,
        insights,
        include_chart_markers=(fmt != "markdown"),
    )
    if fmt == "markdown":
        artifact_path = _write_report_artifact(session_id, title, markdown, "md", "report_md", "formal")
        return _json_result({"status": "exported", "type": "formal", "format": "markdown", "artifact_path": artifact_path})
    html = _html_from_markdown(title, markdown, chart_entries=chart_entries)
    html_path = _write_report_artifact(session_id, title, html, "html", "report", "formal")
    if fmt == "pdf":
        result = _export_pdf_from_html(session_id, html_path, title)
        result.update({"type": "formal"})
        return _json_result(result)
    return _json_result({
        "status": "exported",
        "type": "formal",
        "format": "html",
        "artifact_path": html_path,
        "chart_count": len(chart_entries),
    })


@registry.register(
    name="export_conversation",
    description="Export current session conversation as markdown, html, or pdf.",
)
def export_conversation(title: str = "Conversation Export", format: str = "html", include_charts: bool = False) -> str:
    from data_agent.session.history import load_session

    session_id = _session_id()
    if not session_id:
        return _json_result({"error": "No active session", "error_type": "no_session"})
    data = load_session(session_id) or {}
    messages = data.get("messages", [])
    blocks: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        if role not in {"user", "assistant"}:
            continue
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        speaker = "用户" if role == "user" else "助手"
        blocks.append(f"## {speaker}\n\n{content.strip()}")
    if not blocks:
        return _json_result({"error": "No conversation messages to export", "error_type": "empty_conversation"})
    markdown = f"# {title}\n\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n" + "\n\n".join(blocks)
    fmt = "markdown" if format in {"md", "markdown"} else format
    if fmt == "markdown":
        artifact_path = _write_report_artifact(session_id, title, markdown, "md", "conversation_md", "conversation")
        return _json_result({"status": "exported", "type": "conversation", "format": "markdown", "artifact_path": artifact_path})
    charts_html = ""
    if include_charts:
        chart_entries = _validated_chart_entries(session_id)
        charts_html = "\n".join(entry["html"] for entry in chart_entries)
    html = _html_from_markdown(title, markdown, charts_html=charts_html)
    html_path = _write_report_artifact(session_id, title, html, "html", "conversation_html", "conversation")
    if fmt == "pdf":
        result = _export_pdf_from_html(session_id, html_path, title)
        result.update({"type": "conversation"})
        return _json_result(result)
    return _json_result({"status": "exported", "type": "conversation", "format": "html", "artifact_path": html_path})


@registry.register(
    name="generate_report",
    description="Deprecated wrapper. Use generate_analysis_brief or generate_formal_report.",
)
def generate_report(
    title: str = "Analysis Brief",
    insights: str = "[]",
    charts_html: str = "",
    summary: str = "",
    style: str = "brief",
    data_scope: str = "",
) -> str:
    session_id = _session_id()
    if not session_id:
        return _json_result({"error": "No active session", "error_type": "no_session"})
    markdown = f"# {title}\n\n{summary or 'No summary available.'}\n"
    html = _html_from_markdown(title, markdown)
    artifact_path = _write_report_artifact(session_id, title, html, "html", "report", "brief")
    return _json_result({"status": "exported", "type": "brief", "format": "html", "artifact_path": artifact_path})





