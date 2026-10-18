"""Context cleanup and durable delivery through the single publication path."""
import pytest
from data_agent.agent.context import AgentContext,get_current_context,use_agent_context
from data_agent.agent.loop import AgentLoop
from data_agent.session.workspace import Workspace
from tests.test_trusted_publication_runtime import AppClient,intent_for_app


@pytest.fixture
def stream_loop(tmp_path,monkeypatch):
    from data_agent.config import get_config
    import data_agent.session.task_manager as module
    cfg=get_config()
    monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions")
    monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    monkeypatch.setattr(module,"task_manager",module.TaskManager(tasks_dir=tmp_path/"tasks"))
    loop=AgentLoop(client=object(),session_id="stream-lifecycle")
    intent_for_app(monkeypatch,"knowledge","什么是回归分析？")
    loop.client=AppClient(loop)
    return loop


@pytest.mark.parametrize("method",["stream_turn","resume_turn_streaming"])
@pytest.mark.parametrize("termination",["exhaustion","close","exception"])
@pytest.mark.parametrize("outer_context",[False,True],ids=["no-current","restore-outer"])
def test_streaming_context_is_bound_only_while_generator_runs(stream_loop,monkeypatch,method,termination,outer_context):
    loop=stream_loop
    if method=="resume_turn_streaming":
        # Lifecycle entry only; the actual durable response binding and replay
        # are covered by the runtime resolved/skipped/cancelled app cases.
        suspension=configure_resume(monkeypatch,loop)
    if termination=="exception":
        def explode(_round_num):
            yield {"type":"llm_call_start"}
            raise RuntimeError("stream exploded")
        monkeypatch.setattr(loop,"_stream_llm_round",explode)
    outer=AgentContext(session_id="outer",workspace=Workspace()) if outer_context else None
    def exercise():
        assert get_current_context() is outer
        events=loop.stream_turn("什么是回归分析？") if method=="stream_turn" else loop.resume_turn_streaming(suspension.confirmation_id,"什么是回归分析？",expected_version=suspension.version,idempotency_key="lifecycle_answer_once")
        assert get_current_context() is outer
        try:
            event=next(events)
            assert event["type"]=="llm_call_start"
            assert get_current_context() is loop.context
            if termination=="close": events.close()
            elif termination=="exception":
                with pytest.raises(RuntimeError,match="stream exploded"): list(events)
            else:
                remaining=list(events)
                assert any(e["type"]=="text_delta" for e in remaining)
                assert not any(e["type"]=="error" for e in remaining)
        finally: events.close()
        assert get_current_context() is outer
    if outer is None: exercise()
    else:
        with use_agent_context(outer): exercise()
    assert get_current_context() is None


def configure_resume(monkeypatch,loop):
    from tests.test_trusted_publication_runtime import request
    from data_agent.agent.confirmation.runtime import build_direct_question_candidate
    with use_agent_context(loop.context): request(loop,"什么是回归分析？",kind="knowledge")
    # Kernel lifecycle fixture, separate from the ordinary knowledge-turn
    # question policy: persist a real record and resolve through the service.
    candidate=build_direct_question_candidate(session_id=loop.session_id,
        turn_id="lifecycle",message_version=len(loop.messages),request={
            "question":"本次交付需要解释哪个分析主题？", "options":[],
            "confirmation_type":"scope_confirmation",
            "blocking_reason":"交付主题由用户提供。"})
    service=loop._confirmation_runtime()
    created=service.request(candidate)
    assert created.record is not None
    return service.checkpoint(loop.session_id)


@pytest.mark.parametrize("method",["stream_turn","resume_turn_streaming"])
def test_final_stream_delta_is_persisted_before_it_is_yielded(stream_loop,monkeypatch,method):
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    loop=stream_loop
    if method=="resume_turn_streaming": suspension=configure_resume(monkeypatch,loop)
    events=loop.stream_turn("什么是回归分析？") if method=="stream_turn" else loop.resume_turn_streaming(suspension.confirmation_id,"什么是回归分析？",expected_version=suspension.version,idempotency_key="lifecycle_answer_once")
    observed=[]
    try:
        for event in events:
            if event["type"]!="text_delta": continue
            observed.append(event["text"])
            stored=load_session(loop.session_id)["messages"][-1]
            assert stored["content"]==event["text"]
            assert read_answer(loop.session_id,stored["answer_ref"])["body"]==event["text"]
        assert len(observed)==1 and "回归" in observed[0]
    finally: events.close()
    assert get_current_context() is None
