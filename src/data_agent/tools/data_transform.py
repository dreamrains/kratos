"""数据变换工具：merge、pivot、filter、select、rename、group_aggregate、resample、sort。"""

from __future__ import annotations

import json

import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import validate_pandas_expr
from data_agent.tools.registry import registry


def _sum_preserving_missing(series):
    if pd.api.types.is_integer_dtype(series.dtype):
        observed = series.dropna()
        return sum(int(value) for value in observed) if not observed.empty else None
    return series.sum(min_count=1)


def _resample_input(frame, date_col):
    """The original date coercion, with actual exclusion counts."""
    ts_frame=frame.copy()
    missing=int(ts_frame[date_col].isna().sum())
    if not pd.api.types.is_datetime64_any_dtype(ts_frame[date_col]):
        ts_frame[date_col]=pd.to_datetime(ts_frame[date_col],errors="coerce")
    excluded=int(ts_frame[date_col].isna().sum())
    audit={"source_rows":len(frame),"effective_rows":len(frame)-excluded,"excluded_rows":excluded,
        "missing_date_rows":missing,"invalid_date_rows":excluded-missing}
    return ts_frame.dropna(subset=[date_col]).set_index(date_col),audit


def _transform_parameters(arguments):
    """One interpretation for public structured fields and legacy JSON."""
    raw=arguments.get("params") or ""
    try:p=json.loads(raw) if raw else {}
    except (TypeError,json.JSONDecodeError) as exc:raise ValueError("params 必须是 JSON 对象") from exc
    if not isinstance(p,dict):raise ValueError("params 必须是 JSON 对象")
    fields={"condition":"condition","columns":"columns","rename_mapping":"mapping","sort_by":"by",
        "ascending":"ascending","group_by":"group_by","date_col":"date_col","freq":"freq",
        "resample_agg":"agg","other_name":"other_name","merge_on":"on","merge_how":"how",
        "pivot_index":"index","pivot_columns":"columns","pivot_values":"values",
        "melt_id_vars":"id_vars","melt_value_vars":"value_vars"}
    for source,target in fields.items():
        if arguments.get(source) is not None:p[target]=arguments[source]
    aggregations=arguments.get("aggregations")
    if aggregations is not None:
        p["agg"]={item["column"]:item["functions"] for item in aggregations}
    return p


def _transform_sources(arguments):
    names=[arguments["name"]]
    if arguments.get("operation")=="merge":names.append(_transform_parameters(arguments).get("other_name",""))
    return list(dict.fromkeys(names))


@registry.register(
    name="transform_data",
    capability={"capability_id":"data.transform_data","category":"data_transform"},
    output_contract={"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","effect_adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation","measurement","table"]},
    description=(
        "对数据集执行变换操作。"
        "使用场景：数据预处理（筛选/排序/重命名）、多维聚合、时间重采样、数据合并。"
        "不适用场景：列类型转换（用 apply_type_conversion）、数据清洗（用 clean_data）。"
        "参数说明：根据 operation 选择对应参数即可，无需所有参数都填写。"
        "也可通过 params 传入 JSON 兼容旧格式。"
        "常见错误：列名拼写错误、filter 条件语法错误（需 pandas query 语法）。"
    ),
    recovery_hint=(
        "数据变换失败。常见原因："
        "列名不存在（用 preview_data 查看列名）、"
        "数据类型不匹配（用 describe_dataset 检查类型）、"
        "聚合函数名拼写错误（支持 sum/mean/count/size/nunique/min/max/median/std）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "数据集名称"},
            "operation": {
                "type": "string",
                "description": "操作类型；宽转长使用 operation=pivot 并填写 melt_id_vars/melt_value_vars；melt 不是独立 operation。",
                "enum": ["filter", "select", "rename", "sort", "group_aggregate", "resample", "pivot", "merge"],
            },
            "save_as": {"type": "string", "description": "保存为新数据集名称，为空则自动生成"},
            "params": {"type": "string", "description": "[兼容] JSON 格式参数，优先级低于结构化参数"},
            # filter 参数
            "condition": {"type": "string", "description": "筛选条件（pandas query 语法，如 revenue > 100）"},
            # select 参数
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要选择的列名列表",
            },
            # rename 参数
            "rename_mapping": {
                "type": "object",
                "description": "重命名映射 {旧列名: 新列名}",
                "additionalProperties": {"type": "string"},
            },
            # sort 参数
            "sort_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "排序列名",
            },
            "ascending": {"type": "boolean", "description": "升序/降序（默认 true）"},
            # group_aggregate 参数
            "group_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "分组列名",
            },
            "aggregations": {
                "type": "array",
                "description": "聚合规则列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string", "description": "聚合目标列"},
                        "functions": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["sum", "mean", "count", "size", "nunique", "min", "max", "median", "std"]},
                            "description": "count 是非缺失记录数；size 是总记录数；nunique 是非缺失唯一值数。sum 的全缺失分组保留缺失而非零。",
                        },
                    },
                    "required": ["column", "functions"],
                },
            },
            # resample 参数
            "date_col": {"type": "string", "description": "时间列名（resample 使用）"},
            "freq": {
                "type": "string",
                "description": "重采样频率",
                "enum": ["D", "W", "ME", "QE", "YE"],
            },
            "resample_agg": {
                "type": "object",
                "description": "重采样聚合 {列名: 聚合函数}",
                "additionalProperties": {"type": "string"},
            },
            # merge 参数
            "other_name": {"type": "string", "description": "要合并的第二个数据集名称"},
            "merge_on": {"type": "string", "description": "合并键列名"},
            "merge_how": {
                "type": "string",
                "description": "合并方式",
                "enum": ["inner", "left", "right", "outer"],
            },
            # pivot 参数
            "pivot_index": {"type": "string", "description": "pivot 索引列"},
            "pivot_columns": {"type": "string", "description": "pivot 列名字段"},
            "pivot_values": {"type": "string", "description": "pivot 值字段"},
            "melt_id_vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "melt 操作的 ID 变量列",
            },
            "melt_value_vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "melt 操作的值变量列",
            },
        },
        "required": ["name", "operation"],
    },
)
def transform_data(
    name: str,
    operation: str,
    params: str = "",
    save_as: str = "",
    # 结构化参数（由 Schema 层传递，函数内合并到 params dict）
    condition: str | None = None,
    columns: list | str | None = None,
    rename_mapping: dict | str | None = None,
    sort_by: list | str | None = None,
    ascending: bool | None = None,
    group_by: list | str | None = None,
    aggregations: list | None = None,
    date_col: str | None = None,
    freq: str | None = None,
    resample_agg: dict | str | None = None,
    other_name: str | None = None,
    merge_on: str | None = None,
    merge_how: str | None = None,
    pivot_index: str | None = None,
    pivot_columns: str | None = None,
    pivot_values: str | None = None,
    melt_id_vars: list | str | None = None,
    melt_value_vars: list | str | None = None,
) -> str:
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)

    # 当 save_as 未指定时，自动生成名称（不覆盖源数据集）
    target_name = save_as
    if not target_name:
        _op_suffix = {
            "filter": "filtered", "select": "selected", "sort": "sorted",
            "rename": "renamed", "group_aggregate": "grouped",
            "resample": "resampled", "pivot": "pivoted", "merge": "merged",
        }
        suffix = _op_suffix.get(operation, operation)
        target_name = workspace.next_analysis_name(name, suffix)

    try:
        p=_transform_parameters(locals())
    except (ValueError,KeyError,TypeError) as exc:
        return json.dumps({"error":str(exc),"error_type":"invalid_parameter"},ensure_ascii=False)

    try:
        if operation == "merge":
            other_name = p.get("other_name", "")
            other_df = workspace.get(other_name)
            if other_df is None:
                return json.dumps({"error": f"数据集 '{other_name}' 不存在"}, ensure_ascii=False)
            on = p.get("on")
            left_on = p.get("left_on")
            right_on = p.get("right_on")
            how = p.get("how", "inner")
            result = pd.merge(df, other_df, on=on, left_on=left_on, right_on=right_on, how=how)

        elif operation == "pivot":
            # 判断是 melt 还是 pivot
            if "id_vars" in p:
                result = df.melt(
                    id_vars=p["id_vars"] if isinstance(p["id_vars"], list) else [p["id_vars"]],
                    value_vars=p.get("value_vars"),
                    var_name=p.get("var_name", "variable"),
                    value_name=p.get("value_name", "value"),
                )
            else:
                result = df.pivot(
                    index=p.get("index"),
                    columns=p.get("columns"),
                    values=p.get("values"),
                ).reset_index()
                # Datetime pivot values become Timestamp column labels, which
                # cannot cross the workspace/receipt JSON boundary. Column
                # names are schema identifiers here, so normalize all labels.
                result.columns = [str(column) for column in result.columns]

        elif operation == "filter":
            condition = p.get("condition", "")
            if not condition:
                return json.dumps({"error": "filter 需要 condition 参数"}, ensure_ascii=False)
            err = validate_pandas_expr(condition)
            if err:
                return json.dumps({"error": f"条件不安全 — {err}"}, ensure_ascii=False)
            result = df.query(condition)

        elif operation == "select":
            columns = p.get("columns", "")
            if isinstance(columns, str):
                columns = [c.strip() for c in columns.split(",") if c.strip()]
            missing = [c for c in columns if c not in df.columns]
            if missing:
                return json.dumps({"error": f"列不存在: {missing}"}, ensure_ascii=False)
            result = df[columns]

        elif operation == "rename":
            mapping = p.get("mapping", "")
            if isinstance(mapping, str):
                rename_map = {}
                for pair in mapping.split(","):
                    if ":" in pair:
                        old, new = pair.split(":", 1)
                        rename_map[old.strip()] = new.strip()
            else:
                rename_map = mapping
            result = df.rename(columns=rename_map)

        elif operation == "group_aggregate":
            group_by = p.get("group_by", "")
            if isinstance(group_by, str):
                group_by = [g.strip() for g in group_by.split(",") if g.strip()]

            # 新格式: agg 为 dict（多列多函数）
            agg_spec = p.get("agg")
            if agg_spec and isinstance(agg_spec, dict):
                # agg 格式: {"col1": ["sum", "mean"], "col2": ["count"]}
                # 或 {"col1": "sum"}
                agg_dict = {}
                for col, funcs in agg_spec.items():
                    if isinstance(funcs, str):
                        agg_dict[col] = funcs
                    elif isinstance(funcs, list):
                        agg_dict[col] = funcs
                    else:
                        agg_dict[col] = funcs
                for col, funcs in agg_dict.items():
                    if isinstance(funcs, str):
                        agg_dict[col] = _sum_preserving_missing if funcs == "sum" else funcs
                    elif isinstance(funcs, list):
                        agg_dict[col] = [_sum_preserving_missing if f == "sum" else f for f in funcs]
                result = df.groupby(group_by, dropna=False).agg(agg_dict).reset_index()
                # 扁平化多级列名
                if isinstance(result.columns, pd.MultiIndex):
                    result.columns = [
                        f"{col}_{'sum' if func == '_sum_preserving_missing' else func}" if func else col
                        for col, func in result.columns
                    ]
            else:
                # 兼容旧格式
                agg_func = p.get("agg_func", "count")
                agg_col = p.get("agg_col", "")
                if agg_func == "size":
                    result = df.groupby(group_by, dropna=False).size().reset_index(name="count")
                elif agg_func == "count":
                    if not agg_col:
                        return json.dumps({"error":"count 需要指定 agg_col 列；计算行数请使用 size", "error_type":"invalid_parameter"},ensure_ascii=False)
                    result = df.groupby(group_by, dropna=False)[agg_col].count().reset_index(name="count")
                elif agg_func == "sum":
                    result = df.groupby(group_by, dropna=False)[agg_col].sum(min_count=1).reset_index()
                elif agg_func == "mean":
                    result = df.groupby(group_by)[agg_col].mean().reset_index()
                elif agg_func == "min":
                    result = df.groupby(group_by)[agg_col].min().reset_index()
                elif agg_func == "max":
                    result = df.groupby(group_by)[agg_col].max().reset_index()
                else:
                    return json.dumps({"error": f"不支持的聚合函数: {agg_func}"}, ensure_ascii=False)

        elif operation == "resample":
            date_col = p.get("date_col", "")
            freq = p.get("freq", "W")
            agg_spec = p.get("agg", {})

            if not date_col:
                return json.dumps({"error": "resample 需要 date_col 参数"}, ensure_ascii=False)
            if date_col not in df.columns:
                return json.dumps({"error": f"列 '{date_col}' 不存在"}, ensure_ascii=False)

            ts_df,resample_audit = _resample_input(df,date_col)

            # pandas >=2.2 deprecates 'M'/'Y' in favor of 'ME'/'YE'
            _freq_map = {"M": "ME", "Y": "YE", "Q": "QE"}
            freq = _freq_map.get(freq, freq)


            if not agg_spec:
                # 默认对所有数值列求和
                agg_spec = {}
                for col in ts_df.select_dtypes(include="number").columns:
                    agg_spec[col] = "sum"

            agg_spec={col:([_sum_preserving_missing if f=="sum" else f for f in funcs]
                if isinstance(funcs,list) else _sum_preserving_missing if funcs=="sum" else funcs)
                for col,funcs in agg_spec.items()}
            resampled = ts_df.resample(freq).agg(agg_spec)
            result = resampled.reset_index()

            # 扁平化多级列名
            if isinstance(result.columns, pd.MultiIndex):
                result.columns = [
                    f"{col}_{'sum' if func == '_sum_preserving_missing' else func}" if func else col
                    for col, func in result.columns
                ]

        elif operation == "sort":
            by = p.get("by", "")
            ascending_raw = p.get("ascending", "true")
            ascending = str(ascending_raw).lower() == "true"
            if isinstance(by, str):
                by = [b.strip() for b in by.split(",") if b.strip()]
            result = df.sort_values(by=by, ascending=ascending)

        else:
            return json.dumps({"error": f"不支持的 operation: {operation}", "error_type": "invalid_parameter",
                               "allowed": ["filter", "select", "rename", "sort", "group_aggregate", "resample", "pivot", "merge"],
                               "hint": "宽转长请使用 operation=pivot、melt_id_vars 和 melt_value_vars，无需重新加载数据。"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"变换失败: {e}"}, ensure_ascii=False)

    expression = json.dumps(
        {k: v for k, v in p.items() if k in ("group_by", "freq", "date_col", "condition", "agg")},
        ensure_ascii=False,
    ) if p else ""
    sources=list(dict.fromkeys([name,other_name])) if operation=="merge" else [name]
    derive_result = (workspace.derive_multi(sources,target_name,result,expression=f"{operation}: {expression}")
        if operation=="merge" else workspace.derive(name,target_name,result,expression=f"{operation}: {expression}"))
    if derive_result.startswith("Error:"):
        return json.dumps({"error": derive_result}, ensure_ascii=False)
    from data_agent.tools.data_understand import _observed_date_scope
    return json.dumps({
        "dataset": target_name,
        "source_dataset": name,
        "source_datasets": sources,
        "parameters": p,
        **({"source_observation": {"rows": len(df), "observation_window": _observed_date_scope(df)}}
           if operation == "group_aggregate" else {}),
        "operation": operation,
        **({"resample_audit":resample_audit,"status":"partial" if resample_audit["excluded_rows"] else "complete"}
           if operation=="resample" else {}),
        "rows": len(result),
        "columns": list(result.columns),
        **({"measurement_records": json.loads(result.to_json(orient="records",date_format="iso",double_precision=15))}
           if operation in {"group_aggregate","resample","pivot"} else {}),
    }, ensure_ascii=False, indent=2)
