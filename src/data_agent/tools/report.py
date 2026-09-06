"""Conversation export helpers and the single model-visible export tool."""

from __future__ import annotations

import json
import base64
import re
import uuid
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import mistune
from jinja2 import Template

from data_agent.config import get_config
from data_agent.tools.registry import registry


_md_renderer = mistune.create_markdown(plugins=["table", "strikethrough"])


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _session_id() -> str:
    try:
        from data_agent.agent.context import get_current_context

        context = get_current_context()
        if context is not None:
            return context.session_id
    except Exception:
        pass
    try:
        from data_agent.tools.visualization import current_session_id

        return current_session_id()
    except Exception:
        return ""


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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    identity = uuid.uuid4().hex[:8]
    safe_title = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", title).strip("_")[:48] or prefix
    filename = f"{prefix}_{safe_title}_{timestamp}_{identity}.{suffix}"
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


def _html_from_markdown(title: str, markdown: str, charts_html: str = "") -> str:
    if markdown.startswith(f"# {title}\n"):
        markdown = markdown[len(f"# {title}\n"):].lstrip('\n')
    body = _markdown_to_html(markdown)
    plotly_js = ""
    if charts_html:
        # Standalone export must not depend on the local Web process or a CDN.
        vendor_path = Path(__file__).parents[1] / "web/static/js/plotly-3.5.0.min.js"
        if vendor_path.is_file():
            plotly_js = vendor_path.read_text(encoding="utf-8")
        else:
            # A clean checkout intentionally does not track the large vendor
            # bundle. Plotly already ships the matching runtime with Python,
            # so standalone exports remain offline and reproducible.
            from plotly.offline import get_plotlyjs

            plotly_js = get_plotlyjs()
    return Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
{% if plotly_js %}<script>{{ plotly_js }}</script>{% endif %}
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;max-width:1040px;margin:0 auto;padding:40px 22px;color:#243042;line-height:1.72}
h1{border-bottom:3px solid #1f3a5f;padding-bottom:12px;color:#172033}
h2{border-bottom:1px solid #d9e2ef;padding-bottom:8px;margin-top:34px;color:#1f3a5f}
h3{margin-top:22px;color:#284766}
table{border-collapse:collapse;width:100%;max-width:100%;margin:12px 0;display:block;overflow-x:auto}
th,td{border:1px solid #d8dee9;padding:8px 10px;text-align:left;vertical-align:top}
th{background:#eef3f9}
.analysis-block,.chart-container{min-width:0;max-width:100%;margin:18px 0;padding:14px 18px;border:1px solid #d8dee9;border-radius:6px;background:#fff;overflow-wrap:anywhere}
.chart-container{overflow-x:auto}
.chart-container .plotly-graph-div{max-width:100%!important}
.warning{color:#8a5a00;background:#fff8e1;padding:8px 10px;border-radius:4px}
.metadata{color:#667085;font-size:13px}
code{background:#eef2f7;padding:2px 5px;border-radius:4px;overflow-wrap:anywhere;word-break:break-word}
</style>
</head>
<body>
<h1>{{ title }}</h1>
<div class="analysis-block">{{ body }}</div>
{{ charts_html }}
</body>
</html>""").render(title=escape(title), body=body, charts_html=charts_html, plotly_js=plotly_js)


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
        with pdf_path.open("wb") as stream:
            status = pisa.CreatePDF(html_path.read_text(encoding="utf-8"), dest=stream)
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


def _validated_chart_entries(session_id: str, chart_paths: list[str] | None = None) -> list[dict[str, Any]]:
    from data_agent.session.history import session_charts_dir

    charts_dir = session_charts_dir(session_id)
    entries: list[dict[str, Any]] = []
    for meta_path in sorted(charts_dir.glob("*.json")):
        own_path = f"sessions/{session_id}/charts/{meta_path.stem}.html"
        if chart_paths is not None and own_path not in chart_paths:
            continue
        if not meta_path.resolve().is_relative_to(charts_dir.resolve()):
            continue
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if metadata.get("validation_status") not in {"valid", "warning"}:
            continue
        if metadata.get("purpose") not in {"evidence", "insight", "exploratory"}:
            continue
        html_path = meta_path.with_suffix(".html")
        if not html_path.exists() or not html_path.resolve().is_relative_to(charts_dir.resolve()):
            continue
        if metadata.get("figure"):
            import plotly.graph_objects as go
            from data_agent.tools.chart_contract import validate_figure_renderability
            figure = go.Figure(metadata["figure"])
            if validate_figure_renderability(figure):
                continue
            chart_body = figure.to_html(full_html=False, include_plotlyjs=False)
        else:
            # Preserve legacy validated charts without nesting full documents.
            legacy = html_path.read_text(encoding="utf-8")
            body_match = re.search(r"<body[^>]*>(.*?)</body>", legacy, flags=re.S | re.I)
            chart_body = body_match.group(1) if body_match else legacy
            chart_body = re.sub(r'<script\b[^>]*\bsrc=[^>]*>\s*</script>', '', chart_body, flags=re.I)
        title = str(metadata.get("title") or meta_path.stem)
        identities = metadata.get("result_binding") or metadata.get("data_identity") or {}
        provenance = json.dumps({"evidence_ids": metadata.get("evidence_ids", []), "data": identities}, ensure_ascii=False)
        if metadata.get("purpose") == "exploratory":
            level = "探索图：未绑定正式证据，不能作为已验证结论。"
        else:
            from data_agent.agent.analysis_state import load_analysis_state
            from data_agent.agent.workbench_view import build_workbench_view
            state = load_analysis_state(session_id)
            verified = {item["id"] for item in build_workbench_view(state)["verified_conclusions"]}
            evidence_ids = set(metadata.get("evidence_ids") or [])
            level = "证据图：已绑定当前验证结论。" if evidence_ids and evidence_ids <= verified else "计算绑定图：结论尚未通过当前验证。"
        png = meta_path.with_suffix(".png")
        markdown = f"\n\n### {title}\n\n**{level}**\n\n证据与数据版本：`{provenance}`\n\n"
        static_image = metadata.get("static_image") or {}
        if static_image.get("status", "completed") == "completed" and png.exists() and png.resolve().is_relative_to(charts_dir.resolve()):
            encoded = base64.b64encode(png.read_bytes()).decode("ascii")
            markdown += f"![图表](data:image/png;base64,{encoded})\n"
        else:
            markdown += "静态图不可用；请使用 HTML 导出查看图表。\n"
            if static_image.get("exception_type"):
                markdown += f"首次渲染失败类型：{static_image['exception_type']}；详细原因见图表元数据，未自动重试。\n"
        warning = ""
        if metadata.get("validation_status") == "warning":
            warning = (
                '<p class="warning">Chart warning: '
                + escape("; ".join(metadata.get("validation_warnings") or []))
                + "</p>"
            )
        entries.append(
            {
                "chart_id": metadata.get("chart_id") or meta_path.stem,
                "markdown": markdown,
                "html": (
                    '<div class="chart-container"><p class="metadata">Supplemental chart / 补充图表</p>'
                    f"<h3>{escape(str(metadata.get('title') or meta_path.stem))}</h3>"
                    f'<p class="warning">{escape(level)}</p>'
                    f'<p class="metadata">{escape(provenance)}</p>'
                    f"{warning}{chart_body}</div>"
                ),
            }
        )
    return entries


@registry.register(
    name="export_conversation",
    description="Export current session conversation as markdown, html, or pdf.",
)
def export_conversation(
    title: str = "Conversation Export",
    format: str = "html",
    include_charts: bool = True,
) -> str:
    from data_agent.session.history import load_session

    session_id = _session_id()
    if not session_id:
        return _json_result({"error": "No active session", "error_type": "no_session"})
    data = load_session(session_id) or {}
    from data_agent.session.public_messages import public_messages
    return _export_public_messages(session_id, title, format, public_messages(data.get("messages", [])), include_charts)


def export_assistant_reply(session_id: str, content: str = "", format: str = "markdown", *, reply_id: str = "") -> dict:
    from data_agent.session.history import load_session
    from data_agent.session.public_messages import assistant_replies
    if format not in {"html", "md", "markdown"} or (not reply_id and (not isinstance(content, str) or not content.strip())):
        return {"error": "Expected a non-empty persisted reply and html/markdown format"}
    data = load_session(session_id) or {}
    matches = [reply for reply in assistant_replies(data.get("messages", []), session_id)
               if (reply["reply_id"] == reply_id if reply_id else reply["content"] == content.strip())]
    if not matches:
        return {"error": "Reply is not persisted in this session", "error_type": "unbound_reply"}
    # Duplicate prose can refer to different turns; never guess ownership.
    if len(matches) != 1:
        return {"error": "Reply text is ambiguous; use the conversation export", "error_type": "ambiguous_reply"}
    reply = matches[0]
    return json.loads(_export_public_messages(session_id, "Assistant Reply", format,
        [{"role": "assistant", "content": reply["content"]}], True, reply["chart_paths"]))


def _export_public_messages(session_id, title, format, messages, include_charts=True, chart_paths=None):
    blocks: list[str] = []
    for message in messages:
        role = message.get("role", "")
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        speaker = "用户" if role == "user" else "助手"
        blocks.append(f"## {speaker}\n\n{content.strip()}")
    if not blocks:
        return _json_result(
            {"error": "No conversation messages to export", "error_type": "empty_conversation"}
        )

    markdown = (
        f"# {title}\n\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
        + "\n\n".join(blocks)
    )
    output_format = "markdown" if format in {"md", "markdown"} else format
    entries = _validated_chart_entries(session_id, chart_paths) if include_charts else []
    if output_format == "markdown":
        markdown += "".join(entry["markdown"] for entry in entries)
        artifact_path = _write_report_artifact(
            session_id, title, markdown, "md", "conversation_md", "conversation"
        )
        return _json_result(
            {
                "status": "exported",
                "type": "conversation",
                "format": "markdown",
                "artifact_path": artifact_path,
            }
        )

    charts_html = ""
    if include_charts:
        charts_html = "\n".join(entry["html"] for entry in entries)
    html = _html_from_markdown(title, markdown, charts_html=charts_html)
    html_path = _write_report_artifact(
        session_id, title, html, "html", "conversation_html", "conversation"
    )
    if output_format == "pdf":
        result = _export_pdf_from_html(session_id, html_path, title)
        result.update({"type": "conversation"})
        return _json_result(result)
    return _json_result(
        {
            "status": "exported",
            "type": "conversation",
            "format": "html",
            "artifact_path": html_path,
        }
    )
