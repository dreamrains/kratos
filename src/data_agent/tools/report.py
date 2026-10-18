"""Conversation export helpers and the single model-visible export tool."""

from __future__ import annotations

import json
import hashlib
import base64
import re
import uuid
from datetime import datetime
from html import escape
from pathlib import Path
from functools import lru_cache
from urllib.parse import quote
from typing import Any

import mistune
from jinja2 import Template

from data_agent.config import get_config
from data_agent.tools.registry import registry


class _ExportHTMLRenderer(mistune.HTMLRenderer):
    def __init__(self, *, chart_entries=None, **kwargs):
        super().__init__(**kwargs)
        self.chart_entries = {"/api/files/" + quote(e["path"], safe="/"): e
                              for e in (chart_entries or []) if e.get("path")}
        self.used_chart_paths = set()

    def link(self, text, url, title=None):
        entry = self.chart_entries.get(url)
        if entry is not None:
            self.used_chart_paths.add(entry["path"])
            return entry["html"].replace('<p class="metadata">Supplemental chart / 补充图表</p>', '', 1)
        return super().link(text, url, title)

    def text(self, text: str) -> str:
        # Markdown entities represent text, not an additional HTML parsing pass.
        # Raw HTML handlers still use escape=True; URLs retain safe_url checks.
        return mistune.util.safe_entity(text)


def _export_math(md):
    from mistune.plugins.math import math
    math(md)

    def parse_display(inline, match, state):
        state.append_token({"type": "display_math", "raw": match.group("display_tex")})
        return match.end()

    def render_math(renderer, text, display=False):
        return ('<span class="export-math" data-display="' + str(display).lower()
                + '" data-tex="' + escape(text, quote=True) + '">'
                + escape(text) + '</span>')

    md.inline.register("display_math", r"\$\$(?P<display_tex>[\s\S]+?)\$\$", parse_display, before="inline_math")
    md.renderer.register("display_math", lambda renderer, text: render_math(renderer, text, True))
    md.renderer.register("block_math", lambda renderer, text: render_math(renderer, text, True))
    md.renderer.register("inline_math", render_math)


@lru_cache(maxsize=1)
def _standalone_math_assets():
    # Reuse the installed app's pinned KaTeX assets, including fonts, offline.
    vendor = Path(__file__).parents[1] / "web/static/vendor/katex"
    js = (vendor / "katex-0.16.11.min.js").read_text(encoding="utf-8")
    css = (vendor / "katex-0.16.11.min.css").read_text(encoding="utf-8")

    def font(match):
        name = match.group(1)
        path = vendor / "fonts" / name
        if path.suffix != ".woff2" or not path.is_file():
            return "url(data:,)"
        return "url(data:font/woff2;base64," + base64.b64encode(path.read_bytes()).decode("ascii") + ")"

    css = re.sub(r"url\(fonts/([^)]+)\)", font, css)
    return js.replace("</script", "<\\/script"), css


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
    from data_agent.utils.atomic_files import write_text_atomic
    write_text_atomic(path, content)
    artifact_path = f"{artifact_prefix}/{filename}"
    register_artifact(session_id, artifact_path, artifact_type, title)
    return artifact_path


def _markdown_to_html(markdown: str, *, renderer=None) -> str:
    if not markdown:
        return ""
    renderer = renderer or _ExportHTMLRenderer(escape=True, allow_harmful_protocols=False)
    return mistune.create_markdown(renderer=renderer, plugins=["table", "strikethrough", _export_math])(markdown)


def _html_from_markdown(title: str, markdown: str, charts_html: str = "", *, chart_entries=None) -> str:
    if markdown.startswith(f"# {title}\n"):
        markdown = markdown[len(f"# {title}\n"):].lstrip('\n')
    renderer = _ExportHTMLRenderer(escape=True, allow_harmful_protocols=False, chart_entries=chart_entries)
    body = _markdown_to_html(markdown, renderer=renderer)
    if chart_entries is not None:
        charts_html = "\n".join(e["html"] for e in chart_entries if e.get("path") not in renderer.used_chart_paths)
    math_js, math_css = _standalone_math_assets() if 'class="export-math"' in body else ("", "")
    plotly_js = ""
    if charts_html or renderer.used_chart_paths:
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
<style>{{ math_css }}
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
{% if math_js %}<script>{{ math_js }}</script>
<script>document.querySelectorAll('.export-math').forEach(element => {
  katex.render(element.dataset.tex, element, {displayMode: element.dataset.display === 'true', throwOnError: false, trust: false});
});</script>{% endif %}
</body>
</html>""").render(title=escape(title), body=body, charts_html=charts_html, plotly_js=plotly_js, math_js=math_js, math_css=math_css)


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
        from io import BytesIO
        stream = BytesIO()
        html_source = html_path.read_text(encoding="utf-8")
        # The existing converter ships this CJK CID font; browser system fonts
        # otherwise silently render Chinese as missing-glyph boxes in PDF.
        html_source = html_source.replace("</head>", "<style>body, body * {font-family: STSong-Light;}</style></head>", 1)
        status = pisa.CreatePDF(html_source, dest=stream)
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

    from data_agent.utils.atomic_files import write_bytes_atomic
    if not stream.getvalue().startswith(b"%PDF-"):
        return {"status":"degraded","format":"pdf","reason":"PDF converter returned no PDF bytes","fallback_artifact_path":html_artifact_path}
    write_bytes_atomic(pdf_path, stream.getvalue())
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
            chart_body = figure.to_html(full_html=False, include_plotlyjs=False, div_id="conversation-chart-" + hashlib.sha256(own_path.encode()).hexdigest()[:20])
        else:
            # Preserve legacy validated charts without nesting full documents.
            legacy = html_path.read_text(encoding="utf-8")
            body_match = re.search(r"<body[^>]*>(.*?)</body>", legacy, flags=re.S | re.I)
            chart_body = body_match.group(1) if body_match else legacy
            chart_body = re.sub(r'<script\b[^>]*\bsrc=[^>]*>\s*</script>', '', chart_body, flags=re.I)
        title = str(metadata.get("title") or meta_path.stem)
        identities = metadata.get("result_binding") or metadata.get("data_identity") or {}
        # Export a readable projection; the original chart metadata remains
        # the inspectable provenance record, never embedded as internal JSON.
        provenance = "；".join(
            label + "：" + str(identities[key])
            for key, label in (("dataset", "数据来源"), ("version_id", "数据版本"))
            if isinstance(identities, dict) and identities.get(key)
        ) or "数据版本未声明"
        provenance += "；绑定证据数：" + str(len(metadata.get("evidence_ids") or []))
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
        markdown = f"\n\n### {title}\n\n**{level}**\n\n证据与数据版本：{provenance}\n\n"
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
                "path": own_path,
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
    description="Export the persisted public conversation snapshot as markdown, html or pdf. A standalone request uses the existing operation delivery with exact title/format/include_charts arguments. PDF conversion failure discloses an HTML fallback as partial, never successful PDF. Unknown formats are rejected before writing.",
    output_contract={"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"],"effect":"conversation_export_with_verified_snapshot"},
    schema_overrides={"reply_target":{"enum":["conversation","current_answer"], "description":"current_answer queues an exact current AcceptedAnswer export after reliable persistence; never exports earlier messages as the current report"}},
)
def export_conversation(
    title: str = "Conversation Export",
    format: str = "html",
    include_charts: bool = True,
    reply_target: str = "conversation",
) -> str:
    session_id = _session_id()
    if not session_id:
        return _json_result({"error": "No active session", "error_type": "no_session"})
    try:
        normalized = _conversation_format(format)
        if reply_target not in {"conversation", "current_answer"}:
            raise ValueError("Unknown reply target")
        if reply_target == "current_answer":
            if normalized not in {"markdown", "html"}:
                raise ValueError("Current accepted reply export supports markdown/html")
            return _json_result({"status":"deferred", "reply_target":"current_answer",
                "reason":"Host exports the exact current reply only after its accepted answer is persisted."})
        if not isinstance(title, str) or type(include_charts) is not bool:
            raise ValueError("Expected a string title and boolean include_charts")
        messages, source = _conversation_source(session_id, include_charts)
        from data_agent.utils.atomic_files import rollback_atomic_writes
        with rollback_atomic_writes():
            result = json.loads(_render_public_messages(session_id, title, normalized, messages, include_charts))
            if result.get("error"):
                return _json_result(result)
            _, current = _conversation_source(session_id, include_charts, source)
            if current != source:
                raise ValueError("Conversation source changed during export")
            result.update(source_binding=source, parameters={"title":title,"format":normalized,"include_charts":include_charts})
            result["outputs"] = _conversation_outputs(session_id, result)
            return _json_result(result)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return _json_result({"error": str(exc), "error_type": "unsupported_export_format" if isinstance(exc, _UnsupportedConversationFormat) else "conversation_export_failed"})


class _UnsupportedConversationFormat(ValueError):
    pass


def _conversation_format(value):
    if not isinstance(value, str) or value not in {"md", "markdown", "html", "pdf"}:
        raise _UnsupportedConversationFormat("Supported conversation formats: markdown/md, html, pdf")
    return "markdown" if value == "md" else value


def _conversation_source(session_id, include_charts, bound=None):
    """Freeze an existing persisted prefix; later tool/answer appends are allowed."""
    from data_agent.session.history import load_session, load_canonical_history, _history_sha256, read_canonical_transcript
    from data_agent.session.public_messages import public_messages
    from data_agent.agent.publication.contracts import digest, encode
    from data_agent.agent.publication.runtime import read_answer
    history = load_canonical_history(session_id)
    stored = load_session(session_id) or {}
    count = bound["message_count"] if bound else len(history.messages)
    if type(count) is not int or count < 0 or count > len(history.messages):
        raise ValueError("Conversation source prefix is unavailable")
    prefix = list(history.messages[:count])
    if bound and (bound["session_id"] != session_id or history.revision < bound["history_revision"]
                  or _history_sha256(prefix) != bound["history_sha256"]):
        raise ValueError("Persisted conversation source changed")
    archives = []
    def verify_archives(messages, seen):
        for message in messages:
            ref = message.get("canonical_transcript")
            if ref:
                identity = (ref["filename"], ref["sha256"])
                if identity in seen or len(seen) >= 32:
                    raise ValueError("Canonical transcript cycle or budget exceeded")
                seen.add(identity)
                raw, nested = read_canonical_transcript(session_id, ref)
                archives.append({"filename":ref["filename"],"sha256":ref["sha256"]})
                verify_archives(nested, seen)
    verify_archives(prefix, set())
    current_schema = stored.get("publication_schema", "")
    messages = public_messages(prefix if current_schema == "answer_bindings.v2" else stored.get("messages", []), session_id)
    answers = []
    for message in messages:
        if message.get("answer_ref"):
            accepted = read_answer(session_id, message["answer_ref"])
            if accepted["body"] != message.get("content"):
                raise ValueError("Accepted answer body mismatch")
            answers.append(message["answer_ref"])
    charts = []
    entries = _validated_chart_entries(session_id) if include_charts else []
    if include_charts:
        from data_agent.session.history import session_charts_dir
        root = session_charts_dir(session_id).resolve()
        for path in sorted(root.iterdir()):
            if path.suffix in {".json", ".html", ".png"} and path.is_file():
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("Chart source exceeds current session")
                charts.append({"name":path.name,"sha256":"sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()})
    source = {"session_id":session_id,"history_revision":bound["history_revision"] if bound else history.revision,
              "history_sha256":_history_sha256(prefix),"message_count":count,"publication_schema":current_schema,
              "public_messages_sha256":digest(encode(messages)),"answer_refs":answers,"archives":archives,
              "charts":charts,"chart_entries_sha256":digest(encode(entries))}
    if bound and source != bound:
        raise ValueError("Conversation answer/chart source changed")
    return messages, source


def _conversation_reports_root(session_id):
    from data_agent.session.history import session_reports_dir
    root = get_config().sessions_resolved.resolve()
    session = (root / session_id).resolve()
    reports = session_reports_dir(session_id).resolve()
    if not session.is_relative_to(root) or not reports.is_relative_to(session) or reports != session / "reports":
        raise ValueError("Conversation output exceeds current session reports")
    return reports


def _conversation_outputs(session_id, result):
    from data_agent.session.history import list_artifacts
    from data_agent.agent.publication.contracts import digest
    root = _conversation_reports_root(session_id)
    paths = [result[k] for k in ("artifact_path", "support_artifact_path", "fallback_artifact_path") if result.get(k)]
    if len(set(paths)) != len(paths) or not paths:
        raise ValueError("Export output identity is unavailable")
    outputs = []
    for name in paths:
        prefix = f"sessions/{session_id}/reports/"
        if not isinstance(name, str) or not name.startswith(prefix) or Path(name[len(prefix):]).name != name[len(prefix):]:
            raise ValueError("Export output is outside current reports")
        path = root / name[len(prefix):]
        if path.is_symlink() or path.resolve().parent != root or not path.is_file():
            raise ValueError("Export output is not an owned file")
        current = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        records = [r for r in list_artifacts(session_id) if r["path"] == name and r["sha256"] == current]
        expected_type={".md":"conversation_md",".html":"conversation_html",".pdf":"report_pdf"}.get(path.suffix)
        if len(records) != 1 or not expected_type or records[0]["type"]!=expected_type:
            raise ValueError("Export file does not match registered artifact")
        outputs.append({"path":name,"sha256":current,"type":records[0]["type"],"format":{".md":"markdown",".html":"html",".pdf":"pdf"}.get(path.suffix)})
    return outputs


def export_assistant_reply(session_id: str, content: str = "", format: str = "markdown", *, reply_id: str = "", title: str = "Assistant Reply", include_charts: bool = True, _in_transaction: bool = False) -> dict:
    from data_agent.session.history import load_session
    from data_agent.session.public_messages import assistant_replies
    if format not in {"html", "md", "markdown"} or (not reply_id and (not isinstance(content, str) or not content.strip())):
        return {"error": "Expected a non-empty persisted reply and html/markdown format"}
    data = load_session(session_id) or {}
    matches = [reply for reply in assistant_replies(data.get("messages", []), session_id)
               if (reply["reply_id"] == reply_id if reply_id else (reply["content"] == content or (not reply.get("answer_ref") and reply["content"] == content.strip())))]
    if not matches:
        return {"error": "Reply is not persisted in this session", "error_type": "unbound_reply"}
    # Duplicate prose can refer to different turns; never guess ownership.
    if len(matches) != 1:
        return {"error": "Reply text is ambiguous; use the conversation export", "error_type": "ambiguous_reply"}
    reply = matches[0]
    message = {"role": "assistant", "content": reply["content"], "answer_ref": reply.get("answer_ref")}
    return json.loads(_export_public_messages(
        session_id, title, format, [message], include_charts, reply["chart_paths"], _in_transaction=_in_transaction
    ))


def _publication_appendix(session_id, *, answer_ref=None):
    """Use only the same persisted accepted answer; historical prose has no grant."""
    if not answer_ref:
        return ""
    from data_agent.agent.publication.runtime import read_answer
    answer = read_answer(session_id, answer_ref)
    proofs = {p["receipt_id"]: p for c in answer["source_snapshot"]["claims"] for p in c["basis_refs"]}
    proofs.update({e["receipt_id"]:{"tool_name":e["action"],"result_sha256":e["result_sha256"]} for e in answer["source_snapshot"].get("effects",[])})
    sources = "\n".join("- " + rid + " / " + p["tool_name"] + " / " + p["result_sha256"] for rid, p in proofs.items())
    outcomes = "\n".join("- " + o["requirement_id"] + "：" + o["status"] + ("；" + o["reason"] if o["reason"] else "") for o in answer["requirement_outcomes"])
    return "### 接受答案来源\n\n" + answer["answer_id"] + "\n\n" + sources + "\n\n### 原需求交付\n\n" + outcomes


def _export_public_messages(session_id, title, format, messages, include_charts=True, chart_paths=None, *, _in_transaction=False):
    from data_agent.utils.atomic_files import rollback_atomic_writes,_pending_writes
    if _in_transaction:
        if _pending_writes.get() is None:raise RuntimeError("Reply export requires its existing host transaction")
        return _render_public_messages(session_id, title, _conversation_format(format), messages, include_charts, chart_paths)
    with rollback_atomic_writes():
        return _render_public_messages(session_id, title, _conversation_format(format), messages, include_charts, chart_paths)


def _render_public_messages(session_id, title, format, messages, include_charts=True, chart_paths=None):
    _conversation_reports_root(session_id)
    blocks: list[str] = []
    assistant_count = sum(1 for message in messages if message.get("role") == "assistant")
    for message in messages:
        role = message.get("role", "")
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        speaker = "用户" if role == "user" else "助手"
        block = f"## {speaker}\n\n{content.strip()}"
        if role == "assistant":
            reference = message.get("answer_ref")
            if reference:
                from data_agent.agent.publication.runtime import read_answer
                try:
                    accepted = read_answer(session_id, reference)
                    if accepted["body"] != content:
                        raise ValueError("Accepted answer body mismatch")
                    block = f"## {speaker}\n\n{accepted['body']}"
                    appendix = _publication_appendix(session_id, answer_ref=reference)
                except (ValueError, OSError, KeyError, TypeError):
                    return _json_result({"error": "Accepted answer source cannot be verified", "error_type": "unbound_reply"})
            else:
                appendix = ""
            if appendix:
                block += "\n\n" + appendix
        blocks.append(block)
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
    html = _html_from_markdown(title, markdown, charts_html=charts_html, chart_entries=entries)
    html_path = _write_report_artifact(
        session_id, title, html, "html", "conversation_html", "conversation"
    )
    if output_format == "pdf":
        result = _export_pdf_from_html(session_id, html_path, title)
        result.update({"type": "conversation"})
        if result.get("status") == "exported": result["support_artifact_path"] = html_path
        return _json_result(result)
    return _json_result(
        {
            "status": "exported",
            "type": "conversation",
            "format": "html",
            "artifact_path": html_path,
        }
    )
