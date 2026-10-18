"""Tests for LLM-based intent classification fallback (llm_intent.py)."""

import json
import pytest
from unittest.mock import MagicMock, patch

from data_agent.agent.llm_intent import (
    VALID_INTENT_TYPES,
    classify_intent_llm,
    _extract_json,
)


class TestExtractJson:
    """Test JSON extraction from LLM response text."""

    def test_plain_json_object(self):
        text = '{"intent_type": "directed_analysis", "reason": "test"}'
        result = _extract_json(text)
        assert result == {"intent_type": "directed_analysis", "reason": "test"}

    def test_json_in_code_block(self):
        text = '```json\n{"intent_type": "simple_response", "reason": "greeting"}\n```'
        result = _extract_json(text)
        assert result == {"intent_type": "simple_response", "reason": "greeting"}

    def test_json_in_code_block_no_language(self):
        text = '```\n{"intent_type": "knowledge_qa", "reason": "question"}\n```'
        result = _extract_json(text)
        assert result == {"intent_type": "knowledge_qa", "reason": "question"}

    def test_json_embedded_in_text(self):
        text = 'The classification is: {"intent_type": "data_operation", "reason": "filter request"} end.'
        result = _extract_json(text)
        assert result["intent_type"] == "data_operation"

    def test_invalid_json_returns_none(self):
        assert _extract_json("not json at all") is None

    def test_empty_string_returns_none(self):
        assert _extract_json("") is None

    def test_partial_json_returns_none(self):
        assert _extract_json('{"intent_type":') is None

    def test_array_json_returns_array(self):
        """Arrays are valid JSON and extracted as-is."""
        result = _extract_json("[1, 2, 3]")
        assert result == [1, 2, 3]


class TestValidIntentTypes:
    """Test the valid intent type set."""

    def test_contains_all_nine_types(self):
        expected = {
            "simple_response", "knowledge_qa", "analysis_consultation",
            "result_followup", "intent_negotiation", "data_requirement",
            "data_operation", "directed_analysis", "comprehensive_report",
        }
        assert VALID_INTENT_TYPES == expected


class TestClassifyIntentLlm:
    """Test the LLM classification function with mocked client."""

    def _mock_client(self, response_text):
        mock_response = MagicMock()
        mock_response.text = response_text
        client = MagicMock()
        client.chat.return_value = mock_response
        return client

    def test_valid_classification(self):
        client = self._mock_client(
            '{"intent_type": "directed_analysis", "reason": "user asks for trend", "ambiguities": []}'
        )
        result = classify_intent_llm("分析趋势", "data loaded", client=client)
        assert result["intent_type"] == "directed_analysis"
        assert result["ambiguities"] == []

    def test_requested_outputs_must_be_exact_user_spans(self):
        client = self._mock_client(json.dumps({
            "intent_type": "directed_analysis",
            "requested_outputs": [
                {"exact_span": "促销净收益", "kind": "result"},
                {"exact_span": "模型虚构的目标", "kind": "result"},
                {"exact_span": "促销净收益", "kind": "gap"},
            ],
        }, ensure_ascii=False))
        result = classify_intent_llm("请给出促销净收益", "", client=client)
        assert result["requested_outputs"] == [
            {"exact_span": "促销净收益", "kind": "result", "op": "add"},
        ]

    def test_presentation_style_is_bound_to_an_exact_request(self):
        client = self._mock_client(json.dumps({
            "intent_type": "directed_analysis",
            "requested_outputs": [
                {"exact_span": "业务负责人表达", "kind": "presentation",
                 "presentation_style": "business"},
                {"exact_span": "管理者表达", "kind": "presentation",
                 "presentation_style": "manager"},
            ],
        }, ensure_ascii=False))
        result = classify_intent_llm("请改成业务负责人表达", "", client=client)
        assert result["requested_outputs"] == [
            {"exact_span": "业务负责人表达", "kind": "presentation",
             "presentation_style": "business", "op": "add"},
        ]

    def test_current_named_dataset_selector_is_only_a_candidate_target(self):
        client = self._mock_client(json.dumps({
            "intent_type":"directed_analysis", "requested_outputs":[{
                "exact_span":"analyze missing_orders","kind":"result",
                'business_scope':{'datasets': ['missing_orders'], 'quantity': 'rows'},
            }],
        }))
        result=classify_intent_llm("Please analyze missing_orders", "", client=client)
        assert result["requested_outputs"][0]["business_scope"]=={"datasets":["missing_orders"],"quantity":"rows"}
        assert "source_binding" not in result["requested_outputs"][0]

    def test_optional_continuation_reference_must_be_a_string(self):
        valid = self._mock_client(
            '{"intent_type":"directed_analysis","continuation_of_plan_id":"spec_current"}'
        )
        invalid = self._mock_client(
            '{"intent_type":"directed_analysis","continuation_of_plan_id":{"id":"spec_current"}}'
        )
        assert classify_intent_llm("继续", "current_analysis_plan_id: spec_current", client=valid)[
            "continuation_of_plan_id"
        ] == "spec_current"
        assert classify_intent_llm("继续", "current_analysis_plan_id: spec_current", client=invalid)[
            "continuation_of_plan_id"
        ] == ""

    def test_classification_with_ambiguities(self):
        client = self._mock_client(
            '{"intent_type": "intent_negotiation", "reason": "vague", '
            '"ambiguities": [{"field": "metric", "issue": "unspecified"}]}'
        )
        result = classify_intent_llm("看看数据", "", client=client)
        assert result["intent_type"] == "intent_negotiation"
        assert len(result["ambiguities"]) == 1
        assert result["ambiguities"][0]["field"] == "metric"

    def test_invalid_intent_type_returns_none(self):
        client = self._mock_client(
            '{"intent_type": "invalid_type", "reason": "test"}'
        )
        result = classify_intent_llm("test", "", client=client)
        assert result is None

    def test_malformed_json_returns_none(self):
        client = self._mock_client("This is not JSON")
        result = classify_intent_llm("test", "", client=client)
        assert result is None

    def test_empty_response_returns_none(self):
        client = self._mock_client("")
        result = classify_intent_llm("test", "", client=client)
        assert result is None

    def test_none_response_returns_none(self):
        mock_response = MagicMock()
        mock_response.text = None
        client = MagicMock()
        client.chat.return_value = mock_response
        result = classify_intent_llm("test", "", client=client)
        assert result is None

    def test_non_list_ambiguities_treated_as_empty(self):
        client = self._mock_client(
            '{"intent_type": "data_operation", "reason": "op", "ambiguities": "not a list"}'
        )
        result = classify_intent_llm("筛选数据", "", client=client)
        assert result["ambiguities"] == []

    def test_missing_ambiguities_defaults_to_empty(self):
        client = self._mock_client(
            '{"intent_type": "knowledge_qa", "reason": "question"}'
        )
        result = classify_intent_llm("什么是X", "", client=client)
        assert result["ambiguities"] == []

    def test_client_exception_returns_none(self):
        client = MagicMock()
        client.chat.side_effect = Exception("API error")
        result = classify_intent_llm("test", "", client=client)
        assert result is None

    def test_prompt_includes_user_input_and_context(self):
        client = self._mock_client('{"intent_type": "simple_response", "reason": "hi"}')
        classify_intent_llm("hello world", "some context", client=client)
        call_args = client.chat.call_args
        messages = call_args[0][0]
        assert "hello world" in messages[0]["content"]
        assert "some context" in messages[0]["content"]

    def test_all_valid_intent_types_accepted(self):
        for intent_type in VALID_INTENT_TYPES:
            client = self._mock_client(
                f'{{"intent_type": "{intent_type}", "reason": "test"}}'
            )
            result = classify_intent_llm("test", "", client=client)
            assert result is not None
            assert result["intent_type"] == intent_type


@pytest.mark.parametrize("case,expected",[("M02",4),("M03",4),("M04",3)])
def test_archived_natural_requirements_survive_invalid_execution_target(case,expected):
    """Exact public natural JSON, without fixing the archived selector."""
    from pathlib import Path
    from types import SimpleNamespace
    fixture=json.loads((Path(__file__).parent/"fixtures/p5-classification-20261008.json").read_text(encoding="utf-8"))
    archived=next(x for x in fixture["cases"] if x["case"]==case)
    client=SimpleNamespace(manages_request_timeout=True,chat=lambda *a,**k: SimpleNamespace(text=archived["visible_json"],finish_reason="stop"))
    parsed=classify_intent_llm(archived["input"],"",client=client)
    assert len(parsed["requested_outputs"])==expected
    results=[r for r in parsed["requested_outputs"] if r["kind"]=="result"]
    assert results
    if case in {"M03","M04"}:
        assert all("business_scope" not in r and "selector" not in r for r in results)


@pytest.mark.parametrize("selector",[[],"guess",{"dataset":"orders"},{"dataset":"orders","tool":"describe_dataset","completed":True},{"dataset":"orders","tool":"describe_dataset","result_path":[-1]}])
def test_bad_target_and_unhashable_purpose_do_not_erase_original_question(selector):
    from types import SimpleNamespace
    payload={"intent_type":"directed_analysis","requested_outputs":[{"exact_span":"计算收入","kind":"result","selector":selector,"purposes":[{}]}]}
    client=SimpleNamespace(manages_request_timeout=True,chat=lambda *a,**k:SimpleNamespace(text=json.dumps(payload)))
    result=classify_intent_llm("计算收入", "", client=client)
    assert result["requested_outputs"]==[{"exact_span":"计算收入","kind":"result","op":"add"}]


def test_calculate_and_explain_can_share_original_span_without_losing_a_role():
    from types import SimpleNamespace
    payload={"intent_type":"directed_analysis","requested_outputs":[{"exact_span":"计算并解释收入","kind":"result"},{"exact_span":"计算并解释收入","kind":"presentation","presentation_role":"explanation"}]}
    client=SimpleNamespace(manages_request_timeout=True,chat=lambda *a,**k:SimpleNamespace(text=json.dumps(payload)))
    assert len(classify_intent_llm("计算并解释收入","",client=client)["requested_outputs"])==2


def test_original_six_goal_reuse_survives_actual_classifier():
    from pathlib import Path
    from types import SimpleNamespace
    archived=json.loads((Path(__file__).parent/"fixtures/p5-reuse-20261009.json").read_text(encoding="utf-8"))
    raw=json.loads(archived["visible_json"])
    client=SimpleNamespace(manages_request_timeout=True,chat=lambda *a,**k:SimpleNamespace(text=archived["visible_json"]))
    parsed=classify_intent_llm(archived["input"],"",client=client)
    assert [r["target_id"] for r in parsed["requested_outputs"]]==[r["target_id"] for r in raw["requested_outputs"]]
    assert len(parsed["requested_outputs"])==6


def test_invalid_operation_cannot_shadow_valid_same_span_proposal():
    from types import SimpleNamespace
    payload={"intent_type":"result_followup","requested_outputs":[{"exact_span":"继续","kind":"result","op":"reuse","target_id":[]},{"exact_span":"继续","kind":"result","op":"reuse","target_id":"rq_valid"}]}
    client=SimpleNamespace(manages_request_timeout=True,chat=lambda *a,**k:SimpleNamespace(text=json.dumps(payload)))
    assert classify_intent_llm("继续","",client=client)["requested_outputs"]==[{"exact_span":"继续","kind":"result","op":"reuse","target_id":"rq_valid"}]


def test_s1_invalid_scope_survives_classifier_instead_of_becoming_unbounded():
    from types import SimpleNamespace
    content="计算7日收入，并解释p值"
    scope={"datasets":["orders"],"parameters":{"window":7}}
    payload={"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":"7日收入","business_scope":scope},{"kind":"knowledge","exact_span":"解释p值"}]}
    client=SimpleNamespace(chat=lambda *a,**kw:SimpleNamespace(text=json.dumps(payload)))
    result=classify_intent_llm(content,"",client=client)
    assert result["requested_outputs"][0]["business_scope"]==scope
    assert result["requested_outputs"][1]["exact_span"]=="解释p值"
