"""L5: 可视化工具。"""

from __future__ import annotations
import re
import numpy as np

import json
import uuid
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from data_agent.config import get_config
from data_agent.session.workspace import workspace
from data_agent.tools._utils import get_df
from data_agent.tools.chart_contract import (
    chart_parameter_error,
    is_chart_count_aggregation,
    validate_chart_request,
    validate_figure_renderability,
)
from data_agent.tools.registry import registry, ToolResult


def _save_chart(fig: go.Figure, title: str = "chart", metadata: dict | None = None):
    """Publish chart files and the existing manifest together; retain the first PNG failure."""
    from data_agent.session.history import session_charts_dir, register_artifact, _artifact_manifest_lock
    from data_agent.utils.atomic_files import rollback_atomic_writes, write_text_atomic, write_bytes_atomic, unlink_with_rollback
    from data_agent.tools._utils import sanitize_filename
    from data_agent.tools.registry import ToolResult, ArtifactRef
    import hashlib

    if metadata is not None:
        exploratory = metadata.get("purpose") == "exploratory"
        metadata["publication_level"] = "exploratory" if exploratory else "result_bound"
        fig.add_annotation(text="探索图：未绑定正式证据" if exploratory else "计算绑定图：结论验证状态见工作台",
                           xref="paper", yref="paper", x=0, y=1.12, showarrow=False,
                           font={"size": 11, "color": "#92400e"})
        # Fixed pixel spacing above the plotting area survives responsive height
        # changes; paper fractions previously collided with the chart title.
        header_notes=[a for a in fig.layout.annotations if a.xref=="paper" and a.yref=="paper" and a.y is not None and a.y>=1]
        offset=10
        for note in reversed(header_notes):
            lines=[]
            for line in re.split(r"<br\s*/?>",note.text or ""):
                tokens=re.findall(r"&(?:#\d+|#x[0-9a-fA-F]+|\w+);|<[^>]*>|.",line)
                wrapped=[];width=0
                for token in tokens:
                    if width>=54 and not token.startswith('<'):wrapped.append('<br>');width=0
                    wrapped.append(token)
                    if not token.startswith('<'):width+=1
                lines.append(''.join(wrapped))
            text='<br>'.join(lines)
            note.update(text=text,x=0,xanchor='left',y=1,yanchor='bottom',yshift=offset)
            offset+=15*(text.count('<br>')+1)+10
        fig.update_layout(margin={'t':max(fig.layout.margin.t or 100,offset+45)},
                          title={'y':1,'yanchor':'top','pad':{'t':10}})
    session_id = current_session_id()
    cfg = get_config()
    root = (cfg.sessions_resolved / session_id).resolve() if session_id else cfg.project_resolved.resolve()
    if session_id and not root.is_relative_to(cfg.sessions_resolved.resolve()):
        raise ValueError("Chart session path escapes configured sessions directory")
    output_dir = (root / "charts").resolve()
    if output_dir.parent != root:
        raise ValueError("Chart directory escapes its owner")
    chart_id = f"{sanitize_filename(title.replace(' ', '_'))}_{uuid.uuid4().hex[:6]}"
    path = output_dir / f"{chart_id}.html"
    meta_path = path.with_suffix(".json")
    png_path = path.with_suffix(".png")
    with _artifact_manifest_lock, rollback_atomic_writes():
        output_dir.mkdir(parents=True, exist_ok=True)
        if any(p.exists() for p in (path, meta_path, png_path)):
            raise FileExistsError("Chart destination already exists; no existing output was replaced")
        write_text_atomic(path, fig.to_html(include_plotlyjs='/static/js/plotly-3.5.0.min.js'))
        meta = dict(metadata or {})
        meta.update(chart_id=chart_id, filename=path.name, figure=json.loads(fig.to_json()))
        static_image = None
        if session_id:
            started = time.monotonic()
            static_image = {"status": "failed", "attempts": 1}
            try:
                static_fig = go.Figure(meta["figure"])
                static_fig.update_layout(width=800, height=450)
                png_bytes = static_fig.to_image(format="png", scale=1.5)
                if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("Renderer did not return a PNG image")
                write_bytes_atomic(png_path, png_bytes)
                static_image.update(status="completed", filename=png_path.name, bytes=len(png_bytes))
            except Exception as exc:
                if png_path.exists():
                    unlink_with_rollback(png_path)
                static_image.update(exception_type=type(exc).__name__, message=str(exc)[:2000])
            static_image["elapsed_seconds"] = round(time.monotonic() - started, 6)
            meta["static_image"] = static_image
        if metadata is not None or session_id:
            write_text_atomic(meta_path, json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False))
        artifact_path = f"sessions/{session_id}/charts/{chart_id}.html" if session_id else f"charts/{chart_id}.html"
        if session_id:
            register_artifact(session_id, artifact_path, "chart", title)
        warning = "\nWarning: 静态图不可用，首次失败已记录；HTML 可用。" if static_image and static_image["status"] == "failed" else ""
        summary = f"Chart saved: {artifact_path}{warning}"
        if session_id and ("correlation_audit" in meta or meta.get("completion_gap") or meta.get("aggregation_audit",{}).get("method")=="count"):
            gap = meta.get("completion_gap")
            if gap:
                summary += "\n范围：" + gap["reason"]
            return ToolResult(summary=summary, data={"artifact_path": artifact_path,
                "chart_metadata_ref": f"charts/{meta_path.name}",
                "chart_metadata_sha256": "sha256:" + hashlib.sha256(meta_path.read_bytes()).hexdigest(),
                "completion_gap": gap, **{key: meta[key] for key in ("correlation_audit", "observation_audit", "aggregation_audit") if key in meta}},
                artifacts=[ArtifactRef(path=artifact_path, type="chart", description=title)])
        return summary


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
        value.isoformat() if isinstance(value, pd.Timestamp) else str(value) if isinstance(value, pd.Interval) else value
        for value in series.tolist()
    ]


def _combined_label_tick_text(value: object, *, max_chars: int = 30) -> tuple[str, bool]:
    """Return a compact display label without changing the axis identity.

    ``label_columns`` stores a reversible JSON array on the plotting copy. A
    full array is useful in hover/export metadata but quickly becomes
    unreadable as an x-axis tick. Tick text is presentation only: Plotly keeps
    the original value in ``tickvals`` and every trace's x data.
    """
    raw = str(value)
    display = raw
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, list):
            display = " · ".join("∅" if item is None else str(item) for item in decoded)
    except (json.JSONDecodeError, TypeError):
        pass
    display = " ".join(display.split())
    if len(display) <= max_chars:
        return display, False
    head = max_chars // 2
    tail = max_chars - head - 1
    return f"{display[:head]}…{display[-tail:]}", True


def _apply_combined_label_axis(fig: go.Figure, values: pd.Series, metadata: dict | None) -> None:
    """Make a combined categorical axis legible while retaining full labels."""
    tickvals: list[object] = []
    seen: set[str] = set()
    for value in _plotly_axis_values(values):
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            tickvals.append(value)
    category_count = len(tickvals)
    if category_count >= 12:
        max_chars, tickangle, bottom_margin, tick_size = 18, -90, 175, 10
    elif category_count >= 8:
        max_chars, tickangle, bottom_margin, tick_size = 24, -55, 125, 11
    else:
        max_chars, tickangle, bottom_margin, tick_size = 30, -35, 110, 12
    rendered = [_combined_label_tick_text(value, max_chars=max_chars) for value in tickvals]
    ticktext = [item[0] for item in rendered]
    truncated_count = sum(1 for _, truncated in rendered if truncated)
    fig.update_xaxes(
        type="category",
        tickmode="array",
        tickvals=tickvals,
        ticktext=ticktext,
        tickangle=tickangle if any(len(text) > 12 for text in ticktext) else 0,
        tickfont={"size": tick_size},
        automargin=True,
    )
    fig.update_layout(margin={"b": bottom_margin if tickvals else 80})
    if metadata is not None:
        metadata["axis_label_presentation"] = {
            "source": "label_columns",
            "identity_preserved_in_tickvals": True,
            "max_tick_characters": max_chars,
            "category_count": category_count,
            "truncated_count": truncated_count,
        }


def _parsed_evidence_ids(evidence_ids: str) -> list[str]:
    return [item.strip() for item in (evidence_ids or "").split(",") if item.strip()]


def _unresolved_evidence_ids(evidence_ids: list[str]) -> list[str]:
    """Return evidence ids that are not present in the active session state.

    A chart is an artifact, not evidence by itself.  Allowing an LLM to attach
    arbitrary strings here made a chart look source-bound even when no actual
    evidence record existed.  Keep this lookup deliberately small and local:
    the evidence record remains the authority for the claim and calculation.
    """
    try:
        from data_agent.agent.context import get_current_context

        context = get_current_context()
        state = getattr(context, "analysis_state", None) if context is not None else None
        records = getattr(state, "evidence_records", None) if state is not None else None
        known_ids = {
            str(record.get("id"))
            for record in (records or [])
            if isinstance(record, dict) and record.get("id")
        }
    except Exception:
        known_ids = set()
    return [evidence_id for evidence_id in evidence_ids if evidence_id not in known_ids]


def _first_present(row: dict, keys: tuple[str, ...]):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _unbound_chart_evidence(evidence_ids, dataset, result_binding):
    """Require the chart data version to appear in each evidence's receipts."""
    from data_agent.agent.context import get_current_context
    state = get_current_context().analysis_state
    records = {r.get("id"): r for r in state.evidence_records}
    receipts = {r.get("id"): r for r in state.tool_receipts}
    identity = workspace.get_data_identity(dataset)
    unbound = []
    for eid in evidence_ids:
        matched = False
        for binding in records[eid].get("result_bindings", []):
            receipt = receipts.get(binding.get("receipt_id"), {})
            expected_hash = receipt.get("structured_result_sha256") or receipt.get("result_sha256")
            if not expected_hash or binding.get("result_sha256") != expected_hash:
                continue
            if not identity or receipt.get("data_identities", {}).get(dataset) != identity:
                continue
            if binding.get("data_identities") != receipt.get("data_identities"):
                continue
            if result_binding and receipt.get("id") != result_binding.get("receipt_id"):
                continue
            matched = True
            break
        if not matched:
            unbound.append(eid)
    return unbound


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


def _normalize_funnel_rows(rows: list[dict], step_col: str = "", count_col: str = "") -> tuple[list[dict], str | None]:
    normalized: list[dict] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            return [], "funnel data_json must be a list of objects"
        step = row.get(step_col) if step_col else _first_present(row, ("step", "stage", "label", "name", "步骤", "阶段", "环节", "名称"))
        count = row.get(count_col) if count_col else _first_present(row, ("count", "value", "数值", "数量", "次数", "count_value"))
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
        if not np.isfinite(numeric_count) or numeric_count < 0 or not float(numeric_count).is_integer():
            return [], f"funnel row {idx + 1} count/value must be a finite nonnegative integer"
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


def _title_claims_series_comparison(title: str) -> bool:
    title_l = (title or "").lower()
    has_observed = any(term in title_l for term in ("actual", "observed", "实际", "观测"))
    has_fitted = any(term in title_l for term in ("fit", "fitted", "predicted", "拟合", "预测"))
    return has_observed and has_fitted


def _chart_observation_audit(source, columns, plotted_rows):
    """Describe the actual selected numeric fields without changing their chart algorithm."""
    columns = list(dict.fromkeys(columns))
    if not columns:
        return None
    invalid_rows = pd.Series(False, index=source.index)
    missing_rows = pd.Series(False, index=source.index)
    entries = {}
    for name in columns:
        original = source[name]
        values = pd.to_numeric(original, errors="coerce")
        missing = original.isna()
        conversion_failed = original.notna() & values.isna()
        nonfinite = values.notna() & ~np.isfinite(values)
        invalid_rows |= conversion_failed | nonfinite
        missing_rows |= missing
        entries[name] = {"source_rows": int(len(source)), "missing_count": int(missing.sum()),
            "non_numeric_count": int(conversion_failed.sum()), "nonfinite_count": int(nonfinite.sum()),
            "finite_count": int((values.notna() & np.isfinite(values)).sum())}
    return {"source_rows": int(len(source)), "plotted_rows": int(plotted_rows), "columns": entries,
            "joint_unusable_numeric_rows": int(invalid_rows.sum()),
            "joint_original_missing_rows": int(missing_rows.sum()),
            "scope": "original_selected_numeric_fields", "missing_handling": "original_chart_algorithm"}


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


def _aggregate_chart_groups(df, group_cols, y_cols, aggregation, metadata):
    grouped = df.groupby(group_cols, sort=False, dropna=False)
    measures = grouped[y_cols]
    values = measures.sum(min_count=1) if aggregation == "sum" else measures.agg(aggregation)
    counts = measures.count()
    sizes = grouped.size()
    plot_df = values.reset_index()
    if metadata is not None:
        def scalar(value):
            if pd.isna(value):
                return None
            if isinstance(value, (pd.Timestamp, pd.Timedelta)):
                return value.isoformat()
            return value.item() if isinstance(value, np.generic) else value
        groups = []
        for position in range(len(plot_df)):
            groups.append({
                "group": {col: scalar(plot_df[col].iloc[position]) for col in group_cols},
                "row_count": int(sizes.iloc[position]),
                "valid_counts": {col: int(counts[col].iloc[position]) for col in y_cols},
                "values": {col: scalar(plot_df[col].iloc[position]) for col in y_cols},
            })
        unknown = sum(any(g["values"][col] is None for col in y_cols) for g in groups)
        metadata["aggregation_audit"] = {
            "method": aggregation, "group_columns": group_cols,
            "source_row_count": int(len(df)), "groups": groups,
            "unknown_group_count": unknown,
            "count_semantics": "original_column_nonmissing_entries; not distinct users" if aggregation == "count" else None,
        }
        if unknown:
            metadata.setdefault("validation_warnings", []).append(
                f"{unknown} aggregate group(s) have unknown values; unknown is not zero. Effective observation counts are retained per group."
            )
            metadata["validation_status"] = "warning"
    return plot_df


def _aggregation_hover_text(metadata, indices, column):
    audit = (metadata or {}).get("aggregation_audit")
    if not audit:
        return None
    return [f"有效观测数={audit['groups'][int(i)]['valid_counts'][column]}；聚合={audit['method']}"
            for i in indices]


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
        plot_df = df.copy()
        plot_df[x_col] = parsed
        group_cols = [x_col] + ([color_col] if color_col else [])
        if parsed.notna().any() and (aggregation or plot_df.duplicated(subset=group_cols).any()):
            plot_df = _aggregate_chart_groups(plot_df, group_cols, y_cols, aggregation, metadata)
            _refresh_chart_metadata(
                metadata,
                plot_df,
                x_col,
                y_cols,
                f"{aggregation}_by_timestamp",
            )
            if metadata is not None:
                metadata.setdefault("transformations", []).append(
                    f"aggregation:{aggregation}"
                )
        return plot_df.sort_values(x_col, kind="stable")

    if chart_type == "line" and aggregation:
        group_cols = [x_col] + ([color_col] if color_col else [])
        plot_df = _aggregate_chart_groups(df, group_cols, y_cols, aggregation, metadata)
        _refresh_chart_metadata(metadata, plot_df, x_col, y_cols, f"{aggregation}_by_x")
        numeric_axis = pd.api.types.is_numeric_dtype(df[x_col])
        if metadata is not None:
            metadata.setdefault("transformations", []).append(f"aggregation:{aggregation}")
            metadata["axis_order"] = "numeric_ascending" if numeric_axis else "category_first_appearance"
        return plot_df.sort_values(x_col, kind="stable") if numeric_axis else plot_df

    if chart_type in {"bar", "stacked_bar"}:
        group_cols = [x_col] + ([color_col] if color_col else [])
        if not aggregation and not df.duplicated(subset=group_cols).any():
            return df
        plot_df = _aggregate_chart_groups(df, group_cols, y_cols, aggregation, metadata)
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

    if chart_type == "pie" and aggregation:
        plot_df = _aggregate_chart_groups(df, [x_col], y_cols, aggregation, metadata)
        _refresh_chart_metadata(metadata, plot_df, x_col, y_cols, f"{aggregation}_by_x")
        if metadata is not None:
            metadata.setdefault("transformations", []).append(f"aggregation:{aggregation}")
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
    aggregation: str = "",
    scale_mode: str = "",
) -> tuple[dict | None, str | None]:
    warnings: list[str] = []
    y_cols = [c.strip() for c in y_col.split(",") if c.strip()]
    parameter_error = chart_parameter_error(chart_type, x_col, y_cols, color_col, aggregation)
    if parameter_error:
        return None, _chart_error(parameter_error[0], [], error_code=parameter_error[1])

    if x_col and x_col not in df.columns:
        return None, _chart_error(f"x_col '{x_col}' not found", [f"missing x_col: {x_col}"])
    for col in y_cols:
        if col not in df.columns:
            return None, _chart_error(f"y_col '{col}' not found", [f"missing y_col: {col}"])
        if not is_chart_count_aggregation(df, chart_type, x_col, aggregation):
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().sum() == 0:
                return None, _chart_error(f"y_col '{col}' is empty or non-numeric", [f"invalid y_col: {col}"])

    if color_col and color_col not in df.columns:
        return None, _chart_error(f"color_col '{color_col}' not found", [f"missing color_col: {color_col}"])

    declared_series = len(y_cols)
    if color_col and color_col in df.columns:
        declared_series *= int(df[color_col].nunique(dropna=True))
    if _title_claims_series_comparison(title) and declared_series < 2:
        return None, _chart_error(
            "comparison chart requires at least two plotted series",
            ["title claims a comparison but only one series was provided"],
            error_code="comparison_requires_multiple_series",
            recovery_options=[{
                "chart_type": "line",
                "description": "Provide separate observed and fitted columns in y_col, separated by a comma.",
            }],
        )

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
        if chart_type == "bar" and scale_mode == "normalize" and _bar_chart_needs_normalization(df, y_cols):
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
        "参数说明：data 为数据集名称；line/bar/scatter及heatmap支持多指标，histogram/box/pie/stacked_bar/funnel显式仅单指标。color_col用于支持分组的图种，heatmap不支持。"
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
        "data": {"description": "数据集名称；显式来源不存在或不可读时拒绝；与result_ref并用时仅断言其唯一同源身份，不得与data_json并用。省略时在当前可见数据中优先main，否则选记录数最多的一份。"},
        "title": {"description": "图表标题"},
        "x_col": {"description": "X轴列名；数值折线x不得含正/负Infinity，写图前拒绝；普通缺失沿原规则处理并披露。box显式x须配单列y；仅y保留无分组箱图，均省略保留原默认。line/bar显式聚合或颜色分组须提供x_col或label_columns分析轴，未提供时写图前拒绝；显式x须同时指定y；仅y沿原行号绘制，均省略保留原默认。histogram仅x/仅y均可，同时指定必须同列。scatter显式选轴时须同时指定x_col/y_col，均省略才使用原前两数值列默认。时间折线保留完整时间戳并排序，仅相同时间戳×颜色组聚合。非时间折线显式聚合按相同x×颜色组；数值x升序，分类x首次出现顺序。funnel显式x/y优先选步骤/计数，省略一侧仅用该侧原别名，计数须有限非负整数。日/月桶须先用transform_data显式生成，不从标题推断。"},
        "label_columns": {"description": "组合分析单位的列名，英文逗号分隔。与 x_col 二选一；在绘图副本中生成可逆的组合标签，保留注册数据集血缘。"},
        "y_col": {"description": "Y轴列；line/bar/scatter和heatmap支持逗号分隔多列，histogram/box/pie/stacked_bar/funnel显式仅一列"},
        "color_col": {"description": "颜色分组列；box/histogram/pie/heatmap/funnel不支持，显式指定会拒绝"},
        "data_json": {"description": "独立JSON探索数据；不得与data/result_ref并用，不绑定注册数据表事实。funnel也可直接使用注册表。"},
        "aggregation": {"description": "重复分组的聚合方式；pie显式sum/mean/median须单列y指标，缺指标写图前拒绝；仅x分类频数及等价count保留。scatter/box/histogram/heatmap/funnel不支持，显式指定会拒绝；sum全缺失组未知，count统计原指定列非缺失条数（非去重人数）；未知组饼图拒绝", "enum": ["", "sum", "mean", "median", "count"]},
        "scale_mode": {"description": "raw=原值；normalize=每序列绝对值最大值为100(折线/柱图)；index100=每序列首个观测值为100(仅折线，首值不可为0/缺失)。", "enum": ["", "raw", "normalize", "index100"]},
        "purpose": {"description": "exploratory 为探索图；evidence/insight 须引用当前会话证据及注册数据集", "enum": ["exploratory", "evidence", "insight"]},
        "evidence_ids": {"description": "当前会话 evidence_id，多个 ID 使用英文逗号分隔；不是工具名。"},
        "result_ref": {"description": "工具返回的 tool_outputs/..._detail.json 引用。须有唯一当前数据来源，直接绘制其chart_data；可附data作同源身份断言，不得与data_json并用。curve_fitting 使用 x_col=x、y_col=actual,power_fit（或工具返回的最佳族）。"},
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
    result_ref: str = "",
    label_columns: str = "",
) -> str | ToolResult:
    if data_json and (data or result_ref):
        return _chart_error("data_json cannot be combined with data or result_ref", [],
                            error_code="chart_source_conflict")
    fig = go.Figure()
    plotted_numeric_columns = []
    if scale_mode != "index100" and re.search(r"(?:首日|首个|第一|first|base).*?100", title, re.I):
        return _chart_error("Title claims first observation=100; select scale_mode=index100.", [],
                            error_code="scale_label_mismatch", recovery_options=[{"scale_mode": "index100"}])

    # 获取数据
    df = None
    data_name = data
    result_binding = None
    if result_ref:
        from data_agent.tools.result_reference import load_chart_result_reference
        try:
            result_payload, result_binding, data_name = load_chart_result_reference(result_ref, dataset=data)
            df = pd.DataFrame(result_payload["chart_data"])
        except (ValueError, KeyError, OSError) as exc:
            return _chart_error("Invalid result_ref", [str(exc)], error_code="chart_result_source_invalid")
    elif data:
        if data not in workspace.list_datasets():
            return _chart_error("Explicit dataset is not available: " + data, [],
                                error_code="chart_dataset_not_found")
        df = workspace.get(data)
        if df is None:
            return _chart_error("Explicit dataset cannot be read: " + data, [],
                                error_code="chart_dataset_unavailable")
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

    labels = [c.strip() for c in label_columns.split(",") if c.strip()]
    if labels:
        if x_col or len(labels) < 2 or len(set(labels)) != len(labels) or any(c not in df.columns for c in labels):
            return _chart_error("Invalid label_columns", ["Use at least two distinct existing columns and omit x_col."])
        df = df.copy()
        x_col = "组合分析单位"
        while x_col in df.columns:
            x_col += "_"
        df[x_col] = df[labels].apply(lambda row: json.dumps(
            [None if pd.isna(value) else str(value) for value in row], ensure_ascii=False), axis=1)

    try:
        metadata, validation_error = _validate_chart_spec(df, chart_type, data_name, title, x_col, y_col, color_col, aggregation, scale_mode)
        if validation_error:
            return validation_error
        if metadata is not None:
            if labels:
                metadata["label_columns"] = labels
            allowed_purposes = {"exploratory", "evidence", "insight"}
            normalized_purpose = (purpose or "exploratory").strip().lower()
            if normalized_purpose not in allowed_purposes:
                return _chart_error(
                    f"invalid chart purpose: {purpose}",
                    [f"purpose must be one of {sorted(allowed_purposes)}"],
                )
            metadata["purpose"] = normalized_purpose
            metadata["evidence_ids"] = _parsed_evidence_ids(evidence_ids)
            # A chart used as evidence must remain traceable to the exact
            # session dataset (and, for a derived table, its parent dataset).
            # Do not infer this from the chart title or LLM prose.
            dataset_info = workspace.list_datasets().get(data_name, {}) if data_name else {}
            parent_dataset = dataset_info.get("derived_from", "")
            source_dataset = parent_dataset or data_name
            source_meta = workspace.get_metadata(source_dataset) if source_dataset else {}
            metadata["data_identity"] = {
                **workspace.get_data_identity(data_name),
                "dataset": data_name,
                "source_dataset": source_dataset,
                "derived_from": parent_dataset,
                "source_path": source_meta.get("_source_path", ""),
                "source_fingerprint": source_meta.get("source_fingerprint") or workspace.get_data_identity(data_name).get("source_fingerprint", ""),
            }
            metadata["source_kind"] = "result_ref" if result_binding is not None else "dataset" if data_name else "inline_json"
            if not data_name:
                metadata["data_identity"] = {}
            if result_binding is not None:
                metadata["result_binding"] = result_binding
            if normalized_purpose in {"evidence", "insight"} and not metadata["evidence_ids"]:
                return _chart_error(
                    "purpose 'evidence' or 'insight' requires evidence_ids",
                    ["missing evidence_ids for evidence-backed chart"],
                )
            if normalized_purpose in {"evidence", "insight"} and not data_name:
                return _chart_error(
                    "evidence-backed chart requires a registered session dataset",
                    ["data_json may be used for exploratory charts only"],
                )
            if normalized_purpose in {"evidence", "insight"}:
                unresolved_ids = _unresolved_evidence_ids(metadata["evidence_ids"])
                if unresolved_ids:
                    return _chart_error(
                        "evidence_ids do not resolve in the active session",
                        [f"unknown evidence ids: {', '.join(unresolved_ids)}"],
                    )
                unbound_ids = _unbound_chart_evidence(metadata["evidence_ids"], data_name, result_binding)
                if unbound_ids:
                    return _chart_error(
                        "Evidence does not bind the chart's current data version and result",
                        [f"unbound evidence ids: {', '.join(unbound_ids)}"],
                        error_code="chart_evidence_binding_mismatch",
                        recovery_options=[{"action": "recompute evidence for the current data version, or use exploratory purpose"}],
                    )

        y_cols_for_plot = [c.strip() for c in y_col.split(",") if c.strip()]
        chart_source_df = df.copy()
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
            metadata["source_row_count"] = contract.source_row_count
            metadata["dropped_row_count"] = contract.dropped_row_count
            metadata["dropped_missing_fields"] = contract.dropped_missing_fields
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
        if metadata is not None:
            metadata["plotted_row_count"] = int(len(df))
        if chart_type == "pie" and y_cols_for_plot and df[y_cols_for_plot].isna().any().any():
            return _chart_error("Pie chart has unknown group values; use a table or bar chart to preserve unknowns.",
                                (metadata or {}).get("validation_warnings", []),
                                error_code="unknown_pie_measure")

        if scale_mode == "index100" and x_col and (metadata or {}).get("axis_order") != "category_first_appearance":
            df = df.sort_values(x_col, kind="stable").copy()
        raw_df = df.copy()
        if scale_mode in {"normalize", "index100"}:
            df = df.copy()
            for col in y_cols_for_plot:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
            groups = df.groupby(color_col, sort=False, dropna=False).groups.values() if color_col else [df.index]
            for indices in groups:
                for col in y_cols_for_plot:
                    values = pd.to_numeric(df.loc[indices, col], errors="coerce")
                    denominator = values.iloc[0] if scale_mode == "index100" else values.abs().max()
                    if pd.isna(denominator) or not np.isfinite(denominator) or denominator == 0:
                        return _chart_error("Scale denominator must be finite and nonzero; use raw or revise the scope explicitly.", [], error_code="invalid_scale_denominator")
                    df.loc[indices, col] = values / denominator * 100
            if metadata is not None:
                metadata["scale_mode"] = scale_mode
                transformation = f"scale:{scale_mode}"
                if transformation not in metadata.setdefault("transformations", []):
                    metadata["transformations"].append(transformation)

        if chart_type == "line":
            if x_col and y_col:
                y_cols = [c.strip() for c in y_col.split(",") if c.strip()]
                plotted_numeric_columns = list(y_cols)
                axis_groups = [y_cols] if scale_mode in {"normalize", "index100"} else _detect_axis_groups(df, y_cols)
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
                numeric_cols = y_cols_for_plot or list(df.select_dtypes(include="number").columns[:3])
                plotted_numeric_columns = list(numeric_cols)
                for col in numeric_cols:
                    fig.add_trace(go.Scatter(y=df[col], mode="lines+markers", name=col))

        elif chart_type == "bar":
            if x_col and y_col:
                y_cols = [c.strip() for c in y_col.split(",") if c.strip()]
                plotted_numeric_columns = list(y_cols)
                grouped = list(df.groupby(color_col, sort=False, dropna=False)) if color_col else [(None, df)]
                for col in y_cols:
                    for cat, group_df in grouped:
                        trace_name = col if not color_col else str(cat) if len(y_cols) == 1 else f"{cat} - {col}"
                        original = pd.to_numeric(raw_df.loc[group_df.index, col], errors="coerce")
                        trace = go.Bar(
                            x=_plotly_axis_values(group_df[x_col]),
                            y=group_df[col], name=trace_name,
                            meta={"metric": col, "color_column": color_col,
                                  "color_value": None if pd.isna(cat) else cat},
                        )
                        if scale_mode == "normalize":
                            trace.customdata = original
                            trace.hovertemplate = (
                                "%{fullData.name}<br>%{x}<br>"
                                "Normalized value=%{y:.2f}<br>"
                                "Original value=%{customdata}<extra></extra>"
                            )
                        fig.add_trace(trace)
                if len(y_cols) > 1 or color_col:
                    fig.update_layout(barmode="group")
                if len(y_cols) > 1:
                    fig.update_layout(yaxis_title="Normalized value (max=100)" if scale_mode == "normalize" else "Value")
            else:
                numeric_cols = y_cols_for_plot or list(df.select_dtypes(include="number").columns[:5])
                plotted_numeric_columns = list(numeric_cols)
                for col in numeric_cols:
                    fig.add_trace(go.Bar(x=df.index, y=df[col], name=col))

        elif chart_type == "stacked_bar":
            if x_col and y_col and color_col:
                plotted_numeric_columns = [y_col]
                for cat, group_df in df.groupby(color_col, sort=False, dropna=False):
                    fig.add_trace(go.Bar(x=_plotly_axis_values(group_df[x_col]), y=group_df[y_col], name=str(cat)))
                fig.update_layout(barmode="stack")
            else:
                return "Error: stacked_bar 需要 x_col, y_col 和 color_col"

        elif chart_type == "scatter":
            if x_col and y_col:
                y_cols = [c.strip() for c in y_col.split(",") if c.strip()]
                plotted_numeric_columns = [x_col, *y_cols]
                mode = "lines+markers" if len(y_cols) > 1 and _title_claims_series_comparison(title) else "markers"
                for col in y_cols:
                    if color_col:
                        for cat, group_df in df.groupby(color_col, sort=False, dropna=False):
                            trace_name = str(cat) if len(y_cols) == 1 else f"{cat} - {col}"
                            fig.add_trace(go.Scatter(
                                x=group_df[x_col],
                                y=group_df[col],
                                mode=mode,
                                name=trace_name,
                            ))
                    else:
                        fig.add_trace(go.Scatter(
                            x=df[x_col], y=df[col], mode=mode, name=col,
                        ))
            else:
                numeric_cols = df.select_dtypes(include="number").columns
                if len(numeric_cols) >= 2:
                    plotted_numeric_columns = list(numeric_cols[:2])
                    fig.add_trace(go.Scatter(x=df[numeric_cols[0]], y=df[numeric_cols[1]], mode="markers"))

        elif chart_type == "box":
            if x_col and y_col:
                plotted_numeric_columns = [y_col]
                fig.add_trace(go.Box(
                    x=_plotly_axis_values(df[x_col]),
                    y=pd.to_numeric(df[y_col], errors="coerce").tolist(),
                    name=y_col,
                ))
            else:
                cols = y_cols_for_plot or list(df.select_dtypes(include="number").columns[:5])
                plotted_numeric_columns = list(cols)
                for col in cols:
                    fig.add_trace(go.Box(y=df[col].dropna(), name=col))

        elif chart_type == "histogram":
            col = y_col or x_col
            if col and col in df.columns:
                plotted_numeric_columns = [col]
                fig.add_trace(go.Histogram(x=df[col].dropna(), name=col))
            else:
                numeric_cols = df.select_dtypes(include="number").columns
                if len(numeric_cols):
                    col = numeric_cols[0]
                    plotted_numeric_columns = [col]
                    fig.add_trace(go.Histogram(x=df[col].dropna(), name=col))

        elif chart_type == "heatmap":
            selected_cols = list(dict.fromkeys(
                [name for name in [x_col, *y_cols_for_plot] if name]
            ))
            from data_agent.tools._utils import finite_pairwise_correlation
            original = chart_source_df[selected_cols]
            converted = original.apply(pd.to_numeric, errors="coerce")
            numeric_df, corr, pair_counts = finite_pairwise_correlation(converted, "pearson")
            columns_audit = {}
            for column in selected_cols:
                values = converted[column]
                columns_audit[column] = {
                    "source_rows": int(len(original)), "missing_count": int(original[column].isna().sum()),
                    "non_numeric_count": int((values.isna() & original[column].notna()).sum()),
                    "nonfinite_count": int((values.notna() & ~np.isfinite(values)).sum()),
                    "finite_count": int(numeric_df[column].notna().sum()),
                }
            audit = {"method": "pearson", "scope": "pairwise_finite_observations",
                     "source_rows": int(len(original)), "columns": columns_audit, "pairwise_counts": pair_counts}
            if metadata is not None:
                metadata["correlation_audit"] = audit
                losses = sum(v["nonfinite_count"] + v["non_numeric_count"] for v in columns_audit.values())
                if losses:
                    metadata["completion_gap"] = {"status": "evidence_insufficient", "reason":
                        f"相关图已按成对有限观测计算；{losses} 个非有限或无法转换的列值被排除，原请求范围未完整覆盖。"}
                    metadata["validation_status"] = "warning"
                    metadata["validation_warnings"].append(metadata["completion_gap"]["reason"])
            counts_array = [[pair_counts[row][col] for col in corr.columns] for row in corr.index]
            fig.add_trace(go.Heatmap(z=corr.values, x=list(corr.columns), y=list(corr.columns),
                customdata=counts_array, hovertemplate="%{y} / %{x}<br>Pearson=%{z}<br>有效成对观测数=%{customdata}<extra></extra>",
                colorscale="RdBu_r", zmin=-1, zmax=1))
            from html import escape
            unknown = [f"{escape(str(row))}/{escape(str(col))}(n={pair_counts[row][col]})"
                       for i, row in enumerate(corr.index) for col in list(corr.columns)[i:]
                       if pd.isna(corr.loc[row, col])]
            note = "整体Pearson关联；每对仅用共同有限观测，不证明因果或预测。"
            if unknown:
                note += "<br>未知系数（不是0）：" + "；".join(unknown)
            if metadata is not None and metadata.get("completion_gap"):
                note += "<br>" + metadata["completion_gap"]["reason"]
            fig.add_annotation(text=note, xref="paper", yref="paper", x=0, y=1.06, showarrow=False)

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

            funnel_data, funnel_error = _normalize_funnel_rows(
                funnel_data, x_col, y_cols_for_plot[0] if y_cols_for_plot else "")
            if funnel_error:
                return _chart_error(f"invalid funnel data: {funnel_error}", [funnel_error])

            fig = go.Figure(go.Funnel(
                y=[s["step"] for s in funnel_data],
                x=[s["count"] for s in funnel_data],
                textinfo="value+percent initial+percent previous",
                marker={"color": px.colors.qualitative.Plotly[:len(funnel_data)]},
            ))

        elif chart_type == "pie":
            if x_col and y_col:
                plotted_numeric_columns = [y_col]
                pie_df = df[[x_col, y_col]].copy()
                fig.add_trace(go.Pie(
                    labels=pie_df[x_col].astype(str).tolist(),
                    values=pd.to_numeric(pie_df[y_col], errors="coerce").tolist(),
                ))
            elif x_col and x_col in df.columns:
                counts = df[x_col].value_counts()
                fig.add_trace(go.Pie(
                    labels=counts.index.astype(str).tolist(),
                    values=counts.values.tolist(),
                ))
            else:
                return _chart_error(
                    "pie chart requires x_col for category labels",
                    ["missing pie category column"],
                )

        else:
            return f"Error: 不支持的图表类型 '{chart_type}'。支持: line, bar, stacked_bar, scatter, box, histogram, heatmap, pie, funnel"

        renderability_error = validate_figure_renderability(fig)
        if renderability_error:
            return _chart_error(
                renderability_error,
                [],
                error_code="non_renderable_figure",
                recovery_options=[{
                    "presentation": "table",
                    "description": "Inspect the selected fields and present verified values as a table.",
                }],
            )

        # Count consumes original entries, not numeric measures; its effective counts
        # already belong to the original aggregation audit.
        counted = is_chart_count_aggregation(chart_source_df, chart_type, x_col, aggregation)
        observation = _chart_observation_audit(chart_source_df, [] if counted else plotted_numeric_columns, len(df))
        if metadata is not None and observation is not None:
            metadata["observation_audit"] = observation
            from html import escape
            details = "；".join(f"{escape(str(name))}：有限{item['finite_count']}/{item['source_rows']}，原缺失{item['missing_count']}，转换失败{item['non_numeric_count']}，非有限{item['nonfinite_count']}"
                                for name, item in observation["columns"].items())
            note = "实际数值范围：" + details + "。缺失值沿该图种原规则处理，不推断其业务含义。"
            if observation["joint_unusable_numeric_rows"]:
                reason = f"所选数值字段有{observation['joint_unusable_numeric_rows']}条源记录包含无法转换或非有限值；已保留按原规则计算的图和未知缺口，原请求范围未完整覆盖。"
                metadata["completion_gap"] = {"status": "evidence_insufficient", "reason": reason}
                metadata["validation_status"] = "warning"
                metadata.setdefault("validation_warnings", []).append(reason)
                note += "<br>" + reason
            fig.add_annotation(text=note, xref="paper", yref="paper", x=0, y=1.18, showarrow=False)

        audit = (metadata or {}).get("aggregation_audit")
        if audit:
            for trace in fig.data:
                if chart_type == "pie":
                    trace.text = _aggregation_hover_text(metadata, df.index, y_cols_for_plot[0])
                    trace.hovertemplate = "%{label}<br>%{value}<br>%{text}<extra></extra>"
                    continue
                column = next((col for col in y_cols_for_plot if trace.name == col), None)
                selected = df
                if chart_type == "bar" and isinstance(trace.meta, dict):
                    column = trace.meta["metric"]
                    if color_col:
                        value = trace.meta["color_value"]
                        selected = df[df[color_col].isna() if value is None else df[color_col] == value]
                elif color_col:
                    candidates = [(col, cat, part) for cat, part in df.groupby(color_col, sort=False, dropna=False)
                                  for col in y_cols_for_plot
                                  if trace.name == (str(cat) if len(y_cols_for_plot) == 1 else f"{cat} - {col}")]
                    if len(candidates) == 1:
                        column, _, selected = candidates[0]
                if column is not None:
                    trace.text = _aggregation_hover_text(metadata, selected.index, column)
                    trace.hovertemplate = (trace.hovertemplate.replace("<extra>", "<br>%{text}<extra>")
                                           if trace.hovertemplate else "%{x}<br>%{y}<br>%{text}<extra>%{fullData.name}</extra>")
            if audit["unknown_group_count"]:
                from html import escape
                unknown_groups = [g for g in audit["groups"] if any(v is None for v in g["values"].values())]
                unknown_counts = "；".join(
                    escape(json.dumps(g["group"], ensure_ascii=False)) + "：" +
                    "，".join(f"{escape(col)}有效观测数={count}" for col, count in g["valid_counts"].items())
                    for g in unknown_groups
                )
                fig.add_annotation(text="存在未知聚合值；未知不是0。<br>未知组：" + unknown_counts +
                                   "<br>已知组有效观测数见悬浮信息。",
                                   xref="paper", yref="paper", x=0, y=1.06, showarrow=False)

        if labels and x_col in df.columns:
            _apply_combined_label_axis(fig, df[x_col], metadata)
        fig.update_layout(title=title, template="plotly_white")
        if scale_mode in {"normalize", "index100"}:
            fig.update_yaxes(title_text="Index (first observation=100)" if scale_mode == "index100" else "Normalized value (max absolute=100)")
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


def _count_chart_matches(frame,arguments,metadata):
    """Host verification of original record counts;no chart execution or save."""
    typ=arguments.get('chart_type');x=arguments.get('x_col','');ys=[v.strip() for v in arguments.get('y_col','').split(',') if v.strip()];color=arguments.get('color_col','')
    if (frame is None or not frame.columns.is_unique or arguments.get('aggregation')!='count'
            or typ not in {'bar','line','stacked_bar','pie'} or arguments.get('scale_mode','') not in {'','raw'}
            or any(arguments.get(k) for k in ('result_ref','data_json','label_columns')) or not x or not ys):return False
    try:
        checked=validate_chart_request(frame,typ,x,ys,color,'count',arguments.get('scale_mode',''))
        if not checked.valid:return False
        rebuilt={};df=_prepare_chart_dataframe(checked.dataframe,typ,x,ys,color,rebuilt,'count')
        audit=rebuilt.get('aggregation_audit')
        if not audit or audit!=metadata.get('aggregation_audit'):return False
        def numbers(value):
            if isinstance(value,dict):
                import base64
                if set(value)-{'dtype','bdata','shape'} or value.get('dtype') not in {'i1','u1','i2','u2','i4','u4','i8','u8','f4','f8'}:return None
                payload=np.frombuffer(base64.b64decode(value['bdata'],validate=True),dtype=value['dtype'])
                if 'shape' in value and tuple(int(v.strip()) for v in str(value['shape']).split(','))!=(len(payload),):return None
                value=payload.tolist()
            if not isinstance(value,(list,tuple)) or any(type(v) not in {int,float} or not np.isfinite(v) for v in value):return None
            return list(value)
        traces=metadata.get('figure',{}).get('data',[]);expected=[]
        if not isinstance(traces,list) or any(not isinstance(t,dict) for t in traces):return False
        grouped=list(df.groupby(color,sort=False,dropna=False)) if color else [(None,df)]
        for col in ys:
            for cat,part in grouped:
                name=col if not color else str(cat) if len(ys)==1 else f'{cat} - {col}'
                expected.append((name,col,cat,part))
        if len(traces)!=len(expected) or len({name for name,_,_,_ in expected})!=len(expected):return False
        for name,col,cat,part in expected:
            matches=[t for t in traces if t.get('name','')==name] if typ!='pie' else traces
            if len(matches)!=1:return False
            trace=matches[0];axis=part[x].astype(str).tolist() if typ=='pie' else _plotly_axis_values(part[x])
            if (trace.get('type')!={'bar':'bar','stacked_bar':'bar','line':'scatter','pie':'pie'}[typ]
                    or trace.get('labels' if typ=='pie' else 'x')!=axis
                    or numbers(trace.get('values' if typ=='pie' else 'y'))!=part[col].tolist()
                    or list(trace.get('text',[]))!=_aggregation_hover_text(rebuilt,part.index,col)):return False
            if typ=='bar' and trace.get('meta')!={'metric':col,'color_column':color,'color_value':None if pd.isna(cat) else cat}:return False
        return True
    except (ValueError,TypeError,KeyError,OverflowError):return False
