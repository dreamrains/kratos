import pandas as pd

from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.session.workspace import Workspace
from data_agent.tools.data_understand import interpret_dataset


def test_automatic_hints_do_not_treat_raw_copy_as_independent_source():
    workspace = Workspace()
    source = pd.DataFrame({"user_id":[1,2,3],"amount":[5.,6.,7.]})
    workspace.add("source", source)
    workspace.derive("source", "analysis", source.copy(), expression="analysis view")
    with use_agent_context(AgentContext(session_id="hint-lineage", workspace=workspace)):
        result = interpret_dataset("analysis")
        assert not result.data.get("cross_dataset_hints")
        workspace.add("orders", pd.DataFrame({"user_id":[1,2,2],"revenue":[10.,20.,30.]}))
        result = interpret_dataset("analysis")
    hints = result.data["cross_dataset_hints"]
    assert {hint["other_dataset"] for hint in hints} == {"orders"}
    reasons = [item["reason"] for item in result.data["suggested_analyses"] if "关联分析" in item["direction"]]
    assert reasons and all("先审计" in reason for reason in reasons)


def test_unrelated_peer_pair_is_not_reported_as_target_relationship():
    workspace = Workspace()
    workspace.add("target", pd.DataFrame({"amount":[5.,6.,7.]}))
    workspace.add("orders", pd.DataFrame({"user_id":[1,2,3]}))
    workspace.add("visits", pd.DataFrame({"user_id":[1,2,2]}))
    with use_agent_context(AgentContext(session_id="hint-target", workspace=workspace)):
        result = interpret_dataset("target")
    assert not result.data.get("cross_dataset_hints")
