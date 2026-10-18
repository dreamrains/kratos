"""Original M02 oracles through actual receipts and the single v2 contract.

Historical names preserve behavior tracing. No v1 parser/packet or phrase gate
is exercised; fixed audit decisions only verify bounded orchestration.
"""
from tests.support.rendered_text import visible_text, table_rows, has_pair, has_number, has_record
import json
import hashlib
import pytest
from tests.test_trusted_publication_semantics import engine,execute
from tests.test_trusted_publication_runtime import request,draft
from tests.test_scenario_envelope_and_disclosure import scope,_publish
from tests.test_r2_measurement_confirmation import setup_actual
from data_agent.agent.publication.runtime import snapshot_for_turn,publication_prompt
from data_agent.agent.publication.service import PublicationService
from data_agent.agent.publication.contracts import encode


def test_r4_equivalent_scenario_uses_existing_binding_and_host_renderer(scope):
    answer,calls=_publish(scope)
    assert not calls and has_record(answer["body"], {'模型族':'exponential'})
    assert has_record(answer["body"], {'模型族':'logarithmic'}) and has_record(answer["body"], {'模型族':'power'})
    assert "未来真实值未知" in answer["body"] and "单位未知" in answer["body"]
    assert "%" not in answer["body"] and "[[claim:" not in answer["body"]


def test_r4_rejected_prose_remains_a_red_control_not_a_phrase_patch(scope):
    old_clause="D30 的三个数值只能读作三种机制假设下的拟合情景：指数族的 0.014% 对应相对衰减率近似恒定，幂律族的 3.56% 对应长尾缓慢衰减，对数族因自身给出负值而不适用于外推。"
    answer,calls=_publish(scope,text=old_clause,disposition="reject")
    assert len(calls)==1 and old_clause not in answer["body"]
    # The scoped audit sees exact original values/unknown units; no prose parser.
    assert calls[0]["parts"][0]["text"]==old_clause
    assert next(c for c in calls[0]["claims"] if c["id"]==scope[2]["id"])=={k:scope[2][k] for k in ("id","label","value","unit","scope","limitations")}
    assert "claims" not in calls[0]["answer_context"] and "claim_ids" not in calls[0]["answer_context"]
    assert calls[0]["parts"][0]["claim_refs"]==[scope[2]["id"]]


@pytest.mark.parametrize("changed",[{"receipt_ref":"tr_foreign"},{"reported_values":{"exponential":.5}},{"status":"validated_prediction"},{"unit_status":"confirmed_ratio"},{"validation_status":"holdout_passed"},{"families":["exponential","power"]},{"time_point":6}])
def test_scenario_binding_rejects_foreign_receipt_and_model_supplied_values(scope,changed):
    snapshot,_,claim=scope
    payload=json.loads(draft(snapshot))
    payload["sections"][0]["parts"].append({"kind":"claim","ref":claim["id"],**changed})
    answer=PublicationService(snapshot).publish(encode(payload)).as_dict()
    assert any(i["code"]=="invalid_fields" for i in answer["issues"])
    assert answer["source_snapshot"]["claims"]==snapshot.as_dict()["claims"]


def test_unbound_fabricated_d30_value_still_fails_deterministically(scope):
    answer,calls=_publish(scope,extra={"kind":"claim","ref":"fabricated-D30-50-percent"})
    assert not calls and any(i["code"]=="unknown_claim_ref" for i in answer["issues"])
    assert "fabricated-D30-50-percent" not in answer["body"]


def test_explicit_receipt_ratio_unit_allows_percent_conversion(engine):
    loop,_,_,_,_=setup_actual(engine,scenarios=True)
    snapshot=snapshot_for_turn(loop)
    point=next(c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["result_path"]==["points",6,"y"])
    scenario=next(c for c in snapshot.as_dict()["claims"] if c["basis_refs"][0]["result_path"]==["scenarios"])
    answer=PublicationService(snapshot).publish(draft(snapshot)).as_dict()
    assert point["unit"]=="proportion" and point["value"]==.1 and "10%" in answer["body"]
    # Confirmation scales original observations only; scenario records remain
    # original, unvalidated values and do not inherit a fabricated unit grant.
    assert scenario["unit"] is None and all(r["status"]=="unvalidated" for r in scenario["value"])


def test_real_packet_builder_exposes_receipt_scope_to_existing_binding_prompt(engine):
    loop,_,_,_,_=setup_actual(engine,scenarios=True)
    snapshot=snapshot_for_turn(loop)
    prompt=publication_prompt(loop)
    assert "answer_bindings.v2" in prompt and snapshot.digest in prompt
    assert '"validation":"none"' in prompt and '"status":"unvalidated"' in prompt
    payload=draft(snapshot)
    loop.context.analysis_state.requirement_revision+=1
    updated=snapshot_for_turn(loop)
    assert updated.digest!=snapshot.digest
    answer=PublicationService(updated).publish(payload).as_dict()
    assert any(i["code"]=="stale_draft" for i in answer["issues"])
    assert answer["source_snapshot"]["claims"]==updated.as_dict()["claims"]


def test_finalization_returns_host_rendered_body_not_appendix_only(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit, read_answer
    from data_agent.session.history import load_session
    import pandas as pd
    loop, cfg = engine
    loop.context.workspace.add('retention', pd.DataFrame({'day': list(range(1, 8)), 'rate': [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.1]}))
    request(loop, '展示未验证的 D30 参数情景', {'kind': 'scenario', 'scope': {'datasets': ['retention'], 'parameters': {'scenario_points': [30]}}})
    rid, result = execute(loop, 'curve_fitting', {'name': 'retention', 'x_col': 'day', 'y_col': 'rate', 'scenario_points': [30]})
    host = snapshot_for_turn(loop)
    raw = draft(host)
    body, error = publish(loop, raw)
    assert error is None and '[[claim:' not in body and ('answer-bindings' not in body)
    assert '未验证参数情景' in body and 'logarithmic' in body and ('exponential' in body)


def test_malformed_receipt_fails_closed_without_publishing_placeholder(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit, read_answer
    from data_agent.session.history import load_session
    import pandas as pd
    loop, cfg = engine
    loop.context.workspace.add('retention', pd.DataFrame({'day': list(range(1, 8)), 'rate': [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.1]}))
    request(loop, '展示未验证的 D30 参数情景', {'kind': 'scenario', 'scope': {'datasets': ['retention'], 'parameters': {'scenario_points': [30]}}})
    rid, result = execute(loop, 'curve_fitting', {'name': 'retention', 'x_col': 'day', 'y_col': 'rate', 'scenario_points': [30]})
    receipt = loop.context.analysis_state.tool_receipts[-1]
    from data_agent.agent.publication.facts import _safe_path
    path = _safe_path(receipt['detail_ref']['path'])
    path.write_text('{"fits":[{"parameters":{"a":"not-a-number"}}]}', encoding='utf-8')
    host = snapshot_for_turn(loop)
    raw = draft(host)
    body, error = publish(loop, raw)
    assert error is None and '[[claim:' not in body and ('answer-bindings' not in body)
    assert not host.as_dict()['claims']
    assert loop._accepted_answer['requirement_outcomes'][0]['status'] == 'evidence_insufficient'


def test_placeholder_without_valid_binding_is_never_published(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit, read_answer
    from data_agent.session.history import load_session
    import pandas as pd
    loop, cfg = engine
    loop.context.workspace.add('retention', pd.DataFrame({'day': list(range(1, 8)), 'rate': [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.1]}))
    request(loop, '展示未验证的 D30 参数情景', {'kind': 'scenario', 'scope': {'datasets': ['retention'], 'parameters': {'scenario_points': [30]}}})
    rid, result = execute(loop, 'curve_fitting', {'name': 'retention', 'x_col': 'day', 'y_col': 'rate', 'scenario_points': [30]})
    host = snapshot_for_turn(loop)
    raw = 'D30 仍未知。[[claim:claim_m02_d30]]'
    body, error = publish(loop, raw)
    assert error
    body, error = publish(loop, raw)
    assert error is None and '[[claim:' not in body and ('answer-bindings' not in body)
    assert '未验证参数情景' in body and 'logarithmic' in body and ('exponential' in body)


def test_persisted_reply_and_publication_hash_bind_the_host_rendered_body(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit, read_answer
    from data_agent.session.history import load_session
    import pandas as pd
    loop, cfg = engine
    loop.context.workspace.add('retention', pd.DataFrame({'day': list(range(1, 8)), 'rate': [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.1]}))
    request(loop, '展示未验证的 D30 参数情景', {'kind': 'scenario', 'scope': {'datasets': ['retention'], 'parameters': {'scenario_points': [30]}}})
    rid, result = execute(loop, 'curve_fitting', {'name': 'retention', 'x_col': 'day', 'y_col': 'rate', 'scenario_points': [30]})
    host = snapshot_for_turn(loop)
    raw = draft(host)
    body, error = publish(loop, raw)
    assert error is None and '[[claim:' not in body and ('answer-bindings' not in body)
    assert '未验证参数情景' in body and 'logarithmic' in body and ('exponential' in body)
    assert commit(loop, {'role': 'assistant'}, body) is None
    message = load_session(loop.session_id)['messages'][-1]
    answer = read_answer(loop.session_id, message['answer_ref'])
    assert message['content'] == answer['body'] == body
    assert message['answer_sha256'] == 'sha256:' + hashlib.sha256(body.encode('utf-8')).hexdigest()
    assert message['answer_id'] == answer['answer_id']


def test_explicit_unvalidated_scenario_from_original_tool_result_is_available(engine):
    from data_agent.agent.publication.runtime import snapshot_for_turn, publish, commit, read_answer
    from data_agent.session.history import load_session
    import pandas as pd
    import math
    loop, _ = engine
    loop.context.workspace.add('retention', pd.DataFrame({'day': list(range(1, 8)), 'rate': [0.55, 0.42, 0.31, 0.24, 0.18, 0.13, 0.1]}))
    request(loop, '展示三个曲线族的未验证 D30 参数情景', {'kind': 'scenario', 'scope': {'datasets': ['retention'], 'parameters': {'scenario_points': [30]}}})
    rid, result = execute(loop, 'curve_fitting', {'name': 'retention', 'x_col': 'day', 'y_col': 'rate', 'scenario_points': [30]})
    assert {r['family'] for r in result['scenarios']} == {'exponential', 'logarithmic', 'power'}
    fits = {r['family']: r for r in result['fits']}
    for row in result['scenarios']:
        a, b = (fits[row['family']]['parameters'][k] for k in ('a', 'b'))
        expected = a * math.exp(b * 30) if row['family'] == 'exponential' else a * 30 ** b if row['family'] == 'power' else a + b * math.log(30)
        assert row['value'] == expected and row['validation'] == 'none' and (row['status'] == 'unvalidated')
        assert row['parameters'] == fits[row['family']]['parameters']
    assert next((r['value'] for r in result['scenarios'] if r['family'] == 'logarithmic')) < 0
    host = snapshot_for_turn(loop)
    body, error = publish(loop, draft(host))
    assert error is None
    assert '未验证参数情景' in body and 'exponential' in body and ('logarithmic' in body) and ('power' in body)
    assert '单位未知' in body and '30' in body and ('%' not in body)
    assert loop._accepted_answer['requirement_outcomes'][0]['status'] == 'answered'
    owned = host.as_dict()['requirements'][0]['claim_ids']
    assert len(owned) == 1 and next((c for c in host.as_dict()['claims'] if c['id'] == owned[0]))['value'] == result['scenarios']
    assert commit(loop, {'role': 'assistant'}, body) is None
    message = load_session(loop.session_id)['messages'][-1]
    assert read_answer(loop.session_id, message['answer_ref'])['body'] == message['content'] == body
