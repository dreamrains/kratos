"""Offline contracts for quality scope, chart rendering, and bounded export."""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from tests.test_artifact_publication_contracts import context


def test_quality_results_carry_observed_dates_not_collection_cutoff(context, monkeypatch):
    from data_agent.tools.data_understand import describe_dataset, detect_data_quality
    from data_agent.tools.evidence_statistics import bind_computed_statistics
    from data_agent.tools.analysis_flow import _mark_statistical_detail_status
    context.workspace.add('retention', pd.DataFrame({'date':pd.to_datetime(['2020-07-01','2020-08-31']), 'D30':[.02,0.]}))
    results = {'r1':json.loads(describe_dataset('retention')), 'r2':json.loads(detect_data_quality('retention'))}
    scope = results['r1']['observation_window']
    assert scope['columns']['date']['min'].startswith('2020-07-01')
    assert scope['columns']['date']['max'].startswith('2020-08-31')
    assert scope['collection_cutoff'] == 'unknown'
    assert results['r1']['field_statistics'][0]['datetime_range']['span_days'] == 61
    monkeypatch.setattr('data_agent.tools.result_reference.load_result_reference',
                        lambda ref: (results[ref.split('/')[-1].split('_')[0]], {'receipt_id':ref.split('/')[-1].split('_')[0]}))
    payload = {'time_scope':'invented collection date'}
    bind_computed_statistics(payload, [{'id':r, 'tool_call_id':r, 'tool_name':t, 'arguments':{'name':'retention'}, 'structured_result_sha256':'validated'}
                                     for r,t in [('r1','describe_dataset'),('r2','detect_data_quality')]])
    _mark_statistical_detail_status(payload)
    assert payload['time_scope'] == scope
    assert payload['statistical_detail_status'] == 'complete'
    assert payload['metrics']['detect_data_quality']['total_issues'] == 0
    assert payload['sample_size'] == 2


def test_date_like_strings_do_not_invent_a_time_window(context):
    from data_agent.tools.data_understand import describe_dataset
    context.workspace.add('text', pd.DataFrame({'label':['2020-01','unknown']}))
    assert not json.loads(describe_dataset('text')).get('observation_window')


def test_static_failure_is_receipted_once_and_exported_as_partial(context, monkeypatch):
    from data_agent.tools.visualization import _save_chart
    from data_agent.config import get_config
    from data_agent.tools.report import _validated_chart_entries
    attempts = []
    def fail(self, **kwargs):
        attempts.append(kwargs)
        raise RuntimeError('renderer unavailable at first attempt')
    monkeypatch.setattr(go.Figure, 'to_image', fail)
    result = _save_chart(go.Figure(go.Scatter(x=[1,2], y=[2,3])), 'diagnostic',
                         {'purpose':'exploratory','validation_status':'valid','title':'diagnostic'})
    root = get_config().sessions_resolved / context.session_id / 'charts'
    meta = json.loads(next(root.glob('*.json')).read_text('utf8'))
    assert meta['static_image']['status'] == 'failed'
    assert meta['static_image']['exception_type'] == 'RuntimeError'
    assert 'first attempt' in meta['static_image']['message']
    assert len(attempts) == 1 and '静态图不可用' in result
    assert not list(root.glob('*.png'))
    exported = _validated_chart_entries(context.session_id)
    assert len(exported) == 1 and '静态图不可用' in exported[0]['markdown']
    assert 'RuntimeError' in exported[0]['markdown']
    assert len(attempts) == 1  # Export is not a hidden rendering retry.


def test_fit_scope_preserves_unknown_zero_meaning_and_descriptive_ceiling():
    from data_agent.agent.publication_synthesis import publication_contract, validate_final_narrative
    scope = publication_contract('curve_fitting', {'points':[{'x':1},{'x':30}], 'claim_ceiling':'descriptive',
        'zero_value_semantics':'unknown', 'limitations':['排除零值不证明其为未观测。']})
    assert scope['zero_value_semantics'] == 'unknown'
    assert scope['claim_ceiling'] == 'descriptive'
    packet = {'publication_scope':[scope]}
    assert validate_final_narrative('优先优化早期，ROI最高。', packet)
    assert validate_final_narrative('无法判断优化ROI最高；需要干预成本及收益数据。', packet) is None
    assert validate_final_narrative('选择偏差轻微。', packet)
    assert validate_final_narrative('选择偏差大小未知。', packet) is None
    assert validate_final_narrative('第7天之后衰减趋缓，投入产出比递减。', packet)
    assert validate_final_narrative('30天点cohort构成与短时点不同，存在轻微选择偏差。', packet)
    for unsupported in (
        '这6个零值均为未观测值而非真实零。',
        '曲线说明产品已有稳定核心用户盘。',
        '该形态属于典型社交长线游戏。',
        '检测到的离群值属于自然波动。',
        '该曲线可用于后续LTV建模。',
    ):
        assert validate_final_narrative(unsupported, packet), unsupported
    for qualified in (
        '不能证明零值为未观测，真实含义未知。',
        '无法判断是否属于典型社交游戏。',
        '该拟合不支持留存预测或LTV建模。',
        '离群值的成因未知，不能认定为自然波动。',
    ):
        assert validate_final_narrative(qualified, packet) is None, qualified


def test_timestamp_chart_first_static_attempt_uses_canonical_figure(context):
    from data_agent.tools.visualization import _save_chart
    from data_agent.config import get_config
    from PIL import Image
    fig = go.Figure(go.Scatter(x=list(pd.date_range('2020-07-01', periods=3)), y=[1,2,3]))
    original = fig.to_json()
    _save_chart(fig, 'timestamp', {'purpose':'exploratory','validation_status':'valid','title':'timestamp'})
    root = get_config().sessions_resolved / context.session_id / 'charts'
    meta = json.loads(next(root.glob('*.json')).read_text('utf8'))
    assert meta['static_image']['status'] == 'completed', meta['static_image']
    assert meta['static_image']['attempts'] == 1
    assert meta['figure']['data'] == json.loads(original)['data']
    with Image.open(next(root.glob('*.png'))) as png:
        png.verify()
    # Only the publication annotation is added; the interactive figure must
    # not inherit the static renderer's fixed dimensions.
    assert fig.layout.width is None and fig.layout.height is None


def test_combined_bar_labels_keep_full_identity_and_use_bounded_ticks(context):
    from data_agent.config import get_config
    from data_agent.tools.visualization import create_chart

    frame = pd.DataFrame({
        'region': [f'超长区域名称-{index:02d}' for index in range(15)],
        'channel': [f'渠道名称-{index % 3}-特别长' for index in range(15)],
        'campaign': [f'活动批次-{index:02d}-长标签' for index in range(15)],
        'revenue': list(range(15)),
    })
    context.workspace.add('combinations', frame)
    original = context.workspace.get('combinations').copy(deep=True)
    result = create_chart('bar', data='combinations', label_columns='region,channel,campaign',
                          y_col='revenue', title='组合收入')
    assert 'Chart saved:' in result
    root = get_config().sessions_resolved / context.session_id / 'charts'
    meta = json.loads(next(root.glob('*.json')).read_text('utf8'))
    xaxis = meta['figure']['layout']['xaxis']
    assert xaxis['tickmode'] == 'array'
    assert len(xaxis['tickvals']) == len(xaxis['ticktext']) == 15
    assert all(len(text) <= 18 for text in xaxis['ticktext'])
    assert any('…' in text for text in xaxis['ticktext'])
    assert meta['axis_label_presentation']['identity_preserved_in_tickvals'] is True
    assert meta['axis_label_presentation']['max_tick_characters'] == 18
    assert xaxis['tickangle'] == -90
    assert meta['axis_label_presentation']['truncated_count'] > 0
    assert meta['figure']['data'][0]['x'] == xaxis['tickvals']
    pd.testing.assert_frame_equal(context.workspace.get('combinations'), original)


def test_html_export_bounds_wide_content_and_workbench_collapses_details():
    from data_agent.tools.report import _html_from_markdown
    from data_agent.web.app import create_app

    exported = _html_from_markdown('Report', '| very-long-column | other |\n|---|---|\n| ' + 'x' * 300 + ' | y |')
    assert 'table{border-collapse:collapse;width:100%;max-width:100%' in exported
    assert '.chart-container{overflow-x:auto}' in exported
    assert 'overflow-wrap:anywhere;word-break:break-word' in exported
    assert exported.count('<h1>Report</h1>') == 1
    page = create_app().test_client().get('/').get_data(as_text=True)
    assert '<details x-show="conclusion.summary" class="workbench-conclusion-details mt-1">' in page
    assert '<summary>查看计算详情</summary>' in page
