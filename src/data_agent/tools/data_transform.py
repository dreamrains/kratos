"""数据变换工具：merge、pivot、filter、select、rename、group_aggregate、resample、sort。"""

from __future__ import annotations

import json

import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import registry


@registry.register(
    name="transform_data",
    description=(
        "对数据集执行变换操作。operation 可选: "
        "merge（合并两个数据集，params: other_name, on/left_on/right_on, how=inner），"
        "pivot（宽转长: params: id_vars, value_vars / 长转宽: params: index, columns, values），"
        "filter（筛选行: params: condition，pandas query 语法），"
        "select（选择列: params: columns 逗号分隔或列表），"
        "rename（重命名列: params: mapping，格式 old:new,old2:new2 或 dict），"
        "group_aggregate（分组聚合: params: group_by, agg（dict 格式，如 {\"col1\": [\"sum\", \"mean\"], \"col2\": [\"count\"]}），"
        "或兼容旧格式 agg_func + agg_col），"
        "resample（时间重采样: params: date_col, freq（W/M/Q/Y）, agg（dict 格式，如 {\"col1\": \"sum\", \"col2\": \"mean\"}）），"
        "sort（排序: params: by, ascending=true/false）。"
        "save_as 指定保存为新数据集名称，为空则覆盖原数据集。"
    ),
)
def transform_data(
    name: str,
    operation: str,
    params: str = "",
    save_as: str = "",
) -> str:
    df = workspace.get(name)
    if df is None:
        available = list(workspace.list_datasets().keys())
        return json.dumps({"error": f"数据集 '{name}' 不存在。可用: {available}"}, ensure_ascii=False)

    try:
        p = json.loads(params) if params else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "params 必须是有效的 JSON"}, ensure_ascii=False)

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

    target_name = save_as or name
    workspace.add(target_name, result)
    # 记录变换血缘
    workspace.log_transform(name, operation, target_name, json.dumps({k: v for k, v in p.items() if k in ("group_by", "freq", "date_col", "condition", "agg")}, ensure_ascii=False) if p else "")
    return json.dumps({
        "dataset": target_name,
        "operation": operation,
        "rows": len(result),
        "columns": list(result.columns),
    }, ensure_ascii=False, indent=2)
