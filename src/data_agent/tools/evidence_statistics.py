"""Project statistical detail from the already-validated result receipts."""
from __future__ import annotations

import ast
import json
import math


DESCRIPTIVE_TOOLS = {"curve_fitting", "compare_periods", "cohort_analysis", "synthesize_time_series",
                     "analyze_time_series",
                     "detect_data_quality", "apply_type_conversion", "transform_data", "top_n",
                     "quick_profile", "describe_dataset"}
SUPPORT_TOOLS = {"create_chart", "read_file", "list_files", "write_file", "preview_data", "list_data"}


def literal_result(text):
    """Decode literals, including NumPy scalar repr, without executing calls.

    Arbitrary stdout/prose is deliberately not interpreted as measurements.
    """
    if not isinstance(text, str) or len(text) > 100_000:
        return None
    try:
        tree = ast.parse(text.strip(), mode="eval")
        nodes = list(ast.walk(tree))
        if len(nodes) > 20_000:
            return None
        for node in nodes:
            if isinstance(node, ast.Call):
                if not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "np" and node.func.attr in {
                            "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
                            "float16", "float32", "float64", "bool_"}
                        and len(node.args) == 1 and not node.keywords):
                    return None
                value = ast.literal_eval(node.args[0])
                if not isinstance(value, (int, float, bool)) or not math.isfinite(value):
                    return None
        class Scalars(ast.NodeTransformer):
            def visit_Call(self, node):
                return ast.copy_location(ast.Constant(ast.literal_eval(node.args[0])), node)
        value = ast.literal_eval(Scalars().visit(tree))
        # Reject non-finite/unsupported values, not silently stringifying them.
        json.dumps(value, allow_nan=False)
        return value if isinstance(value, (dict, list)) else None
    except (ValueError, SyntaxError, TypeError, RecursionError, OverflowError):
        return None


def sandbox_values(result):
    value = literal_result(result.get("result"))
    if value is not None:
        return value
    # Whole dictionary stdout is common in A02. Mixed prose is not a typed
    # result; reading a few numeric fragments would silently lose the scope.
    return literal_result(result.get("output"))


def _bound_dataset_time_scope(receipts: list[dict]) -> dict | None:
    """Derive a date window only from current, receipt-bound datasets.

    Custom sandbox calculations and transformations do not all return a
    dedicated observation-window field.  Their receipts still carry exact
    dataset identities.  Falling back to those bound frames closes that
    structural gap without trusting a model-reported date or parsing prose.
    """
    import pandas as pd

    from data_agent.session.workspace import workspace

    windows = []
    seen = set()
    for receipt in receipts:
        arguments = receipt.get("arguments") or {}
        explicit = str(arguments.get("date_col") or "").strip()
        identities = receipt.get("data_identities") or {}
        for name in receipt.get("dataset_refs") or []:
            name = str(name)
            identity = identities.get(name)
            if not identity or (name, str(identity.get("version_id") or "")) in seen:
                continue
            frame = workspace.get(name)
            if frame is None or frame.empty:
                continue
            candidates = []
            if explicit and explicit in frame.columns:
                candidates.append(explicit)
            candidates.extend(
                str(column) for column in frame.columns
                if pd.api.types.is_datetime64_any_dtype(frame[column]) and str(column) not in candidates
            )
            candidates.extend(
                str(column) for column in frame.columns
                if str(column) not in candidates
                and any(hint in str(column).casefold() for hint in ("date", "time", "日期", "时间"))
            )
            for column in candidates:
                values = pd.to_datetime(frame[column], errors="coerce").dropna()
                if values.empty:
                    continue
                windows.append({
                    "dataset": name,
                    "version_id": identity.get("version_id", ""),
                    "column": column,
                    "start": pd.Timestamp(values.min()).isoformat(),
                    "end": pd.Timestamp(values.max()).isoformat(),
                    "non_null_rows": int(values.size),
                    "source_rows": int(len(frame)),
                })
                seen.add((name, str(identity.get("version_id") or "")))
                break
    return {"datasets": windows} if windows else None


def bind_computed_statistics(payload: dict, receipts: list[dict]) -> None:
    from data_agent.tools.result_reference import load_result_reference
    from data_agent.tools._utils import sanitize_filename

    results = []
    for receipt in receipts:
        if not receipt.get("structured_result_sha256"):
            continue  # Legacy receipts remain subject to their existing checks.
        reference = "tool_outputs/" + sanitize_filename(receipt["tool_call_id"]) + "_detail.json"
        result, binding = load_result_reference(reference)
        if binding["receipt_id"] != receipt["id"]:
            raise ValueError("Statistical detail does not match selected receipt")
        results.append((receipt["tool_name"], result, binding, receipt.get("arguments", {})))
    if not results:
        return

    payload["computed_statistics_sources"] = [binding for _, _, binding, _ in results]
    # Model-reported nested/top-level statistics are annotations, not an
    # alternative authority when a current result receipt is available.
    reported = dict(payload.pop("statistical_details", {}) or {})
    for key in ("metrics", "sample_size", "significance", "correlation", "confidence_interval"):
        if key in payload:
            reported.setdefault(key, payload.pop(key))
    if reported:
        payload["reported_statistical_details"] = reported
    required = {"metrics", "time_scope", "calculation_method", "method_detail"}
    metrics = {}
    gaps = []
    methods = []
    details = []
    inference = False
    for tool, result, binding, arguments in results:
        if not isinstance(result, dict):
            gaps.append({"receipt_id": binding["receipt_id"], "reason": "unsupported_result_shape"})
            continue
        if tool in SUPPORT_TOOLS:
            continue
        methods.append(tool)
        details.append({"receipt_id": binding["receipt_id"], "tool": tool, "arguments": arguments})
        projected = None
        if tool == "ab_test" and isinstance(result.get("test"), dict):
            inference = True
            metrics[tool] = {k: result[k] for k in ("groups", "difference", "analysis_unit", "design") if k in result}
            payload["significance"] = {k: result[k] for k in ("test", "wilcoxon_signed_rank") if k in result}
            payload["sample_size"] = result.get("paired_sample_size") or sum(g.get("n", 0) for g in result.get("groups", {}).values())
            payload["confidence_interval"] = result.get("difference", {}).get("confidence_interval_95")
            required.update(["sample_size", "significance"])
            if result.get("design") == "paired":
                required.add("confidence_interval")
        elif tool in DESCRIPTIVE_TOOLS:
            projected = {k: result[k] for k in (
                "metrics", "fits", "cohorts", "aligned_rows", "source_identities", "missing_aligned_dates",
                "period_a", "period_b", "combined", "conversion", "rows", "summary", "records",
                "coverage", "shape", "quality", "points", "analysis_unit", "right_censoring",
                "data_points", "date_range", "statistics", "trend", "change_points", "seasonality",
                "claim_ceiling", "limitations", "fields", "field_statistics", "total_issues", "issues") if k in result}
            if result.get("observation_window"):
                payload["time_scope"] = result["observation_window"]
            elif tool == "compare_periods":
                payload["time_scope"] = {p: result[p].get("range") for p in ("period_a", "period_b")}
            elif tool == "synthesize_time_series" and result.get("coverage"):
                payload["time_scope"] = result["coverage"]
            elif tool == "curve_fitting" and result.get("points"):
                x = [p["x"] for p in result["points"] if "x" in p]
                if x:
                    payload["time_scope"] = {"observed_x_min": min(x), "observed_x_max": max(x), "extrapolation": False}
            elif tool == "analyze_time_series" and isinstance(result.get("date_range"), dict):
                payload["time_scope"] = result["date_range"]
            if tool == "analyze_time_series" and isinstance(result.get("trend"), dict):
                trend = result["trend"]
                if isinstance(trend.get("p_value"), (int, float)):
                    inference = True
                    required.update(["sample_size", "significance"])
                    payload["significance"] = {
                        "trend": {key: trend[key] for key in ("p_value", "significant") if key in trend}
                    }
            if result.get("effective_n") is not None:
                payload["sample_size"] = result["effective_n"]
            elif tool == "analyze_time_series" and isinstance(result.get("data_points"), int):
                payload["sample_size"] = result["data_points"]
            elif "sample_size" not in payload:
                count = result.get("aligned_rows", result.get("combined", {}).get("row_count"))
                if count is None and tool == "cohort_analysis":
                    count = sum(row["size"] for row in result.get("cohorts", []) if "size" in row)
                if count is None:
                    count = result.get("rows")
                if count is None and isinstance(result.get("shape"), dict):
                    count = result["shape"].get("rows")
                if count is not None:
                    payload["sample_size"] = count
        elif tool == "run_python":
            projected = sandbox_values(result)
            if isinstance(projected, dict) and "sample_size" not in payload:
                for count_key in ("sample_size", "rows", "left_rows", "voucher_rows"):
                    count = projected.get(count_key)
                    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                        payload["sample_size"] = count
                        payload["sample_size_source"] = {"receipt_id": binding["receipt_id"], "field": count_key}
                        break
            if projected is None:
                gaps.append({"receipt_id": binding["receipt_id"], "reason": "untyped_sandbox_output",
                             "blocking": result.get("fallback_policy", {}).get("role") != "supplemental",
                             "recovery": "Use a native analysis tool or return a literal result dictionary with metrics and scope; free-form stdout is retained as exploratory output."})
        else:
            gaps.append({"receipt_id": binding["receipt_id"], "reason": "unsupported_statistical_method"})
        if projected is not None:
            # Multiple calls to the same tool must not overwrite earlier facts.
            key = tool if tool not in metrics else tool + ":" + binding["receipt_id"]
            metrics[key] = projected
    if metrics:
        payload["metrics"] = metrics
    if methods:
        payload["calculation_method"] = list(dict.fromkeys(methods))
        payload["method_detail"] = details
    if not payload.get("time_scope"):
        time_scope = _bound_dataset_time_scope(receipts)
        if time_scope:
            payload["time_scope"] = time_scope
            payload["time_scope_source"] = {
                "type": "current_receipt_bound_datasets",
                "receipt_ids": [str(receipt.get("id") or "") for receipt in receipts],
            }
    payload["statistical_projection_gaps"] = gaps
    payload["statistical_detail_required_fields"] = sorted(required)
    payload["statistical_inference"] = inference
