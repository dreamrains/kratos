import json

from data_agent.agent.compact import CompactState, compact_history
from data_agent.agent.synthesis_policy import build_synthesis_instruction, derive_synthesis_policy
from data_agent.knowledge.retrieval import KnowledgeRetrievalService
from data_agent.tools.registry import registry, tool_search
from data_agent.tools.sandbox import run_python


def test_tool_search_discovers_then_reaches_advanced_group():
    registry.reset_groups()
    result = json.loads(tool_search("synthesize"))

    assert "synthesize_time_series" in {item["name"] for item in result["tools"]}
    assert "eda" in registry._get_active_groups()


def test_run_python_blocks_pandas_and_numpy_io_and_emits_replay_receipt():
    for code in ("pd.read_csv('secret.csv')", "np.save('secret.npy', [1])"):
        blocked = json.loads(run_python(code))
        assert blocked["error_type"] == "sandbox_violation"
        assert "I/O" in blocked["error"]

    receipt = json.loads(run_python("1 + 1", purpose="unsupported calculation"))
    assert receipt["result"] == "2"
    assert receipt["execution_label"] == "exploratory_sandbox"
    assert receipt["replay"]["contract_version"] == "sandbox_replay.v1"
    assert len(receipt["replay"]["code_sha256"]) == 64


def test_synthesis_keeps_conditional_recommendations_and_explanation_discipline():
    policy = derive_synthesis_policy(
        user_input="recommend a retention intervention",
        evidence_records=[{"claim": "D7 retention fell", "confidence": "high"}],
    )
    instruction = build_synthesis_instruction(policy).lower()

    assert policy.answer_mode == "advisory"
    assert "decision_recommendation" not in policy.suppressed_moves
    assert "direct evidence, inferential evidence, or suggestive context" in instruction
    assert "competing explanations" in instruction
    assert "lack of causal proof alone" in instruction


def test_conflict_detection_requires_explicit_shared_identifier_not_token_overlap():
    service = KnowledgeRetrievalService()

    assert service._looks_conflicting("Revenue excludes platform fees", "Costs include platform fees") is False
    assert service._looks_conflicting("GMV excludes canceled orders", "GMV includes all orders") is True


def test_compaction_deterministically_carries_identity_and_user_obligations(tmp_path, monkeypatch):
    import data_agent.agent.compact as compact

    monkeypatch.setattr(compact, "_session_transcripts_dir", lambda _: tmp_path)
    messages = [
        {"role": "user", "content": "dataset=orders; version_id=v17; fingerprint=abc123"},
        {"role": "assistant", "content": "ack"},
        {"role": "user", "content": "不得把旧数据当作当前证据。"},
    ] + [{"role": "user", "content": f"turn {index}"} for index in range(12)]

    class Client:
        class Response:
            text = "LLM summary that omitted details"

        def chat(self, **_):
            return self.Response()

    result = compact_history("slice5", Client(), messages, CompactState())
    preserved = result[0]["content"]
    assert "version_id=v17" in preserved
    assert "不得把旧数据当作当前证据" in preserved
