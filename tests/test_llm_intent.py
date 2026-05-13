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
