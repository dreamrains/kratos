import pandas as pd
import pytest

from data_agent.tools.auto_insight import _generate_observations
from data_agent.tools.data_clean import infer_column_type
from data_agent.tools.data_understand import _classify_columns
from data_agent.utils.data_features import scan_data_quality


@pytest.mark.parametrize('name', ['user_id', 'userId', '主用户ID', '订单编号'])
def test_repeated_identifiers_remain_identifiers_without_becoming_unique_keys(name):
    values = ['20250101', '20250102'] * 10
    df = pd.DataFrame({name: values, '售价': [12, 45] * 10})
    classified = _classify_columns(df)
    assert classified['id_columns'] == [{'column': name, 'unique_count': 2}]
    assert scan_data_quality(df)['columns'][name]['type'] == 'id'
    assert infer_column_type(df[name])['suggested_type'] == 'keep'
    assert df[name].tolist() == values
    assert [m['column'] for m in classified['key_metrics']] == ['售价']


@pytest.mark.parametrize('name', ['paid', 'bid', 'liquidity', 'user_id_count'])
def test_id_substrings_and_aggregated_counts_are_not_identifiers(name):
    df = pd.DataFrame({name: range(20)})
    assert not _classify_columns(df)['id_columns']


@pytest.mark.parametrize('name', ['售价', '实收金额', '代金券面值(分)', 'unit_price', 'revenue'])
def test_low_cardinality_monetary_values_remain_numeric_without_guessing_units(name):
    series = pd.Series([12, 45] * 10, name=name)
    assert infer_column_type(series)['suggested_type'] == 'keep'
    assert scan_data_quality(series.to_frame())['columns'][name]['type'] == 'numeric'
    assert infer_column_type(pd.Series([0, 1] * 10, name='status'))['suggested_type'] == 'category_maybe'


def test_automatic_insights_do_not_sum_trend_or_correlate_repeated_numeric_ids():
    df = pd.DataFrame({
        'user_id': [700000000000000000, 900000000000000000] * 10,
        '支付时间': pd.date_range('2026-04-07', periods=20),
        '商品名称': ['周卡', '月卡'] * 10,
        '售价': [12, 45] * 10,
    })
    before = df.copy(deep=True)
    observations = _generate_observations(df, 'full')
    assert observations and any('售价' in item for item in observations)
    assert all('user_id' not in item for item in observations)
    pd.testing.assert_frame_equal(df, before)


def test_repeated_identifier_cannot_be_a_chart_measure_but_allows_grouped_categories():
    from data_agent.tools.chart_contract import infer_semantic_role, validate_chart_request
    df = pd.DataFrame({'user_id': [10, 20] * 10, 'revenue': range(20)})
    assert infer_semantic_role('user_id', df.user_id) == 'identifier'
    assert not validate_chart_request(df, 'scatter', 'user_id', ['revenue']).valid
    assert not validate_chart_request(df, 'line', 'user_id', ['revenue']).valid
    grouped = df.groupby('user_id', as_index=False).revenue.sum()
    assert validate_chart_request(grouped, 'bar', 'user_id', ['revenue']).valid


@pytest.mark.parametrize('chart_type', ['bar', 'line', 'box', 'pie'])
def test_identifier_values_are_not_chart_measures(chart_type):
    from data_agent.tools.chart_contract import validate_chart_request
    df = pd.DataFrame({'group': ['a', 'b'], 'user_id': [123, 456]})
    result = validate_chart_request(df, chart_type, 'group', ['user_id'])
    assert result.error_code == 'invalid_identifier_measure'
    counted = validate_chart_request(df, chart_type, 'group', ['user_id'], aggregation='count')
    assert counted.valid == (chart_type in {'bar', 'pie'})


@pytest.mark.parametrize('name', ['用户平均金额', '用户数', 'customer_count', 'user_id_count'])
def test_named_measures_are_not_identifiers_just_because_they_mention_users(name):
    from data_agent.tools.chart_contract import infer_semantic_role
    assert infer_semantic_role(name, pd.Series([10, 20])) == 'measure'


@pytest.mark.parametrize('text, expected', [
    ('比较2026-04-07至2026-04-21和2026-04-22至2026-05-06收入', True),
    ('compare 2026/4/7 to 2026/4/21 and 2026/4/22 to 2026/5/6', True),
    ('compare 2026-02-30~2026-03-20 and 2026-04-01~2026-04-15', False),
    ('compare 2026-03-20~2026-03-01 and 2026-04-01~2026-04-15', False),
    ('比较收入', False),
])
def test_explicit_comparison_ranges_are_recognized_without_keyword_guesses(text, expected):
    from data_agent.agent.question_need_detector import _has_time_window
    assert _has_time_window(text) is expected
