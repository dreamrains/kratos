"""Render accepted nodes in place and locate them in the single public body."""
from decimal import Decimal
from html import escape
import json
from urllib.parse import quote

from .contracts import encode

STATUS_LABELS = {"partial":"部分完成", "not_computed":"未计算", "evidence_insufficient":"证据不足",
                 "needs_confirmation":"需要业务口径确认", "failed":"未完成"}


def _cell(value):
    """Escape a canonical value for Markdown without changing its precision."""
    text = "未知" if value is None else value if isinstance(value, str) else encode(value)
    text = escape(text, quote=True).replace("\\", "\\\\")
    for char in "|`*_[]":
        text = text.replace(char, "\\" + char)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "&#10;")


def _table(columns, rows):
    lines = ["| " + " | ".join(_cell(c) for c in columns) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend("| " + " | ".join(_cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def _context_value(claim, context, path):
    # Context may supply only a scalar from the very same verified receipt,
    # version and structured result. Never borrow a nearby dataset or run.
    bindings = [{k: v for k, v in b.items() if k != "result_path"}
                for b in claim["basis_refs"]]
    values = []
    for other in context:
        for basis in other.get("basis_refs", []):
            if (basis.get("result_path") == path and
                    {k: v for k, v in basis.items() if k != "result_path"} in bindings):
                values.append(other["value"])
    return values[0] if values and all(v == values[0] for v in values) else None


def _period_heading(claim, context, *, dates_only=False):
    # time_scope is host-generated structured JSON, not answer prose.
    try:
        scope = json.loads(claim["scope"]["time_scope"])
    except (ValueError, TypeError):
        scope = {}
    if dates_only and (not isinstance(scope, dict) or set(scope) != {"period_a", "period_b"}
            or any(not isinstance(v, list) or len(v) != 2
                   or any(item is not None and not isinstance(item, str) for item in v)
                   for v in scope.values())):
        return None
    parts = []
    for key, label in (("period_a", "前期"), ("period_b", "后期")):
        dates = scope.get(key) if isinstance(scope, dict) else None
        period = "—".join(_cell(v) for v in dates) if isinstance(dates, list) and len(dates) == 2 else "日期未知"
        if dates_only:
            parts.append(label + "：" + period)
            continue
        days = _context_value(claim, context, [key, "day_count"])
        rows = _context_value(claim, context, [key, "rows"])
        parts.append(label + "：" + period + "（" + _cell(days) + "天；" + _cell(rows) + "条）")
    return "；".join(parts)


def _business_table(claim, context):
    target = claim.get("target", {})
    product = target.get("business_product", {})
    if product.get("kind") != "table":
        return None
    params = product["parameters"]
    value = claim["value"]
    if target["tool"] == "top_n":
        output = params.get("topn_output")
        if output == "records" and isinstance(value, list):
            columns = list(params["topn_columns"])
            for row in value:
                columns.extend(k for k in row if k not in columns)
            heading = "按 " + _cell(params["topn_sort_by"]) + (" 升序" if params["topn_ascending"] else " 降序") + "；请求前 " + _cell(params["topn_n"]) + " 条记录"
            shown = heading + "\n\n" + _table(columns, [[row.get(k) for k in columns] for row in value])
            if not value:
                shown += "\n\n当前排行范围无返回记录。"
            return shown
        if output == "observation" and isinstance(value, dict):
            return _table(["源表记录数", "实际返回记录数"], [[value.get("source_rows"), value.get("returned_rows")]])
    if target["tool"] == "distribution_analysis" and isinstance(value, dict):
        # The native distribution table is a verified per-column result.
        # Keep its existing numbers, unknowns and inference boundaries intact.
        observation = value["observation"]
        quantiles = value["quantiles"]
        normality = value["normality_test"]
        conclusion = {"not_rejected": "未拒绝正态性", "rejected": "拒绝正态性"}.get(normality["conclusion"], "未知")
        parts = [_cell(claim["label"]),
                 _table(["有效观测数", "均值", "总体标准差", "偏度", "峰度"],
                        [[value[k] for k in ("count", "mean", "std", "skewness", "kurtosis")]]),
                 _table(["最小值", "25%分位数", "中位数", "75%分位数", "最大值"],
                        [[quantiles[k] for k in ("min", "25%", "50%", "75%", "max")]]),
                 "分位数：线性插值。",
                 _table(["原始记录数", "有效观测数", "缺失数", "非有限值排除数"],
                        [[observation[k] for k in ("source_rows", "count", "missing_count", "excluded_nonfinite")]]),
                 _table(["正态检验", "p值", "判断", "不可计算原因"],
                        [["Shapiro–Wilk", normality["p_value"], conclusion, normality["reason"] or "—"]])]
        return "\n\n".join(parts)
    if target["tool"] != "compare_periods":
        return None
    output = params.get("comparison_output")
    heading = _period_heading(claim, context)
    if output == "observation" and isinstance(value, dict):
        labels = {"source_rows":"原始记录数", "valid_date_rows":"有效日期记录数",
                  "date_excluded_rows":"日期排除记录数", "missing_date":"日期缺失记录数",
                  "invalid_date":"坏日期记录数", "outside_windows_rows":"两期之外记录数",
                  "period_a_rows":"前期记录数", "period_b_rows":"后期记录数"}
        return heading + "\n\n" + _table(["日期范围审计", "记录数"], [[labels.get(k, k), v] for k, v in value.items()])
    if output != "comparison":
        return None
    dimensions = params["comparison_dimensions"]
    grouped = isinstance(value, list)
    entries = value if grouped else [{"dimension_values":{}, **value}]
    parts = [heading, "变化率分母为前期值的绝对值；零分母或不可计算的量显示未知。"]
    for metric in product["metrics"]:
        items = [(row.get("dimension_values", {}), row[metric]) for row in entries if metric in row]
        if not items:
            continue
        a, b = ("a", "b") if grouped else ("period_a", "period_b")
        is_sum = all(item["aggregation"]["operator"] == "sum" for _, item in items)
        columns = list(dimensions) + (["前期合计", "后期合计"] if is_sum else ["前期值", "后期值"]) + ["差值", "变化率", "前期有效数", "后期有效数"]
        daily = any("daily_avg_a" in item for _, item in items)
        if daily:
            columns += ["前期日均", "后期日均", "日均差值", "日均变化率"]
        rows, audit_rows, operand_rows, notes = [], [], [], []
        for groups, item in items:
            group = [groups.get(d) for d in dimensions]
            exact = item["exact_aggregates"]
            pct = lambda v: "未知" if v is None else str(v) + "%"
            observation = item["observation"]
            row = group + [exact.get(a), exact.get(b), exact.get("diff"), pct(item.get("change_pct")), observation[a].get("effective_rows"), observation[b].get("effective_rows")]
            if daily:
                row += [item.get("daily_avg_a"), item.get("daily_avg_b"), item.get("daily_avg_diff"), pct(item.get("daily_avg_change_pct"))]
            rows.append(row)
            for key, label in ((a, "前期"), (b, "后期")):
                audit = observation[key]
                audits = [("指标", audit)] if "operands" not in audit else [("共同有效范围", audit)] + [(name, sub) for name, sub in audit["operands"].items()]
                for name, sub in audits:
                    audit_rows.append(group + [label, name] + [sub.get(k) for k in ("source_rows", "effective_rows", "excluded_rows", "missing_value", "nonfinite_value")])
                sums = item["aggregation"].get("operand_sums", {}).get(key)
                if sums is not None:
                    operand_rows.append(group + [label, sums.get("numerator"), sums.get("denominator")])
            notes.extend(item.get("completion_gaps", []))
            if item.get("percentage_limitation"):
                notes.append(item["percentage_limitation"])
        parts += [_cell(metric) + ("（求和）" if is_sum else "（窗口比率）"), _table(columns, rows),
                  _table(list(dimensions) + ["时段", "观测范围", "原始数", "有效数", "排除数", "缺失数", "非有限数"], audit_rows)]
        if operand_rows:
            formula = params["comparison_formulas"][metric]
            parts += ["窗口比率：" + _cell(formula["numerator"]) + " 合计 ÷ " + _cell(formula["denominator"]) + " 合计；不累计逐行比率。",
                      _table(list(dimensions) + ["时段", "分子合计", "分母合计"], operand_rows)]
        parts.extend(_cell(note) for note in dict.fromkeys(notes))
    return "\n\n".join(parts)


def _declared_curve_number(value, scale):
    multiplier=100 if scale=="fraction" else 1
    shown=format(Decimal(str(value))*multiplier,"f")
    if "." in shown:shown=shown.rstrip("0").rstrip(".")
    return shown+"%（原值 "+str(value)+"）"


def _shown_claim_value(claim, *, for_table=False):
    source_unit = claim.get("target", {}).get("source_unit_proof", {})
    literal_unit = source_unit.get("render_as_source_label", False)
    label = (lambda value: str(value)) if for_table else _cell
    value, unit = claim["value"], claim["unit"]
    if value is None:
        shown = "未知"
    elif literal_unit:
        shown = label(value)
    elif type(value) in {int,float} and unit == "proportion":
        shown = format(Decimal(str(value))*100,"f")
        if "." in shown:
            shown = shown.rstrip("0").rstrip(".")
        shown += "%"
    elif unit == "hypothesis_status":
        shown = {"supported":"受当前结构化测量支持","refuted":"被当前结构化测量反驳","contested":"支持与反证冲突未决"}[value]
    elif unit == "percent":
        shown = str(value) + "%" if value is not None else "未知"
    elif isinstance(value,str):
        shown = value
    else:
        shown = encode(value)
    catalog=claim.get("target",{}).get("tool")=="list_data" and claim["scope"]["dataset"] is None
    if catalog and not value:
        shown="该授权可见范围内为空（0个对象）" if isinstance(value,dict) else "该授权可见范围内无变换记录（0条）"
    file=claim.get("target",{}).get("tool") in {"read_file","list_files"} and claim["scope"]["dataset"] is None
    if file and not value:shown="该页文件原文为空（0字符）" if isinstance(value,str) else "该次授权文件枚举为空（0条）；不代表不可见范围为空"
    skills=claim.get("target",{}).get("tool")=="list_skills" and claim["scope"]["dataset"] is None
    if skills and not value:shown="当前宿主Skills目录为空（0项）；加载状态仅属于本会话"
    mcp=claim.get("target",{}).get("tool")=="list_mcp_servers" and claim["scope"]["dataset"] is None
    if mcp and isinstance(value,list) and not value:shown="当前全局MCP配置为空（0项）"
    if mcp and isinstance(value,dict) and value.get("availability")=="unavailable":shown="当前进程无可用MCP管理器；连接状态未知"
    if unit is None and source_unit:
        shown += "（核定源单位：" + label(source_unit["units"][0]) + "）"
    elif unit is None and not (catalog or file or skills or mcp):
        shown += "（单位未知）"
    elif unit is not None and (literal_unit or unit not in {"proportion", "percent", "hypothesis_status"}):
        shown += " " + (label(unit) if literal_unit else unit)
    return shown


_CURVE_LABELS = {
    "x": "x（原值）", "y": "观测值（原值）", "n_observed": "有效观测数",
    "n_excluded_zeros": "排除零值数", "n_excluded_invalid": "排除无效值数",
    "n_excluded_immature": "排除未成熟数", "weight_sum": "权重合计",
    "family": "模型族", "formula": "拟合公式", "r_squared": "R²",
    "sse": "残差平方和", "mean_residual": "平均残差", "max_abs_residual": "最大绝对残差",
    "value": "情景值（原值）", "status": "状态", "validation": "验证状态",
    "observed_x_range": "观测x范围", "parameters": "参数",
}


def _structured_tables(value, *, labels=None, fit_vectors=False):
    """Render every field of an already verified curve product; no row cap."""
    labels = labels or {}
    if isinstance(value, dict):
        if value and all(isinstance(row, dict) and row for row in value.values()):
            columns = list(next(iter(value.values())))
            if all(set(row) == set(columns) and all(not isinstance(cell, (dict, list)) for cell in row.values()) for row in value.values()):
                return _table(["条目"] + columns, [[key] + [row[column] for column in columns] for key, row in value.items()])
        scalars = [(k, v) for k, v in value.items() if not isinstance(v, (dict, list))]
        parts = [_table(["字段", "原值"], [[labels.get(k, k), v] for k, v in scalars])] if scalars else []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                parts += [_cell(labels.get(key, key)), _structured_tables(item, labels=labels, fit_vectors=fit_vectors)]
        return "\n\n".join(parts) or "该结果为空。"
    if not isinstance(value, list):
        return _cell(value)
    if not value:
        return "该结果为空（0项）。"
    if all(isinstance(row, dict) for row in value):
        keys = list(dict.fromkeys(k for row in value for k in row))
        columns = [k for k in keys if all(not isinstance(row.get(k), (dict, list)) for row in value)]
        parts = [_table([labels.get(k, k) for k in columns], [[row[k] if k in row else "未提供" for k in columns] for row in value])] if columns else []
        for number, row in enumerate(value, 1):
            nested = {k: v for k, v in row.items() if k not in columns}
            if not nested:
                continue
            parts.append("第 " + str(number) + " 项" + ("（" + _cell(row["family"]) + "）" if "family" in row else ""))
            paired = {k: nested.pop(k) for k in ("predicted", "residuals") if isinstance(nested.get(k), list)} if fit_vectors else {}
            if paired:
                keys = list(paired)
                parts.append(_table(["点序"] + [{"predicted": "拟合值", "residuals": "残差"}[k] for k in keys],
                                    [[i + 1] + [paired[k][i] if i < len(paired[k]) else "未提供" for k in keys] for i in range(max(map(len, paired.values()), default=0))]))
            for key, item in nested.items():
                parts += [_cell(labels.get(key, key)), _structured_tables(item, labels=labels, fit_vectors=fit_vectors)]
        return "\n\n".join(parts)
    if all(not isinstance(item, (dict, list)) for item in value):
        return _table(["序号", "原值"], [[i, v] for i, v in enumerate(value, 1)])
    return "\n\n".join("第 " + str(i) + " 项\n\n" + _structured_tables(item, labels=labels, fit_vectors=fit_vectors) for i, item in enumerate(value, 1))


def _scope_caption(claim, context):
    scope = claim["scope"]
    details = [scope["dataset"], scope["population"], scope["grain"]]
    time_scope = scope["time_scope"]
    if claim.get("target", {}).get("tool") == "compare_periods":
        time_scope = _period_heading(claim, context, dates_only=True) or time_scope
    elif claim.get("target", {}).get("tool") == "curve_fitting":
        try:
            structured = json.loads(time_scope)
        except (ValueError, TypeError):
            structured = None
        if isinstance(structured, dict) and set(structured) == {"parameters"}:
            time_scope = ""
            details.append("计算参数见下表")
            parameters = _structured_tables(structured["parameters"])
        else:
            parameters = ""
    else:
        parameters = ""
    if claim.get("target", {}).get("tool") != "curve_fitting":
        parameters = ""
    return "来源与口径：" + "；".join(_cell(v) for v in details + [time_scope] if v) + ("\n\n" + parameters if parameters else "")


def _curve_product_table(claim, context):
    if claim.get("target", {}).get("tool") != "curve_fitting":
        return None
    path = claim["basis_refs"][0]["result_path"]
    if path not in (["points"], ["fits"], ["scenarios"]) or not isinstance(claim["value"], list):
        return None
    value = claim["value"]
    title = {"points": "实际观测", "fits": "拟合模型与误差", "scenarios": "未验证参数情景（未来真实值未知）"}[path[0]]
    display = claim.get("target", {}).get("curve_display", {})
    scale = display.get("value_scale") if display.get("basis") == "plan_declaration" else None
    if path == ["points"] and scale in {"fraction", "percentage_points"}:
        value = [{**row, "y": _declared_curve_number(row["y"], scale)} for row in value]
    unit = "单位未知" if claim["unit"] is None else _cell(claim["unit"])
    return "\n\n".join([title, _structured_tables(value, labels=_CURVE_LABELS, fit_vectors=path == ["fits"]), _scope_caption(claim, context), unit,
                            "；".join(_cell(v) for v in dict.fromkeys(claim["limitations"]))])


def _scalar_group_key(claim, requirement_ids):
    target = claim.get("target", {})
    tool = target.get("tool")
    if tool not in {"compare_periods", "curve_fitting"} or type(claim["value"]) not in {int, float, type(None)}:
        return None
    proofs = [{k: v for k, v in basis.items() if k != "result_path"} for basis in claim["basis_refs"]]
    if not proofs:
        return None
    return encode([tool, proofs, claim["scope"], claim["limitations"], sorted(requirement_ids),
                   {k: target.get(k) for k in ("curve_display", "source_unit_proof", "source_unit_proofs")}])


def claim_text(claim, *, context=()):
    curve_table = _curve_product_table(claim, context)
    if curve_table is not None:
        return curve_table
    target=claim.get("target",{})
    source_unit=target.get("source_unit_proof",{})
    literal_unit=source_unit.get("render_as_source_label",False)
    display=target.get("curve_display",{})
    scale=display.get("value_scale") if display.get("basis")=="plan_declaration" else None
    path=claim["basis_refs"][0]["result_path"]
    if target.get("tool")=="curve_fitting" and path==["sensitivity"]:
        value=claim["value"]
        return _table(["日龄","普通均值（原值）","人数加权均值（原值）","绝对差（原值）"],[[p[k] for k in ("x","ordinary_mean","weighted_mean","absolute_difference")] for p in value["points"]])+"\n\n最大绝对口径敏感性差："+_cell(value["max_absolute_difference"])+"；对应日龄："+_cell(value["max_difference_x"])+"。\n\n"+"；".join(_cell(x) for x in claim["limitations"])
    if target.get("tool")=="curve_fitting" and len(path)==3 and path[0]=="points" and path[-1]=="y" and scale in {"fraction","percentage_points"}:
        return _cell(claim["label"])+"："+_cell(_declared_curve_number(claim["value"],scale))+"；"+"；".join(_cell(x) for x in claim["limitations"])
    table = _business_table(claim, context)
    if table is not None:
        details = [claim["scope"]["dataset"], claim["scope"]["population"], "单位未知" if claim["unit"] is None else claim["unit"]] + claim["limitations"]
        if source_unit:details.append("核定源单位："+source_unit["units"][0])
        multiple=target.get("source_unit_proofs")
        if multiple:
            metrics=target["business_product"]["metrics"]
            details.append("逐指标源单位："+"；".join(metric+"→"+multiple[metric]["units"][0] if metric in multiple else metric+"→未知（未声明）" for metric in metrics))
        return table + "\n\n" + "；".join(_cell(v) for v in details if v)
    if claim["scope"]["dataset"] is not None and isinstance(claim["value"], (dict, list)):
        proof = target.get("source_unit_proof", {})
        unit = ("核定源单位：" + _cell(proof["units"][0]) if proof else "单位未知" if claim["unit"] is None else _cell(claim["unit"]))
        return "\n\n".join([_cell(claim["label"]), _structured_tables(claim["value"]),
                                _scope_caption(claim, context), unit,
                                "；".join(_cell(v) for v in dict.fromkeys(claim["limitations"]))])
    shown = _shown_claim_value(claim)
    file = target.get("tool") in {"read_file", "list_files"} and claim["scope"]["dataset"] is None
    scope = claim["scope"]
    time_scope = scope["time_scope"]
    if time_scope and claim.get("target", {}).get("tool") == "compare_periods":
        # Render the existing verified host window, never parse answer prose or
        # rewrite an AcceptedAnswer that was already stored.
        time_scope = _period_heading(claim, context, dates_only=True) or time_scope
    details = ([scope["dataset"]] if scope["dataset"] is not None else ["文件范围" if file else "目录元数据"]) + [str(v) for v in (scope["population"], time_scope, scope["grain"]) if v]
    if claim["limitations"]:
        details.extend(claim["limitations"])
    return claim["label"] + "：" + shown + "；" + "；".join(details)


def artifact_text(artifact):
    label = artifact["description"].replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    reference=artifact["path"].replace("\\", "/")
    if not reference.startswith("sessions/"): reference="sessions/"+artifact["session_id"]+"/"+reference
    path = "/api/files/" + quote(reference, safe="/")
    return "[" + label + "](" + path + ")"


def effect_text(effect):
    obj=effect["object"];identity=obj["identity"]
    if effect["action"]=="export_conversation":
        if effect["arguments"].get("reply_target")=="current_answer":
            artifact={"description":"下载"+effect["details"]["format"].upper()+"当前报告","path":obj["name"],"session_id":effect["session_id"]}
            return "当前报告已导出："+artifact_text(artifact)+"；精确原回复 "+effect["details"]["source_reply"]["reply_id"]+"；原正文及保存时交付状态未改写。"
        label="下载"+effect["details"]["format"].upper()+"会话文件"
        artifact={"description":label,"path":obj["name"],"session_id":effect["session_id"]}
        result=("会话导出部分完成：" if effect.get("completion_gap") else "会话已导出：")+artifact_text(artifact)
        if effect.get("completion_gap"):result+="；"+effect["completion_gap"]["reason"]
        return result+"；范围为调用前已保存的公开会话快照；导出不验证正文中的数据结论。"
    shown=identity.get("version_id") if obj["kind"]=="dataset" else identity.get("sha256") if obj["kind"] in {"file","memory"} else encode({k:identity[k] for k in ("exists","enabled","loaded")})
    gap=effect.get("completion_gap")
    result=("操作部分完成：" if gap else "操作完成：")+effect["action"]+"；对象 "+obj["name"]+"；已核身份 "+str(shown)+"；参数 "+encode(effect["arguments"])+"；权限范围 "+effect["permission_scope"]
    if obj["kind"]=="memory" and effect.get("details",{}).get("changed") is False:result+="；已确认，状态未改变（幂等）"
    if effect.get("details"):result+="；实际处理 "+encode(effect["details"])
    if gap:result+="；"+gap["reason"]
    return result


class Renderer:
    def __init__(self):
        self._pieces = []
        self._length = 0
        self.trace = []
        self._pending_claims = []

    def add(self, value, *, part_id, kind, ref=None, requirement_ids=(), disposition="accepted", reason="",
            purpose=None, claim_refs=(), semantic_reviewed=False):
        self._flush_claims()
        start = end = None
        if value is not None:
            start = self._length + (2 if self._pieces else 0)
            end = start + len(value)
            self._pieces.append(value)
            self._length = end
        self.trace.append(dict(part_id=part_id,kind=kind,ref=ref,requirement_ids=list(requirement_ids),
            disposition=disposition,reason=reason,start=start,end=end,rendered_text=value))
        if purpose is not None:
            self.trace[-1].update(purpose=purpose, claim_refs=list(claim_refs), semantic_reviewed=semantic_reviewed)

    def add_claim(self, claim, *, context=(), part_id, ref, requirement_ids=()):
        key = _scalar_group_key(claim, requirement_ids)
        if key is None:
            self.add(claim_text(claim, context=context), part_id=part_id, kind="claim", ref=ref, requirement_ids=requirement_ids)
            return
        self._pending_claims.append((claim, context, part_id, ref, list(requirement_ids)))

    def _flush_claims(self):
        pending = self._pending_claims
        if not pending:
            return
        self._pending_claims = []
        groups = {}
        for entry in pending:
            groups.setdefault(_scalar_group_key(entry[0], entry[4]), []).append(entry)
        for group in groups.values():
            self._flush_claim_group(group)

    def _flush_claim_group(self, pending):
        if len(pending) == 1:
            claim, context, pid, ref, rids = pending[0]
            self.add(claim_text(claim, context=context), part_id=pid, kind="claim", ref=ref, requirement_ids=rids)
            return
        first, context = pending[0][:2]
        rows = []
        for claim, _, _, _, _ in pending:
            display = claim.get("target", {}).get("curve_display", {})
            scale = display.get("value_scale") if display.get("basis") == "plan_declaration" else None
            path = claim["basis_refs"][0]["result_path"]
            shown = (_declared_curve_number(claim["value"], scale) if claim["value"] is not None and
                     claim.get("target", {}).get("tool") == "curve_fitting" and len(path) == 3 and path[0] == "points" and path[-1] == "y" and scale in {"fraction", "percentage_points"}
                     else _shown_claim_value(claim, for_table=True))
            rows.append([claim["label"], shown])
        value = "\n\n".join([_scope_caption(first, context), _table(["指标", "已核值与单位"], rows),
                                "；".join(_cell(v) for v in dict.fromkeys(first["limitations"]))])
        start = self._length + (2 if self._pieces else 0)
        end = start + len(value)
        self._pieces.append(value)
        self._length = end
        # Every original claim keeps its own ID/owners and points to the exact
        # shared visible block, including its necessary local limitations.
        for _, _, pid, ref, rids in pending:
            self.trace.append(dict(part_id=pid, kind="claim", ref=ref, requirement_ids=rids,
                                   disposition="accepted", reason="", start=start, end=end, rendered_text=value))

    @property
    def body(self):
        self._flush_claims()
        return "\n\n".join(self._pieces)
