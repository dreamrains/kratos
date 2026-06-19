import pandas as pd

from data_agent.tools.chart_contract import ChartContractResult, infer_semantic_role


def test_numeric_user_identifier_is_not_a_measure():
    series = pd.Series([200000000000000001, 200000000000000002])

    assert infer_semantic_role("user_id", series) == "identifier"


def test_numeric_amount_is_a_measure():
    assert infer_semantic_role("revenue", pd.Series([10.5, 12.0])) == "measure"


def test_parseable_dates_are_time():
    assert infer_semantic_role(
        "paid_at",
        pd.Series(["2026-05-01", "2026-05-02"]),
    ) == "time"


def test_low_cardinality_text_is_category():
    assert infer_semantic_role("segment", pd.Series(["A", "B", "A"])) == "category"


def test_contract_result_is_valid_only_without_error():
    valid = ChartContractResult(dataframe=pd.DataFrame({"value": [1]}))
    invalid = ChartContractResult(
        dataframe=pd.DataFrame({"value": [1]}),
        error="invalid measure",
    )

    assert valid.valid is True
    assert invalid.valid is False
