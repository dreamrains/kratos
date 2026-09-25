"""P1-5: origin-class findings are revision triggers, never terminal.

Per the 2026-09-21 realignment and Codex hardening: the provenance lexicon
only RECALLS possible unsupported origin claims; after one revision attempt
the finding stops blocking publication and the host annotates the answer
with the authoritative provenance status instead.  Closed-class findings
(bare extrapolated numbers etc.) keep blocking on every pass.
"""

from __future__ import annotations

from types import SimpleNamespace

from data_agent.agent.loop import AgentLoop
from data_agent.agent.publication_synthesis import (
    drop_revision_only_issues,
    validate_final_narrative_issues,
)


def _packet(unit_unknown: bool = True):
    sources = [{
        "receipt_id": "r1", "tool_name": "describe_dataset", "summary": "描述",
        "facts": [{"path": "rows", "value": 12}],
    }]
    if unit_unknown:
        sources[0]["unit_status"] = "not_confirmed"
    return {"sources": sources}


ORIGIN_CLAUSE = "这份文件的取值特征表明它是典型模板/占位符特征的数据。"


def test_origin_finding_is_revision_only_classification():
    issues = validate_final_narrative_issues(ORIGIN_CLAUSE, _packet())
    blocking, revision_only = drop_revision_only_issues(issues)
    assert any(i["code"] == "unsupported_data_origin_inference" for i in revision_only)
    assert not any(i["code"] == "unsupported_data_origin_inference" for i in blocking)


def test_closed_class_findings_still_block_every_pass():
    # A wrong extrapolated value against a real curve receipt is a fact
    # violation: it must survive the revision-only filter untouched.
    packet = {
        "publication_scope": [{
            "tool": "curve_fitting", "extrapolation_allowed": False,
            "observed_x_range": [1, 7],
            "scenario_extrapolation": {
                "status": "descriptive_fit_only", "validation": "none",
                "models": [
                    {"family": "power", "parameters": {"a": 0.676, "b": -0.8657}, "r_squared": 0.856},
                ],
            },
        }],
        "sources": [],
    }
    issues = validate_final_narrative_issues(
        "幂律模型情景延伸 D30 约为 9.9%。", packet
    )
    blocking, revision_only = drop_revision_only_issues(issues)
    assert any(i["code"] in {"unbound_time_point_claim", "extrapolated_time_point"} for i in blocking)
    assert not revision_only


def test_accepted_revision_renders_host_provenance_annotation_in_answer():
    packet = _packet()
    packet.update({"status": "ready", "snapshot_digest": "sha256:origin-test"})
    fake_loop = SimpleNamespace(
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=True,
        context=SimpleNamespace(turn_state=None),
    )
    published, error = AgentLoop._render_finalized_publication(fake_loop, ORIGIN_CLAUSE)
    assert error is None
    assert published is not None and ORIGIN_CLAUSE in published
    assert "数据来源状态" in published and "未经证实" in published


def test_answer_without_origin_claim_has_no_provenance_annotation():
    packet = _packet()
    packet.update({"status": "ready", "snapshot_digest": "sha256:origin-test"})
    fake_loop = SimpleNamespace(
        _turn_publication_packet=packet,
        _turn_origin_revision_issued=False,
        context=SimpleNamespace(turn_state=None),
    )
    published, error = AgentLoop._render_finalized_publication(fake_loop, "这里只说明已观察的数据。")
    assert error is None
    assert published is not None and "数据来源状态" not in published
