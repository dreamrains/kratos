"""数据变换工具：merge、pivot、filter、select、rename、group_aggregate、resample、sort。"""

from __future__ import annotations

import json

import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools._utils import validate_pandas_expr
from data_agent.tools.registry import registry


@registry.register(
    name="transform_data",
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
        "聚合函数名拼写错误（支持 sum/mean/count/min/max/median/std）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "数据集名称"},
            "operation": {
                "type": "string",
                "description": "操作类型",
                "enum": ["filter", "select", "rename", "sort", "group_aggregate", "resample", "pivot", "merge"],
            },
            "save_as": {"type": "string", "description": "保存为新数据集名称，为空则自动生成", "default": ""},
            "params": {"type": "string", "description": "[兼容] JSON 格式参数，优先级低于结构化参数", "default": ""},
            # filter 参数
            "condition": {"type": "string", "description": "筛选条件（pandas query 语法，如 revenue > 100）", "default": ""},
            # select 参数
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要选择的列名列表",
                "default": None,
                "nullable": True,
            },
            # rename 参数
            "rename_mapping": {
                "type": "object",
                "description": "重命名映射 {旧列名: 新列名}",
                "additionalProperties": {"type": "string"},
                "default": None,
                "nullable": True,
            },
            # sort 参数
            "sort_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "排序列名",
                "default": None,
                "nullable": True,
            },
            "ascending": {"type": "boolean", "description": "升序/降序（默认 true）", "default": True},
            # group_aggregate 参数
            "group_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "分组列名",
                "default": None,
                "nullable": True,
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
                            "items": {"type": "string", "enum": ["sum", "mean", "count", "min", "max", "median", "std"]},
                            "description": "聚合函数列表",
                        },
                    },
                    "required": ["column", "functions"],
                },
                "default": None,
                "nullable": True,
            },
            # resample 参数
            "date_col": {"type": "string", "description": "时间列名（resample 使用）", "default": ""},
            "freq": {
                "type": "string",
                "description": "重采样频率",
                "enum": ["", "D", "W", "ME", "QE", "YE"],
                "default": "",
            },
            "resample_agg": {
                "type": "object",
                "description": "重采样聚合 {列名: 聚合函数}",
                "additionalProperties": {"type": "string"},
                "default": None,
                "nullable": True,
            },
            # merge 参数
            "other_name": {"type": "string", "description": "要合并的第二个数据集名称", "default": ""},
            "merge_on": {"type": "string", "description": "合并键列名", "default": ""},
            "merge_how": {
                "type": "string",
                "description": "合并方式",
                "enum": ["inner", "left", "right", "outer"],
                "default": "inner",
            },
            # pivot 参数
            "pivot_index": {"type": "string", "description": "pivot 索引列", "default": ""},
            "pivot_columns": {"type": "string", "description": "pivot 列名字段", "default": ""},
            "pivot_values": {"type": "string", "description": "pivot 值字段", "default": ""},
            "melt_id_vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "melt 操作的 ID 变量列",
                "default": None,
                "nullable": True,
            },
            "melt_value_vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "melt 操作的值变量列",
                "default": None,
                "nullable": True,
            },
        },
        "required": ["name", "operation"],
        "additionalProperties": False,
    },
)
def transform_data(
    name: str,
    operation: str,
    params: str = "",
    save_as: str = "",
    # 结构化参数（由 Schema 层传递，函数内合并到 params dict）
    condition: str = "",
    columns: list | str | None = None,
    rename_mapping: dict | str | None = None,
    sort_by: list | str | None = None,
    ascending: bool = True,
    group_by: list | str | None = None,
    aggregations: list | None = None,
    date_col: str = "",
    freq: str = "",
    resample_agg: dict | str | None = None,
    other_name: str = "",
    merge_on: str = "",
    merge_how: str = "inner",
    pivot_index: str = "",
    pivot_columns: str = "",
    pivot_values: str = "",
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
        candidate = f"{name}_{suffix}"
        if candidate == name:
            candidate = f"{name}_{operation}_1"
        target_name = candidate

    # 合并结构化参数到 params dict
    try:
        p = json.loads(params) if params else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "params 必须是有效的 JSON"}, ensure_ascii=False)

    # 结构化参数 → params dict（结构化参数优先，覆盖 params 中的同名字段）
    if condition and "condition" not in p:
        p["condition"] = condition
    if columns is not None and "columns" not in p:
        p["columns"] = columns
    if rename_mapping is not None and "mapping" not in p:
        p["mapping"] = rename_mapping
    if sort_by is not None and "by" not in p:
        p["by"] = sort_by
    if not ascending and "ascending" not in p:
        p["ascending"] = ascending
    if group_by is not None and "group_by" not in p:
        p["group_by"] = group_by
    if aggregations is not None and "agg" not in p:
        # aggregations: [{"column": "x", "functions": ["sum", "mean"]}] → {"x": ["sum", "mean"]}
        p["agg"] = {a["column"]: a["functions"] for a in aggregations if "column" in a and "functions" in a}
    if date_col and "date_col" not in p:
        p["date_col"] = date_col
    if freq and "freq" not in p:
        p["freq"] = freq
    if resample_agg is not None and "agg" not in p:
        p["agg"] = resample_agg
    if other_name and "other_name" not in p:
        p["other_name"] = other_name
    if merge_on and "on" not in p:
        p["on"] = merge_on
    if merge_how != "inner" and "how" not in p:
        p["how"] = merge_how
    if pivot_index and "index" not in p:
        p["index"] = pivot_index
    if pivot_columns and "columns" not in p:
        p["columns"] = pivot_columns
    if pivot_values and "values" not in p:
        p["values"] = pivot_values
    if melt_id_vars is not None and "id_vars" not in p:
        p["id_vars"] = melt_id_vars
    if melt_value_vars is not None and "value_vars" not in p:
        p["value_vars"] = melt_value_vars

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
                result = df.groupby(group_by).agg(agg_dict).reset_index()
                # 扁平化多级列名
                if isinstance(result.columns, pd.MultiIndex):
                    result.columns = [
                        f"{col}_{func}" if func else col
                        for col, func in result.columns
                    ]
            else:
                # 兼容旧格式
                agg_func = p.get("agg_func", "count")
                agg_col = p.get("agg_col", "")
                if agg_func in ("count", "size"):
                    result = df.groupby(group_by).size().reset_index(name="count")
                elif agg_func == "sum":
                    result = df.groupby(group_by)[agg_col].sum().reset_index()
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

            # 确保日期列是 datetime 类型
            ts_df = df.copy()
            if not pd.api.types.is_datetime64_any_dtype(ts_df[date_col]):
                ts_df[date_col] = pd.to_datetime(ts_df[date_col], errors="coerce")

            # pandas >=2.2 deprecates 'M'/'Y' in favor of 'ME'/'YE'
            _freq_map = {"M": "ME", "Y": "YE", "Q": "QE"}
            freq = _freq_map.get(freq, freq)

            ts_df = ts_df.dropna(subset=[date_col]).set_index(date_col)

            if not agg_spec:
                # 默认对所有数值列求和
                agg_spec = {}
                for col in ts_df.select_dtypes(include="number").columns:
                    agg_spec[col] = "sum"

            resampled = ts_df.resample(freq).agg(agg_spec)
            result = resampled.reset_index()

            # 扁平化多级列名
            if isinstance(result.columns, pd.MultiIndex):
                result.columns = [
                    f"{col}_{func}" if func else col
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
            return json.dumps({"error": f"不支持的 operation: {operation}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"变换失败: {e}"}, ensure_ascii=False)

    add_result = workspace.add(target_name, result)
    if str(add_result).startswith("Error:"):
        scoped_storage_errors = {
            "Error: dataset_outside_current_task_scope",
            "Error: derived_scope_not_registered",
        }
        if operation == "group_aggregate" and str(add_result) in scoped_storage_errors:
            inline_limit = 50
            records = json.loads(
                result.head(inline_limit).to_json(
                    orient="records",
                    date_format="iso",
                    force_ascii=False,
                )
            )
            return json.dumps({
                "dataset": target_name,
                "operation": operation,
                "rows": len(result),
                "columns": list(result.columns),
                "records": records,
                "records_truncated": len(result) > inline_limit,
                "persisted": False,
                "storage_reason": "scoped_inline_result",
            }, ensure_ascii=False, indent=2)
        return json.dumps({"error": str(add_result)}, ensure_ascii=False)
    # 记录变换血缘
    workspace.log_transform(name, operation, target_name, json.dumps({k: v for k, v in p.items() if k in ("group_by", "freq", "date_col", "condition", "agg")}, ensure_ascii=False) if p else "")
    return json.dumps({
        "dataset": target_name,
        "operation": operation,
        "rows": len(result),
        "columns": list(result.columns),
    }, ensure_ascii=False, indent=2)
