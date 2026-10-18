"""Explicit, copy-on-write time alignment across existing workspace datasets."""
from __future__ import annotations

import math
import pandas as pd

from data_agent.session.workspace import workspace
from data_agent.tools.registry import ToolResult, registry


def _synthesis_parameters(arguments):
    names = [item.strip() for item in arguments['datasets'].split(',') if item.strip()]
    pairs = [item.strip() for item in arguments['metrics'].split(',') if item.strip()]
    if len(names) < 2 or len(set(names)) != len(names) or 'date' in names:
        raise ValueError('至少指定两个不重复的数据集；来源名称不能与输出日期列 date 冲突。')
    metric_map = {}
    for pair in pairs:
        if ':' not in pair:
            raise ValueError('metrics 必须使用 dataset:metric 格式。')
        dataset, metric = (part.strip() for part in pair.split(':', 1))
        if not dataset or not metric or dataset in metric_map:
            raise ValueError('每个来源必须且只能声明一个非空指标，不能重复或覆盖。')
        metric_map[dataset] = metric
    if set(names) != set(metric_map):
        raise ValueError('每个数据集必须指定一个 metric，不能遗漏或包含其他来源。')
    date_col = arguments['date_col']
    if not isinstance(date_col, str) or not date_col.strip():
        raise ValueError('date_col 必须为明确的日期列。')
    if arguments.get('save_as'):
        from data_agent.session.workspace import validate_dataset_alias
        validate_dataset_alias(arguments['save_as'])
    return names, metric_map


def _time_synthesis_result(frames, identities, arguments):
    """One original sum/outer-alignment owner, shared with host revalidation."""
    from pandas.api.types import is_integer_dtype
    names, metric_map = _synthesis_parameters(arguments)
    series, coverage, observation, timezones = [], {}, {}, set()
    for name in names:
        frame = frames.get(name)
        if frame is None:
            raise ValueError(f"数据集 '{name}' 不存在或不在当前任务范围。")
        date_col, metric = arguments['date_col'], metric_map[name]
        if list(frame.columns).count(date_col) != 1 or list(frame.columns).count(metric) != 1:
            raise ValueError(f"数据集 '{name}' 的日期或指标列缺失或重复。")
        dates = pd.to_datetime(frame[date_col], errors='coerce')
        try:
            timezone = str(dates.dt.tz) if dates.dt.tz is not None else None
        except AttributeError:
            raise ValueError('日期包含混合或无法确定的时区；请先明确同一业务时区。') from None
        timezones.add(timezone)
        if len(timezones) > 1:
            raise ValueError('各来源必须使用同一时区，不能混合有/无时区或不同业务时区。')
        numbers = pd.to_numeric(frame[metric], errors='coerce')
        finite = numbers.map(lambda value: not pd.isna(value) and math.isfinite(value))
        valid = dates.notna() & finite
        count = int(valid.sum())
        observation[name] = {
            'rows': int(len(frame)), 'effective_rows': count, 'excluded_rows': int((~valid).sum()),
            'missing_dates': int(frame[date_col].isna().sum()),
            'invalid_dates': int((frame[date_col].notna() & dates.isna()).sum()),
            'missing_values': int(frame[metric].isna().sum()),
            'nonnumeric_values': int((frame[metric].notna() & numbers.isna()).sum()),
            'nonfinite_values': int((numbers.notna() & ~finite).sum()),
            'reason_counts_may_overlap': True,
        }
        if not count:
            raise ValueError(f"数据集 '{name}' 没有可用的有限日期/数值观测。")
        working = pd.DataFrame({'date': dates.loc[valid].dt.normalize(), name: numbers.loc[valid]})
        # Integer addition must not wrap at int64; floating sums retain pandas' algorithm.
        if is_integer_dtype(working[name].dtype):
            working[name] = working[name].astype(object)
        daily = working.groupby('date', as_index=False)[name].sum(min_count=1).sort_values('date')
        if any(not math.isfinite(value) for value in daily[name]):
            raise ValueError(f"数据集 '{name}' 的日合计不可有限表达。")
        daily[name] = daily[name].astype(object)
        coverage[name] = {
            'metric': metric, 'rows': int(len(frame)), 'effective_rows': count,
            'start': daily['date'].min().isoformat(), 'end': daily['date'].max().isoformat(),
            'distinct_dates': int(len(daily)), 'timezone': timezone,
        }
        series.append(daily)
    aligned = series[0]
    for item in series[1:]:
        aligned = aligned.merge(item, on='date', how='outer', validate='one_to_one')
    aligned = aligned.sort_values('date').reset_index(drop=True)
    missing = {name: int(aligned[name].isna().sum()) for name in names}
    records = []
    for values in aligned.itertuples(index=False, name=None):
        row = {'date': values[0].isoformat()}
        for name, value in zip(names, values[1:]):
            row[name] = None if pd.isna(value) else value.item() if hasattr(value, 'item') else value
        records.append(row)
    # Keep the actual derived frame numeric as well as preserving exact values.
    # Object dtype is only needed for integer totals beyond pandas integer ranges.
    from numbers import Integral
    for name in names:
        observed = aligned[name].dropna().tolist()
        if all(isinstance(value, Integral) for value in observed):
            low, high = min(observed), max(observed)
            dtype = 'Int64' if -(2**63) <= low and high < 2**63 else 'UInt64' if low >= 0 and high < 2**64 else None
        else:
            dtype = 'Float64'
        if dtype is not None:
            aligned[name] = pd.array(aligned[name], dtype=dtype)
    gaps = [f"{name} 排除 {row['excluded_rows']} 条记录，原范围未完整覆盖。" for name, row in observation.items() if row['excluded_rows']]
    if any(missing.values()):
        gaps.append('来源在部分对齐日期没有有效观测；对应值未知，不补零。')
    result = {
        'method_contract': 'multi_file_time_synthesis.v1', 'status': 'partial' if gaps else 'supported',
        'date_col': arguments['date_col'], 'source_datasets': names,
        'source_identities': {name: identities[name] for name in names},
        'parameters': {'date_col': arguments['date_col'], 'metric_map': metric_map, 'grain': 'calendar_day', 'timezone': next(iter(timezones))},
        'coverage': coverage, 'observation': observation, 'aligned_rows': int(len(aligned)),
        'aligned_data': records, 'missing_aligned_dates': missing, 'completion_gaps': gaps,
        'limitations': ['按各来源同一明确时区的自然日求和并外对齐；无时区输入按其自然日。',
                        '仅对有限有效观测求和；排除原因可能重叠，联合排除数独立披露。',
                        '未观测值保持未知；真实观测零保留零；不推断业务 join、跨来源可加性或因果。'],
        'claim_ceiling': 'descriptive',
    }
    return aligned, result


@registry.register(
    name="synthesize_time_series",
    description="按共同明确时区的自然日求和并外对齐，完整返回各来源数值、有限有效范围和未知值；混合时区拒绝，save_as 可创建多父派生表，不推断业务 join。",
    schema_overrides={
        "datasets": {"description": "数据集名称，逗号分隔"},
        "date_col": {"description": "各数据集共有的日期列"},
        "metrics": {"description": "dataset:metric 逗号分隔，例如 banner:广告收入,iap:内购收入"},
        "save_as": {"description": "可选派生数据集名称；为空只返回对齐结果"},
    },
)
def synthesize_time_series(datasets: str, date_col: str = "日期", metrics: str = "", save_as: str = "") -> ToolResult:
    arguments = dict(datasets=datasets, date_col=date_col, metrics=metrics, save_as=save_as)
    try:
        names, metric_map = _synthesis_parameters(arguments)
        frames = {name: workspace.get(name) for name in names}
        identities = {name: workspace.get_data_identity(name) for name in names}
        aligned, result = _time_synthesis_result(frames, identities, arguments)
    except (ValueError, TypeError, OverflowError) as exc:
        return ToolResult(summary='Error: '+str(exc), data={'error': str(exc), 'error_type': 'invalid_synthesis_input'})
    if save_as:
        message = workspace.derive_multi(names, save_as, aligned, expression=f'date-aligned daily sums: {metric_map}')
        if message.startswith('Error:'):
            return ToolResult(summary=message, data={'error': message, 'error_type': 'synthesis_save_failed'})
        result.update(dataset=save_as, derived_dataset=save_as, derived_identity=workspace.get_data_identity(save_as))
    return ToolResult(summary='已按自然日汇总并外对齐；完整数值、有效范围和未知值已披露。', data=result)
