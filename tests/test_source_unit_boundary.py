"""AC25 actual source units; declared labels do not become source authority."""
import json
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine
from tests.support.publication_runtime import request,draft,_NativeProductModel
from tests.test_slice3_method_integrity import _p1_original_call,_joint_http_answer


@pytest.mark.parametrize('route',['direct','registry','executor'])
@pytest.mark.parametrize('case',['same','mixed','missing'])
def test_ac25_current_raw_unit_column_never_grants_verified_currency(engine,tmp_path,route,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.tools.registry import registry
    loop,_=engine;units={'same':['CNY','CNY'],'mixed':['CNY','USD'],'missing':['CNY',None]}[case]
    loop.context.workspace.add('sales',pd.DataFrame(dict(amount=[10.,20.],currency=units)))
    request(loop,'保留sales原记录的amount合计和currency原值，不能把声明币种当作已核源单位。',dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum')))
    if route=='executor':
        from data_agent.llm.client import ToolCall
        loop._execute_tools_sequential([ToolCall('actual_currency','describe_dataset',dict(name='sales'))], '')
    else:_p1_original_call(loop,route,'describe_dataset',dict(name='sales'))
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));claims=[c for c in snap.as_dict()['claims'] if c.get('target',{}).get('metric')=='amount' and c['target'].get('statistic')=='sum']
    assert error is None and len(claims)==1 and claims[0]['value']==30 and claims[0]['unit'] is None
    assert all(c['unit'] not in {'CNY','USD'} for c in claims)
    if route!='executor':assert '单位未知' in body
    (tmp_path/'ac25-unit-observation.json').write_text(json.dumps(dict(route=route,case=case,source=loop.context.workspace.get('sales').to_dict('records'),answer=loop._accepted_answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


def test_ac25_normal_mixed_currency_formal_total_requires_original_unit_binding(engine,tmp_path):
    content='加载附件将其命名为sales；amount的原币种在currency列，交付同一币种的可比较总额，混合币种不能相加成已完成的金额。'
    frame=pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','USD']))
    specs=[dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]
    model=_NativeProductModel(content,'sales','describe_dataset',dict(name='sales'),specs)
    loop,answer=_joint_http_answer(engine,tmp_path,model,['sales'],[frame],'ac25_source_currency')
    assert '混合源单位' in answer['body'] and any(c['value']==2 and c['unit']=='条' for c in answer['source_snapshot']['claims'])
    published={t['ref'] for t in answer['render_trace'] if t['kind']=='claim' and t['disposition']=='accepted'}
    assert not any(c['id'] in published and c.get('target',{}).get('metric')=='amount' and c['value']==30 for c in answer['source_snapshot']['claims'])
    assert answer['requirement_outcomes'][0]['status']!='answered', 'Current formal delivery has no source-unit constraint;raw30/unknown currently completes the explicitly unit-dependent goal.'


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same','mixed','missing'])
def test_ac25_bound_source_units_across_real_interfaces(engine,tmp_path,route,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine;frame=pd.DataFrame(dict(amount=[10.,20.],currency={'same':['CNY','CNY'],'mixed':['CNY','USD'],'missing':['CNY',None]}[case]));loop.context.workspace.add('sales',frame)
    specs=[dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]
    request(loop,'amount源单位来自currency，混币或缺失币种只保留金额缺口及独立行数。',specs)
    _p1_original_call(loop,route,'describe_dataset',dict(name='sales'))
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    (tmp_path/'bound-units.json').write_text(json.dumps(dict(case=case,route=route,answer=answer),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None and any(c['value']==2 and c['unit']=='条' for c in snap.as_dict()['claims'])
    amounts=[c for c in snap.as_dict()['claims'] if c.get('target',{}).get('metric')=='amount' and c.get('target',{}).get('statistic')=='sum']
    if case=='same':assert len(amounts)==1 and amounts[0]['unit']=='CNY' and answer['requirement_outcomes'][0]['status']=='answered'
    else:assert not amounts and answer['requirement_outcomes'][0]['status']!='answered' and ('混合源单位' if case=='mixed' else '缺失') in body


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same','mixed','missing','outside_window','unrelated_change','version_change','permission_change','missing_column'])
def test_ac25_actual_comparison_source_unit_scope_and_original_identity(engine,tmp_path,route,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.native import resolve_native_claims
    loop,cfg=engine;units=['CNY','USD'] if case=='mixed' else ['CNY',None] if case=='missing' else ['CNY','CNY']
    frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=units))
    if case=='outside_window':frame=pd.concat([frame,pd.DataFrame(dict(day=['2026-09-03','bad-date'],amount=[100.,100.],currency=['USD','USD']))],ignore_index=True)
    if case=='missing_column':frame=frame.drop(columns=['currency'])
    loop.context.workspace.add('sales',frame)
    scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))
    request(loop,'比较两个指定日历窗口的amount，单位来自currency；不借窗口外单位或旧版本完成。',[dict(kind='measurement',scope=scope),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))])
    args=dict(name='sales',date_col='day',metrics='amount',period_a='2026-09-01~2026-09-01',period_b='2026-09-02~2026-09-02')
    rid,raw,_=_p1_original_call(loop,route,'compare_periods',args);receipt=loop.context.analysis_state.tool_receipts[-1];file=cfg.sessions_resolved/loop.session_id/receipt['detail_ref']['path'];original=file.read_bytes()
    if case=='unrelated_change':loop.context.workspace.add('other',pd.DataFrame(dict(x=[1])))
    elif case=='version_change':loop.context.workspace.add('sales',frame.assign(amount=frame.amount*2))
    elif case=='permission_change':receipt['data_identities']['sales']['permission_scope']='another_permission'
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    (tmp_path/'comparison-units.json').write_text(json.dumps(dict(route=route,case=case,result=raw,answer=answer),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None and file.read_bytes()==original
    values=[c for c in snap.as_dict()['claims'] if c.get('target',{}).get('metric')=='amount']
    if case in {'same','outside_window','unrelated_change'}:
        assert any(c['value']==10 and c['unit']=='CNY' for c in values) and any(c['value']==20 and c['unit']=='CNY' for c in values)
        assert answer['requirement_outcomes'][0]['status']==('partial' if case=='outside_window' else 'answered')
        assert '混合源单位' not in body
    else:
        assert not values and answer['requirement_outcomes'][0]['status']!='answered'
        if case in {'mixed','missing','missing_column'}:assert any(c['unit']=='条' for c in snap.as_dict()['claims'])


def test_ac25_original_unit_scope_cannot_be_omitted_from_formal_plan(engine):
    from data_agent.agent.analysis_plan_contracts import validate_analysis_plan_contract
    from copy import deepcopy
    loop,_=engine;loop.context.workspace.add('sales',pd.DataFrame(dict(amount=[1],currency=['CNY'])))
    spec=dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))
    request(loop,'amount原单位字段为currency，必须交付同单位总额。',spec)
    plan=deepcopy(loop.context.analysis_state.analysis_plan)
    plan['method_plan'][0]['required_deliveries'][0]['scope']['parameters']={}
    result=validate_analysis_plan_contract(plan,answer_requirements=loop.context.analysis_state.answer_requirements,requirement_revision=loop.context.analysis_state.requirement_revision)
    assert not result.ok


@pytest.mark.parametrize('case',['describe_same','describe_missing','compare_same','compare_mixed'])
def test_ac25_bound_units_normal_original_save_refresh_and_export(engine,tmp_path,case):
    comparison=case.startswith('compare');mixed=case.endswith('mixed');missing=case.endswith('missing');name='sales'
    frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY',None if missing else 'USD' if mixed else 'CNY']))
    spec=dict(kind='measurement',scope=dict(datasets=[name],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))
    content='加载附件将其命名为sales；amount原单位来自currency；交付同币金额，混币或单位缺失保持金额缺口。'
    if comparison:
        tool='compare_periods';args=dict(name=name,date_col='day',metrics='amount',period_a='2026-09-01~2026-09-01',period_b='2026-09-02~2026-09-02')
    else:tool='describe_dataset';args=dict(name=name)
    model=_NativeProductModel(content,name,tool,args,[spec]);loop,answer=_joint_http_answer(engine,tmp_path,model,[name],[frame],'source_units_'+case)
    monetary=[c for c in answer['source_snapshot']['claims'] if c.get('target',{}).get('source_unit_proof')]
    if mixed or missing:assert not monetary and answer['requirement_outcomes'][0]['status']!='answered' and ('混合源单位' if mixed else '缺失') in answer['body']
    else:assert monetary and all(c.get('unit') in {'CNY','percent'} for c in monetary if isinstance(c['value'],(int,float))) and answer['requirement_outcomes'][0]['status']=='answered' and 'CNY' in answer['body']


@pytest.mark.parametrize('change',['source_version','scope_rebind'])
def test_ac25_unit_authority_is_rechecked_before_commit(engine,tmp_path,change):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    loop,cfg=engine;frame=pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY'],other_unit=['USD','USD']));loop.context.workspace.add('sales',frame)
    specs=[dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))]
    request(loop,'amount原单位明确绑定currency；声明不能在计算后换成other_unit。',specs)
    _p1_original_call(loop,'registry','describe_dataset',dict(name='sales'));snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None and 'CNY' in body
    receipt=loop.context.analysis_state.tool_receipts[-1];file=cfg.sessions_resolved/loop.session_id/receipt['detail_ref']['path'];original=file.read_bytes()
    if change=='source_version':loop.context.workspace.add('sales',frame.assign(currency=['USD','USD']))
    else:loop.context.analysis_state.answer_requirements[0]['necessary_deliveries'][0]['scope']['parameters']['source_unit_columns']['amount']='other_unit'
    assert commit(loop,dict(role='assistant'),body) and not loop.context.analysis_state.accepted_answers
    assert file.read_bytes()==original


@pytest.mark.parametrize('label',['proportion','percent','hypothesis_status'])
def test_ac25_source_unit_label_cannot_invoke_renderer_protocol_or_rescale(engine,label):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine;loop.context.workspace.add('sales',pd.DataFrame(dict(amount=[10.,20.],currency=[label,label])))
    spec=dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))
    request(loop,'源单位标签只原样保留，不授予比例缩放或假设状态协议。',spec)
    _p1_original_call(loop,'registry','describe_dataset',dict(name='sales'));snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap))
    expected_label={'hypothesis_status':r'hypothesis\_status'}.get(label,label)
    assert error is None and '30.0 '+expected_label in body and '3000%' not in body and loop._accepted_answer['requirement_outcomes'][0]['status']=='answered'


@pytest.mark.parametrize('case',['missing_metrics','count_quantity','valid'])
def test_ac25_published_scope_schema_matches_static_unit_requirements(case):
    from jsonschema import Draft7Validator
    from data_agent.agent.publication.deliveries import business_scope_schema,validate_business_scope
    from data_agent.agent.publication.contracts import ContractError
    scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))
    if case=='missing_metrics':scope.pop('metrics')
    elif case=='count_quantity':scope['quantity']='rows'
    advertised=not list(Draft7Validator(business_scope_schema(required=True,measurement=True)).iter_errors(scope))
    try:validate_business_scope(scope,required=True,measurement=True);runtime=True
    except ContractError:runtime=False
    assert advertised==runtime==(case=='valid')



def _ac25_register_same_deliveries(loop,route,marker):
    from data_agent.tools.registry import registry
    from data_agent.tools.analysis_flow import record_analysis_plan
    state=loop.context.analysis_state
    deliveries=[{'id':d['id']} for q in state.answer_requirements if q.get('lifecycle_status')=='active' for d in q.get('necessary_deliveries',[])]
    raw=dict(contract_version='stage3c0b.v2',requirement_revision=state.requirement_revision,goal=marker,visualization_strategy=[],method_plan=[dict(step_id=marker,goal=marker,expected_output='Same original source-unit delivery',dataset_inputs=['sales'],dataset_contract_ids=[c['id'] for c in state.dataset_contracts if c.get('dataset')=='sales'],evidence_requirements=['original receipt'],required_deliveries=deliveries)])
    result=record_analysis_plan(raw) if route=='direct' else registry.execute('record_analysis_plan',dict(plan_json=raw)).summary
    result=json.loads(result);assert result.get('analysis_plan_id'),result
    return result


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('change',['same','unrelated','source_changed'])
def test_ac25_original_unit_delivery_survives_same_scope_plan_replacement(engine,tmp_path,route,change):
    from pathlib import Path
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
    from data_agent.agent.publication.requirements import update_requirements
    from data_agent.session.history import save_session,load_canonical_history
    loop,cfg=engine;frame=pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']));
    from tests.test_slice3_method_integrity import _joint_trust_original
    _joint_trust_original(loop,'sales',frame)
    spec=dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))
    request(loop,'amount原币种来自currency，交付同币总额。',spec);rid=loop.context.turn_requirement_ids[0]
    first_plan=_ac25_register_same_deliveries(loop,route,'unit_original')
    _p1_original_call(loop,route,'describe_dataset',dict(name='sales'))
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));assert error is None and 'CNY' in body
    assert commit(loop,dict(role='assistant'),body) is None
    originals={str(p):p.read_bytes() for p in (cfg.sessions_resolved/loop.session_id).rglob('*.json') if p.parent.name in {'analyses','analysis_flow','tool_outputs'}}
    content='沿用原amount同币总额，保留原单位字段；仅重新安排正式步骤。';msgid='unit_reuse_'+change
    loop.messages.append(dict(role='user',content=content,request_id=msgid));save_session(loop.messages,loop.session_id,extra_meta={'publication_schema':'answer_bindings.v2'},merge_protect=False);loop._last_jsonl_idx=len(loop.messages)
    state=loop.context.analysis_state;ids=update_requirements(state,load_canonical_history(loop.session_id),msgid,[dict(op='reuse',start=0,end=len(content),kind='result',target_id=rid)],expected_revision=state.requirement_revision);loop.context.turn_requirement_ids=ids
    if change in {'unrelated','source_changed'}:
        loop.prepare_for_bound_upload()
        result=loop.context.workspace.add('other',pd.DataFrame(dict(x=[999.]))) if change=='unrelated' else loop.context.workspace.add('sales',frame.assign(currency=['USD','USD']))
        assert not result.startswith('Error:'),result
        if change=='source_changed':assert loop.context.workspace._publication_data_identity('sales')!=state.answer_requirements[0]['source_data_identities']['sales']
    if change=='source_changed':
        next_plan=None
    else:next_plan=_ac25_register_same_deliveries(loop,route,'unit_replacement')
    after=snapshot_for_turn(loop);next_body,error=publish(loop,draft(after));assert error is None
    claims=[c for c in after.as_dict()['claims'] if c.get('target',{}).get('metric')=='amount' and c['target'].get('statistic')=='sum']
    evidence=dict(route=route,change=change,first_plan=first_plan,next_plan=next_plan,snapshot=after.as_dict(),answer=loop._accepted_answer,Provider=0)
    (tmp_path/'unit-plan-replacement.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(Path(p).read_bytes()==raw for p,raw in originals.items())
    if change=='source_changed':assert not claims and loop._accepted_answer['requirement_outcomes'][0]['status']!='answered'
    else:
        assert next_plan['analysis_plan_id']!=first_plan['analysis_plan_id']
        assert len(claims)==1 and claims[0]['value']==30 and claims[0]['unit']=='CNY' and loop._accepted_answer['requirement_outcomes'][0]['status']=='answered'



def test_ac25_normal_reuse_replans_original_unit_without_recomputation(engine,tmp_path):
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    from data_agent.llm.client import Response,ToolCall,StreamTextDelta,StreamComplete
    from data_agent.agent.publication.contracts import encode
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
    from data_agent.tools.report import export_assistant_reply
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    content='加载附件将其命名为sales；amount原币种来自currency，交付同币总额。'
    spec=dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))
    first_model=_NativeProductModel(content,'sales','describe_dataset',dict(name='sales'),[spec])
    loop,first=_joint_http_answer(engine,tmp_path,first_model,['sales'],[pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']))],'unit_plan_normal')
    _,cfg=engine;root=cfg.sessions_resolved/loop.session_id;originals={p:p.read_bytes() for p in root.rglob('*.json') if p.parent.name in {'analyses','analysis_flow','tool_outputs'}}
    class Replan:
        content='沿用原amount同币总额，原目标和单位字段不变；仅重新安排正式步骤，不重新计算。'
        calls=[]
        def chat(self,messages,system='',**kw):
            if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':
                requirements,_=json.JSONDecoder().raw_decode(messages[-1]['content'].partition('canonical_requirements: ')[2]);goal=next(r for r in requirements if r['semantic_kind']=='result' and r['lifecycle_status']=='active')
                return Response(text=encode(dict(intent_type='directed_analysis',requested_outputs=[dict(kind='result',exact_span=self.content,op='reuse',target_id=goal['id'])])))
            view=ScriptedClient._current_host_snapshot(messages,system)
            if not self.calls:
                deliveries=[{'id':d['id']} for q in view['execution_targets'] if q['semantic_kind']=='result' for d in q['necessary_deliveries']]
                plan=dict(contract_version='stage3c0b.v2',requirement_revision=view['requirement_revision'],goal=self.content,visualization_strategy=[],method_plan=[dict(step_id='unit_next',goal=self.content,expected_output='Same original amount and source unit',dataset_inputs=['sales'],evidence_requirements=['original receipt'],required_deliveries=deliveries)])
                self.calls.append('record_analysis_plan');return Response(tool_calls=[ToolCall('unit_replan','record_analysis_plan',dict(plan_json=plan))])
            return Response(text=encode(dict(schema='answer_bindings.v2',snapshot_digest=view['snapshot_digest'],sections=[dict(requirement_ids=[q['id']],parts=[dict(kind='claim',ref=cid) for cid in q['claim_ids']]) for q in view['requirements'] if not q['withdrawn']])))
        def stream_chat_structured(self,*a,**kw):
            response=self.chat(*a,**kw)
            if response.text:yield StreamTextDelta(response.text)
            yield StreamComplete(response)
    model=Replan();factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config['agent_manager']=factory()
    with app.test_client() as http:
        response=http.post('/api/chat',json=dict(session_id=loop.session_id,message=model.content))
        events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
        refresh=http.get('/api/sessions/'+loop.session_id).get_json()
    loop=app.config['agent_manager'].get(loop.session_id)
    with use_agent_context(loop.context):
        saved=load_session(loop.session_id);message=next(m for m in reversed(saved['messages']) if m.get('answer_ref'));answer=read_answer(loop.session_id,message['answer_ref']);export=export_assistant_reply(loop.session_id,answer['body'],'md',reply_id=message['reply_id'])
    app.config['agent_manager']=factory()
    with app.test_client() as http:cold=http.get('/api/sessions/'+loop.session_id).get_json()
    (tmp_path/'unit-normal-replan.json').write_text(json.dumps(dict(first=first,events=events,answer=answer,export=export,cold=cold,calls=model.calls,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert model.calls==['record_analysis_plan'] and not any(k in {'error','suspended','confirmation_required'} for k,v in events)
    assert len([v for k,v in events if k=='turn_end'])==1 and next(v for k,v in events if k=='turn_end')['reply_content']==answer['body']
    assert first['source_snapshot']['plan_id']!=answer['source_snapshot']['plan_id']
    assert all(p.read_bytes()==raw for p,raw in originals.items())
    assert any(m.get('answer_ref')==message['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
    assert export['status']=='exported' and answer['body'] in (root/'reports'/export['artifact_path'].split('/')[-1]).read_text(encoding='utf-8')
    assert answer['requirement_outcomes'][0]['status']=='answered' and '30.0 CNY' in answer['body']



@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('fault',['missing','changed','rehashed','unregistered','wrong_step','rebind','new_goal'])
def test_ac25_old_plan_reuse_requires_original_registration_scope_and_goal(engine,tmp_path,route,fault):
    import hashlib
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from tests.test_slice3_method_integrity import _joint_trust_original
    loop,cfg=engine;_joint_trust_original(loop,'sales',pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY'],other_currency=['USD','USD'])))
    spec=dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))
    request(loop,'amount源单位绑定currency，保留原目标。',spec);original_goal=loop.context.turn_requirement_ids[0]
    first=_ac25_register_same_deliveries(loop,route,'unit_original')
    _p1_original_call(loop,route,'describe_dataset',dict(name='sales'))
    _ac25_register_same_deliveries(loop,route,'unit_replacement')
    old=cfg.sessions_resolved.parent/first['saved'];raw=old.read_bytes();(tmp_path/'plan-original.json').write_bytes(raw)
    manifest=cfg.sessions_resolved/loop.session_id/'artifacts.json';manifest_raw=manifest.read_bytes();(tmp_path/'manifest-original.json').write_bytes(manifest_raw)
    if fault in {'missing','changed','rehashed'}:
        old.rename(old.with_suffix('.preserved'))
        if fault!='missing':
            payload=json.loads(raw);payload['method_plan'][0]['required_deliveries'][0]['scope']['parameters']['source_unit_columns']['amount']='other_currency';old.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        if fault=='rehashed':
            items=json.loads(manifest_raw)
            for item in items:
                if item['path']==first['saved']:item['sha256']='sha256:'+hashlib.sha256(old.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(items,ensure_ascii=False),encoding='utf-8')
    elif fault=='unregistered':manifest.write_text(json.dumps([item for item in json.loads(manifest_raw) if item['path']!=first['saved']],ensure_ascii=False),encoding='utf-8')
    elif fault=='wrong_step':loop.context.analysis_state.tool_receipts[-1]['step_id']='another_original_step'
    elif fault=='rebind':loop.context.analysis_state.answer_requirements[0]['necessary_deliveries'][0]['scope']['parameters']['source_unit_columns']['amount']='other_currency'
    elif fault=='new_goal':
        request(loop,'新增另一目标的amount同币合计，不能借旧交付ID完成。',spec)
        assert loop.context.turn_requirement_ids[0]!=original_goal
        _ac25_register_same_deliveries(loop,route,'unit_new_goal')
    snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));answer=loop._accepted_answer
    (tmp_path/'unit-original-plan-guard.json').write_text(json.dumps(dict(route=route,fault=fault,original_goal=original_goal,snapshot=snapshot.as_dict(),answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None
    if fault=='new_goal':
        target=next(q for q in answer['source_snapshot']['requirements'] if q['id']==loop.context.turn_requirement_ids[0]);assert not target['claim_ids']
        assert next(q for q in answer['requirement_outcomes'] if q['requirement_id']==target['id'])['status']!='answered'
        assert any(c.get('target',{}).get('statistic')=='sum' and c['value']==30 and c['unit']=='CNY' for c in answer['source_snapshot']['claims'])
    else:
        assert not any(c.get('target',{}).get('metric')=='amount' and c['target'].get('statistic')=='sum' for c in snapshot.as_dict()['claims'])
        assert answer['requirement_outcomes'][0]['status']!='answered'



def _ac25_unit_plan(loop,route,names,deliveries,marker):
    from data_agent.tools.registry import registry
    from data_agent.tools.analysis_flow import record_analysis_plan
    state=loop.context.analysis_state
    plan=dict(contract_version='stage3c0b.v2',requirement_revision=state.requirement_revision,goal=marker,visualization_strategy=[],method_plan=[dict(step_id=marker,goal=marker,expected_output='Original independent unit-bound products',dataset_inputs=names,evidence_requirements=['original receipts'],required_deliveries=deliveries)])
    value=record_analysis_plan(plan) if route=='direct' else registry.execute('record_analysis_plan',dict(plan_json=plan)).summary
    value=json.loads(value);assert value.get('analysis_plan_id'),value
    return value


@pytest.mark.parametrize('route',['direct','registry'])
def test_ac25_append_keeps_original_unit_proof_without_granting_new_delivery(engine,tmp_path,route):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.native import resolve_native_claims
    from tests.test_slice3_method_integrity import _joint_trust_original
    loop,cfg=engine;_joint_trust_original(loop,'sales',pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY'])))
    request(loop,'在同一sales范围逐步交付amount统计，币种字段为currency。');state=loop.context.analysis_state;rid=loop.context.turn_requirement_ids[0]
    scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))
    _ac25_unit_plan(loop,route,['sales'],[dict(requirement_id=rid,kind='measurement',label='Original sum',scope=scope)],'unit_sum')
    old_id,_,_=_p1_original_call(loop,route,'describe_dataset',dict(name='sales'));before=resolve_native_claims(session_id=loop.session_id,receipt_id=old_id)
    old=state.answer_requirements[0]['necessary_deliveries'][0];old_copy=json.loads(json.dumps(old));deliveries=[{'id':old['id']},dict(requirement_id=rid,kind='measurement',label='Appended mean',scope=dict(scope,quantity='mean'))]
    originals={p:p.read_bytes() for p in (cfg.sessions_resolved/loop.session_id).rglob('*.json') if p.parent.name in {'analysis_flow','tool_outputs'}}
    _ac25_unit_plan(loop,route,['sales'],deliveries,'unit_append')
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    after=resolve_native_claims(session_id=loop.session_id,receipt_id=old_id)
    (tmp_path/'unit-append-before-compute.json').write_text(json.dumps(dict(route=route,before=before,after=after,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None and all(p.read_bytes()==raw for p,raw in originals.items()) and old_copy in state.answer_requirements[0]['necessary_deliveries']
    assert any(c.get('target',{}).get('statistic')=='sum' and c['value']==30 and c['unit']=='CNY' for c in after)
    accepted={x['ref'] for x in answer['render_trace'] if x['kind']=='claim' and x['disposition']=='accepted'}
    assert any(c['id'] in accepted and c.get('target',{}).get('statistic')=='sum' and c['value']==30 for c in answer['source_snapshot']['claims'])
    assert answer['requirement_outcomes'][0]['status']!='answered'



@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same_field','different_field','second_mixed'])
def test_ac25_multisource_units_preserve_each_original_delivery(engine,tmp_path,route,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from tests.test_slice3_method_integrity import _joint_trust_original
    loop,cfg=engine;col='currency' if case=='same_field' else 'unit_b'
    _joint_trust_original(loop,'sales_a',pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY'])))
    _joint_trust_original(loop,'sales_b',pd.DataFrame({'amount':[1.,3.],col:['USD','CNY' if case=='second_mixed' else 'USD']}))
    request(loop,'分别交付sales_a和sales_b的amount同币合计，各用原单位字段；不合并金额。');state=loop.context.analysis_state;rid=loop.context.turn_requirement_ids[0]
    deliveries=[dict(requirement_id=rid,kind='measurement',label='Separate '+name,scope=dict(datasets=[name],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':unit}))) for name,unit in [('sales_a','currency'),('sales_b',col)]]
    _ac25_unit_plan(loop,route,['sales_a','sales_b'],deliveries,'units_original')
    receipts=[_p1_original_call(loop,route,'describe_dataset',dict(name=name))[0] for name in ['sales_a','sales_b']]
    originals={p:p.read_bytes() for p in (cfg.sessions_resolved/loop.session_id).rglob('*.json') if p.parent.name in {'analysis_flow','tool_outputs'}}
    _ac25_unit_plan(loop,route,['sales_a','sales_b'],[{'id':d['id']} for d in state.answer_requirements[0]['necessary_deliveries']],'units_replan')
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    (tmp_path/'unit-multisource.json').write_text(json.dumps(dict(route=route,case=case,receipts=receipts,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None and all(p.read_bytes()==raw for p,raw in originals.items())
    accepted={x['ref'] for x in answer['render_trace'] if x['kind']=='claim' and x['disposition']=='accepted'}
    sums=[c for c in answer['source_snapshot']['claims'] if c['id'] in accepted and c.get('target',{}).get('statistic')=='sum']
    assert any(c['scope']['dataset']=='sales_a' and c['value']==30 and c['unit']=='CNY' and c['basis_refs'][0]['receipt_id']==receipts[0] for c in sums)
    if case=='second_mixed':assert not any(c['scope']['dataset']=='sales_b' for c in sums) and answer['requirement_outcomes'][0]['status']!='answered' and '混合源单位' in body
    else:assert any(c['scope']['dataset']=='sales_b' and c['value']==4 and c['unit']=='USD' and c['basis_refs'][0]['receipt_id']==receipts[1] for c in sums) and answer['requirement_outcomes'][0]['status']=='answered'



class _Ac25MultiInitial(_NativeProductModel):
    def __init__(self,content,specs):
        super().__init__(content,'','describe_dataset',{'name':'sales_b'},specs,[('describe_dataset',{'name':'sales_a'})]);self.tickets={}
    def chat(self,messages,system='',**kw):
        from data_agent.llm.client import Response
        from data_agent.agent.publication.contracts import encode
        if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':
            return Response(text=encode(dict(intent_type='directed_analysis',requested_outputs=[dict(kind='result',exact_span=self.content,business_scope=dict(datasets=['sales_a','sales_b']))],upload_bindings=[dict(upload_id=t['upload_id'],dataset=n,relation='new',exact_span='将其命名为'+n) for n,t in self.tickets.items()])))
        result=super().chat(messages,system=system,**kw)
        for call in result.tool_calls:
            if call.name=='record_analysis_plan':call.arguments['plan_json']['method_plan'][0]['dataset_inputs']=['sales_a','sales_b']
        return result


class _Ac25Continue:
    def __init__(self,names,addition=None):
        self.names,self.addition=names,addition;self.content='沿用原统计目标及原单位字段，'+('追加同范围均值并实际计算。' if addition else '仅调整正式步骤，不重算两个来源。');self.calls=[];self.pre_compute=None
    def chat(self,messages,system='',**kw):
        from data_agent.llm.client import Response,ToolCall
        from data_agent.agent.publication.contracts import encode
        from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
        if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':
            requirements,_=json.JSONDecoder().raw_decode(messages[-1]['content'].partition('canonical_requirements: ')[2]);goal=next(r for r in requirements if r['semantic_kind']=='result' and r['lifecycle_status']=='active')
            return Response(text=encode(dict(intent_type='directed_analysis',requested_outputs=[dict(kind='result',exact_span=self.content,op='reuse',target_id=goal['id'])])))
        view=ScriptedClient._current_host_snapshot(messages,system)
        if not self.calls:
            goal=next(q for q in view['execution_targets'] if q['semantic_kind']=='result');deliveries=[{'id':d['id']} for d in goal['necessary_deliveries']]
            if self.addition:deliveries.append(dict(self.addition,requirement_id=goal['id'],label='Appended same-scope mean'))
            plan=dict(contract_version='stage3c0b.v2',requirement_revision=view['requirement_revision'],goal=self.content,visualization_strategy=[],method_plan=[dict(step_id='units_continued',goal=self.content,expected_output='Original unit-bound independent products',dataset_inputs=self.names,evidence_requirements=['original receipts'],required_deliveries=deliveries)])
            self.calls.append('record_analysis_plan');return Response(tool_calls=[ToolCall('units_continue_plan','record_analysis_plan',dict(plan_json=plan))])
        if self.addition and len(self.calls)==1:
            self.pre_compute=view;self.calls.append('describe_dataset');return Response(tool_calls=[ToolCall('units_continue_compute','describe_dataset',{'name':self.names[0]})])
        return Response(text=encode(dict(schema='answer_bindings.v2',snapshot_digest=view['snapshot_digest'],sections=[dict(requirement_ids=[q['id']],parts=[dict(kind='claim',ref=cid) for cid in q['claim_ids']]) for q in view['requirements'] if not q['withdrawn']])))
    def stream_chat_structured(self,*a,**kw):
        from data_agent.llm.client import StreamTextDelta,StreamComplete
        response=self.chat(*a,**kw)
        if response.text:yield StreamTextDelta(response.text)
        yield StreamComplete(response)


@pytest.mark.parametrize('case',['append','multisource'])
def test_ac25_normal_append_and_multisource_original_unit_continuity(engine,tmp_path,case):
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.publication.native import resolve_native_claims
    from data_agent.session.history import load_session
    from data_agent.tools.report import export_assistant_reply
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    names=['sales'] if case=='append' else ['sales_a','sales_b']
    frames=[pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']))]+([] if case=='append' else [pd.DataFrame(dict(amount=[1.,3.],unit_b=['USD','CNY']))])
    specs=[dict(kind='measurement',scope=dict(datasets=[name],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency' if i==0 else 'unit_b'}))) for i,name in enumerate(names)]
    content='加载附件将其命名为sales；沿原范围交付amount统计，币种字段currency，先交付合计。' if case=='append' else '加载两附件将其命名为sales_a；将其命名为sales_b；分别交付amount同币合计，不合并金额；各单位字段currency和unit_b。'
    initial=_NativeProductModel(content,names[0],'describe_dataset',{'name':names[0]},specs) if case=='append' else _Ac25MultiInitial(content,specs)
    loop,first=_joint_http_answer(engine,tmp_path,initial,names,frames,'units_continuity_'+case);_,cfg=engine;root=cfg.sessions_resolved/loop.session_id
    originals={p:p.read_bytes() for p in root.rglob('*.json') if p.parent.name in {'analyses','analysis_flow','tool_outputs'}}
    receipts=[r['id'] for r in loop.context.analysis_state.tool_receipts if r['tool_name']=='describe_dataset' and r.get('required_delivery_ids')]
    addition=dict(kind='measurement',scope=dict(specs[0]['scope'],quantity='mean')) if case=='append' else None;model=_Ac25Continue(names,addition);factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=factory()
    with app.test_client() as http:
        response=http.post('/api/chat',json=dict(session_id=loop.session_id,message=model.content));events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=http.get('/api/sessions/'+loop.session_id).get_json()
    loop=app.config['agent_manager'].get(loop.session_id)
    with use_agent_context(loop.context):
        saved=load_session(loop.session_id);message=next(m for m in reversed(saved['messages']) if m.get('answer_ref'));answer=read_answer(loop.session_id,message['answer_ref']);export=export_assistant_reply(loop.session_id,answer['body'],'md',reply_id=message['reply_id']);old_claims=[c for rid in receipts for c in resolve_native_claims(session_id=loop.session_id,receipt_id=rid)]
    app.config['agent_manager']=factory()
    with app.test_client() as http:cold=http.get('/api/sessions/'+loop.session_id).get_json()
    (tmp_path/'unit-continuity-normal.json').write_text(json.dumps(dict(case=case,first=first,answer=answer,old_claims=old_claims,pre_compute=model.pre_compute,calls=model.calls,events=events,refresh=refresh,cold=cold,export=export,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(p.read_bytes()==raw for p,raw in originals.items()) and first['source_snapshot']['plan_id']!=answer['source_snapshot']['plan_id']
    assert len([v for k,v in events if k=='turn_end'])==1 and next(v for k,v in events if k=='turn_end')['reply_content']==answer['body']
    assert not any(k in {'error','confirmation_required','suspended'} for k,v in events)
    assert any(m.get('answer_ref')==message['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
    assert export['status']=='exported' and answer['body'] in (root/'reports'/export['artifact_path'].split('/')[-1]).read_text(encoding='utf-8')
    assert any(c['scope']['dataset']==names[0] and c.get('target',{}).get('statistic')=='sum' and c['value']==30 and c['unit']=='CNY' for c in old_claims)
    if case=='append':
        visible=[dict(zip(model.pre_compute['claim_fields'],row)) for row in model.pre_compute['claims']]
        assert any(c['value']==30 and c['unit']=='CNY' for c in visible)
        assert model.calls==['record_analysis_plan','describe_dataset'] and answer['requirement_outcomes'][0]['status']=='answered' and '15.0 CNY' in answer['body']
    else:assert model.calls==['record_analysis_plan'] and '30.0 CNY' in answer['body'] and '混合源单位' in answer['body'] and answer['requirement_outcomes'][0]['status']!='answered'



def _ac25_window_inputs(case):
    names=['sales_a','sales_b'];column='currency' if case=='same_field' else 'unit_b'
    frames=[pd.DataFrame(dict(day=['2026-09-01','2026-09-02','2026-10-01'],amount=[10.,20.,900.],currency=['CNY','CNY','USD'])),pd.DataFrame({'day':['2026-10-01','2026-10-02','2026-09-01'],'amount':[2.,6.,800.],column:['USD','CNY' if case=='second_mixed' else 'USD','CNY']} )]
    args=[dict(name=n,date_col='day',metrics='amount',period_a=a+'~'+a,period_b=b+'~'+b) for n,a,b in [('sales_a','2026-09-01','2026-09-02'),('sales_b','2026-10-01','2026-10-02')]]
    specs=[dict(kind='measurement',scope=dict(datasets=[n],metrics=['amount'],quantity=q,parameters=dict(source_unit_columns={'amount':unit},comparison_date_col='day',period_a=a['period_a'],period_b=a['period_b']))) for n,unit,a in zip(names,['currency',column],args) for q in ['sum','difference','relative_change']]
    return names,frames,args,specs


def _ac25_assert_window_proofs(answer,receipts,mixed=False):
    accepted={t['ref'] for t in answer['render_trace'] if t['kind']=='claim' and t['disposition']=='accepted'}
    claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in accepted and c.get('target',{}).get('source_unit_proof')]
    for name,values,unit,rid in [('sales_a',[10.,20.,10.],'CNY',receipts[0]),('sales_b',[2.,6.,4.],'USD',receipts[1])]:
        local=[c for c in claims if c['scope']['dataset']==name]
        if mixed and name=='sales_b':assert not local;continue
        for path,value in zip(['period_a','period_b','diff'],values):
            matches=[c for c in local if c['basis_refs'][0]['result_path']==['metrics','amount','exact_aggregates',path]]
            assert len(matches)==1 and matches[0]['value']==value and matches[0]['unit']==unit
        for c in local:
            proof=c['target']['source_unit_proof'];assert proof['verified'] and proof['valid_rows']==2 and proof['units']==[unit] and proof['receipt_id']==rid
            assert c['basis_refs'][0]['receipt_id']==rid
            expected_start='2026-09-01' if name=='sales_a' else '2026-10-01';expected_end='2026-09-02' if name=='sales_a' else '2026-10-02'
            assert proof['scope']['datasets']==[name] and proof['scope']['parameters']['period_a']==expected_start+'~'+expected_start and proof['scope']['parameters']['period_b']==expected_end+'~'+expected_end
            assert proof['source_identity']==c['basis_refs'][0]['data_identities'][name]
        assert any(c['unit']=='percent' and c['value']==(100. if name=='sales_a' else 200.) for c in local)
    if mixed:assert '混合源单位' in answer['body'] and answer['requirement_outcomes'][0]['status']!='answered'
    else:assert '混合源单位' not in answer['body']


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same_field','different_field','second_mixed'])
def test_ac25_compare_multisource_windows_replan_keeps_exact_original_proofs(engine,tmp_path,route,case):
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from tests.test_slice3_method_integrity import _joint_trust_original
    loop,cfg=engine;names,frames,args,specs=_ac25_window_inputs(case)
    for n,f in zip(names,frames):_joint_trust_original(loop,n,f)
    request(loop,'分别比较两个来源各自明确日期窗口，按各自原单位列核同币金额，不合并来源或借窗口外币种。');state=loop.context.analysis_state;rid=loop.context.turn_requirement_ids[0]
    _ac25_unit_plan(loop,route,names,[dict(s,requirement_id=rid,label='Own windows '+str(i)) for i,s in enumerate(specs)],'multi_windows_original')
    receipts=[_p1_original_call(loop,route,'compare_periods',a)[0] for a in args]
    snap=snapshot_for_turn(loop);_,error=publish(loop,draft(snap));assert error is None;first=json.loads(json.dumps(loop._accepted_answer))
    originals={p:p.read_bytes() for p in (cfg.sessions_resolved/loop.session_id).rglob('*.json') if p.parent.name in {'analysis_flow','tool_outputs'}}
    _ac25_unit_plan(loop,route,names,[{'id':d['id']} for d in state.answer_requirements[0]['necessary_deliveries']],'multi_windows_replan')
    snap=snapshot_for_turn(loop);_,error=publish(loop,draft(snap));answer=loop._accepted_answer
    (tmp_path/'compare-multisource-original.json').write_text(json.dumps(dict(route=route,case=case,receipts=receipts,first=first,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None and all(p.read_bytes()==raw for p,raw in originals.items())
    assert first['source_snapshot']['plan_id']!=answer['source_snapshot']['plan_id']
    _ac25_assert_window_proofs(first,receipts,case=='second_mixed');_ac25_assert_window_proofs(answer,receipts,case=='second_mixed')



def test_ac25_normal_compare_multisource_window_proofs_survive_original_replan(engine,tmp_path):
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    from data_agent.tools.report import export_assistant_reply
    names,frames,args,specs=_ac25_window_inputs('second_mixed')
    content='加载两附件将其命名为sales_a；将其命名为sales_b；分别比较sales_a九月1/2日及sales_b十月1/2日amount，各单位来自currency和unit_b；交付原期值、金额差和相对变化，混币保留缺口，不合并来源。'
    class Compare(_Ac25MultiInitial):
        def __init__(self):
            super().__init__(content,specs);self.tool='compare_periods';self.args=args[1];self.preparatory_calls=[('compare_periods',args[0])]
    model=Compare();loop,first=_joint_http_answer(engine,tmp_path,model,names,frames,'ac25_multi_compare');_,cfg=engine;root=cfg.sessions_resolved/loop.session_id
    assert model.calls==['record_analysis_plan','compare_periods','compare_periods']
    originals={p:p.read_bytes() for p in root.rglob('*.json') if p.parent.name in {'analyses','analysis_flow','tool_outputs'}}
    receipts=[r['id'] for r in loop.context.analysis_state.tool_receipts if r['tool_name']=='compare_periods' and r.get('required_delivery_ids')]
    continued=_Ac25Continue(names);factory=lambda:AgentManager(client_factory=lambda **kw:continued,auxiliary_client_factory=lambda:continued);app=create_app();app.config['agent_manager']=factory()
    with app.test_client() as http:
        response=http.post('/api/chat',json=dict(session_id=loop.session_id,message=continued.content));events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=http.get('/api/sessions/'+loop.session_id).get_json()
    loop=app.config['agent_manager'].get(loop.session_id)
    with use_agent_context(loop.context):
        message=next(m for m in reversed(load_session(loop.session_id)['messages']) if m.get('answer_ref'));answer=read_answer(loop.session_id,message['answer_ref']);export=export_assistant_reply(loop.session_id,answer['body'],'md',reply_id=message['reply_id'])
    app.config['agent_manager']=factory()
    with app.test_client() as http:cold=http.get('/api/sessions/'+loop.session_id).get_json()
    (tmp_path/'compare-multisource-normal.json').write_text(json.dumps(dict(first=first,answer=answer,events=events,refresh=refresh,cold=cold,export=export,calls=continued.calls,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert continued.calls==['record_analysis_plan'] and all(p.read_bytes()==raw for p,raw in originals.items())
    assert first['source_snapshot']['plan_id']!=answer['source_snapshot']['plan_id']
    _ac25_assert_window_proofs(first,receipts,True);_ac25_assert_window_proofs(answer,receipts,True)
    ends=[v for k,v in events if k=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed' and ends[0]['reply_content']==answer['body']
    assert not any(k in {'error','confirmation_required','suspended'} for k,v in events)
    assert any(m.get('answer_ref')==message['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
    assert export['status']=='exported' and answer['body'] in (root/'reports'/export['artifact_path'].split('/')[-1]).read_text(encoding='utf-8')



@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['child_bound','ancestor_bound','composite','lookalike'])
def test_ac25_real_derived_lineage_and_composite_unit_scope_do_not_borrow_parent_authority(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.tools.registry import registry
    loop,cfg=engine;raw=tmp_path/'source.csv';raw.write_text('amount,currency\n10,CNY\n20,CNY\n',encoding='utf-8');loaded=load_data(str(raw),name='sales');assert 'Error:' not in loaded
    parent=loop.context.workspace.get_data_identity('sales');assert parent['source_origins']
    args=dict(name='sales',sort_by='amount',n=2,save_as='ranked');result=registry.get('top_n').func(**args) if route=='direct' else registry.execute('top_n',args).summary;result=json.loads(result);assert result.get('dataset')=='ranked',result
    child=loop.context.workspace.get_data_identity('ranked');assert parent['version_id'] in child['ancestor_version_ids'] and child['source_origins']==parent['source_origins']
    name='ranked'
    if case=='lookalike':
        loop.context.workspace.add('lookalike',loop.context.workspace.get('ranked').copy());name='lookalike';copy=loop.context.workspace.get_data_identity(name);assert parent['version_id'] not in copy['ancestor_version_ids'] and copy['fingerprint']==child['fingerprint']
    datasets=['ranked'] if case=='child_bound' else ['sales','ranked'] if case=='composite' else ['sales']
    spec=dict(kind='measurement',scope=dict(datasets=datasets,metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))
    request(loop,'仅对正式交付明确绑定的当前对象核原currency；父对象或复合范围不借派生回执授予新单位。',spec);rid,_,_=_p1_original_call(loop,route,'describe_dataset',dict(name=name));snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    (tmp_path/'source-unit-real-lineage.json').write_text(json.dumps(dict(route=route,case=case,parent=parent,child=child,receipt=rid,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None
    visible={x['ref'] for x in answer['render_trace'] if x['kind']=='claim' and x['disposition']=='accepted'};monetary=[c for c in answer['source_snapshot']['claims'] if c['id'] in visible and c.get('target',{}).get('statistic')=='sum']
    if case=='child_bound':
        assert len(monetary)==1 and monetary[0]['value']==30 and monetary[0]['unit']=='CNY' and monetary[0]['target']['source_unit_proof']['source_identity']==child
        assert answer['requirement_outcomes'][0]['status']=='answered'
    else:assert not monetary and answer['requirement_outcomes'][0]['status']!='answered'



def test_ac25_normal_real_derived_child_explicit_unit_scope_after_cold_restore(engine,tmp_path):
    from tests.test_slice3_method_integrity import _joint_http_answer
    from data_agent.llm.client import Response
    from data_agent.agent.publication.contracts import encode
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    args=dict(name='sales',sort_by='amount',n=2,save_as='ranked');spec=dict(kind='operation',scope=dict(datasets=['sales'],operation=dict(action='top_n',arguments=args)));content='加载附件将其命名为sales；仅按amount排序保存全部2条到ranked，保留原数据和派生关系。';initial=_NativeProductModel(content,'sales','top_n',args,[spec]);loop,first=_joint_http_answer(engine,tmp_path,initial,['sales'],[pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']))],'ac25_derived_child_normal');_,cfg=engine;root=cfg.sessions_resolved/loop.session_id;originals={p:p.read_bytes() for p in root.rglob('*.json') if p.parent.name in {'analyses','analysis_flow','tool_outputs'}}
    class Child(_NativeProductModel):
        def __init__(self):super().__init__('仅计算当前ranked的amount合计，源单位明确为currency，不能用父对象的计划代替。','','describe_dataset',dict(name='ranked'),[dict(kind='measurement',scope=dict(datasets=['ranked'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))]);self.public_results=[]
        def chat(self,messages,system='',**kw):
            if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return Response(text=encode(dict(intent_type='directed_analysis',requested_outputs=[dict(kind='result',exact_span=self.content,business_scope=dict(datasets=['ranked']))])))
            self.public_results=[m.get('content','') for m in messages if m.get('role')=='tool'];result=super().chat(messages,system=system,**kw)
            for call in result.tool_calls:
                if call.name=='record_analysis_plan':call.arguments['plan_json']['method_plan'][0]['dataset_inputs']=['ranked']
            return result
    model=Child();factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=factory()
    with app.test_client() as http:
        response=http.post('/api/chat',json=dict(session_id=loop.session_id,message=model.content));events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=http.get('/api/sessions/'+loop.session_id).get_json()
    saved=load_session(loop.session_id);last=next(m for m in reversed(saved['messages']) if m.get('answer_ref'));answer=read_answer(loop.session_id,last['answer_ref'])
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    with use_agent_context(app.config['agent_manager'].get(loop.session_id).context):export=export_assistant_reply(loop.session_id,answer['body'],'md',reply_id=last['reply_id'])
    app.config['agent_manager']=factory()
    with app.test_client() as http:cold=http.get('/api/sessions/'+loop.session_id).get_json()
    (tmp_path/'derived-child-normal.json').write_text(json.dumps(dict(first=first,answer=answer,events=events,refresh=refresh,cold=cold,export=export,calls=model.calls,public_results=model.public_results,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(p.read_bytes()==raw for p,raw in originals.items())
    assert answer['requirement_outcomes'][-1]['status']=='answered' and '30.0 CNY' in answer['body']
    ends=[v for k,v in events if k=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed' and ends[0]['reply_content']==answer['body']
    assert any(m.get('answer_ref')==last['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
    assert export['status']=='exported' and answer['body'] in (root/'reports'/export['artifact_path'].split('/')[-1]).read_text(encoding='utf-8')




@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('fault',[False,True])
def test_ac25_single_parent_derived_snapshot_is_atomic_before_success_receipt(engine,tmp_path,monkeypatch,route,fault):
    from data_agent.tools.registry import registry
    import data_agent.session.workspace as storage_module
    from tests.test_slice3_method_integrity import _joint_trust_original
    loop,cfg=engine;frame=pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']));_joint_trust_original(loop,'sales',frame);loop.context.workspace.persist_dataset(loop.session_id,'sales');loop.context.workspace.save_meta(loop.session_id)
    root=cfg.sessions_resolved/loop.session_id;before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()};read=storage_module._read_persisted_snapshot;observed=[]
    def verify(sid,name):
        if name=='ranked':
            observed.append(name)
            if fault:return None
        return read(sid,name)
    monkeypatch.setattr(storage_module,'_read_persisted_snapshot',verify);args=dict(name='sales',sort_by='amount',n=2,save_as='ranked');error=None;result=None
    try:
        call=registry.get('top_n').func(**args) if route=='direct' else registry.execute('top_n',args);result=json.loads(call if isinstance(call,str) else call.summary)
    except ValueError as exc:error=str(exc)
    (tmp_path/'single-parent-durable.json').write_text(json.dumps(dict(route=route,fault=fault,result=result,error=error,observed=observed,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert observed,'single-parent derived storage never validated a durable original'
    if fault:
        assert error or result.get('error') or result.get('error_type')
        assert not loop.context.workspace.exists('ranked') and {p:p.read_bytes() for p in root.rglob('*') if p.is_file()}==before
    else:
        assert not error and result.get('dataset')=='ranked';saved=read(loop.session_id,'ranked');assert saved is not None and saved[0]['data_identity']==loop.context.workspace.get_data_identity('ranked')
        assert saved[1].equals(loop.context.workspace.get('ranked')) and list(saved[1]['amount'])==[20.,10.]



@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['current','missing_receipt','changed_parent','missing_child_snapshot','contract_failure'])
def test_ac25_topn_current_contract_requires_owned_originals_and_never_inherits_method_roles(engine,tmp_path,monkeypatch,route,case):
    from tests.test_slice3_method_integrity import _joint_trust_original
    from data_agent.agent.artifact_refs import hydrate_refs
    from data_agent.tools import data_io
    loop,cfg=engine;frame=pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']));_joint_trust_original(loop,'sales',frame);loop.context.workspace.persist_dataset(loop.session_id,'sales');loop.context.workspace.save_meta(loop.session_id)
    args=dict(name='sales',sort_by='amount',n=2,save_as='ranked');spec=dict(kind='operation',scope=dict(datasets=['sales'],operation=dict(action='top_n',arguments=args)));request(loop,'将当前sales排序生成ranked，当前子合同须独立检查，不能继承父对象字段角色或方法就绪。',spec)
    original=data_io._record_trust_workflow;fired=[]
    def fail(**kw):
        result=original(**kw)
        if kw.get('dataset')=='ranked':fired.append(True);raise OSError('child contract committed then device unavailable')
        return result
    with monkeypatch.context() as m:
        if case=='contract_failure':m.setattr(data_io,'_record_trust_workflow',fail)
        rid,raw,summary=_p1_original_call(loop,route,'top_n',args)
    state=loop.context.analysis_state;refs=[r for r in state.dataset_contracts if r.get('dataset')=='ranked'];assert rid and raw.get('dataset')=='ranked'
    if case=='contract_failure':
        assert fired and not refs and loop.context.workspace._publication_data_identity('ranked')
        assert not any('trust_ranked_' in p.name for p in (cfg.sessions_resolved/loop.session_id).rglob('*.json'))
        return
    assert len(refs)==1 and refs[0]['source_binding']['producer_receipt_id']==rid
    child=loop.context.workspace.get_data_identity('ranked');root=cfg.sessions_resolved/loop.session_id
    if case=='missing_receipt':
        receipt=next(r for r in state.tool_receipts if r['id']==rid);source=root/receipt['detail_ref']['path'];assert source.resolve().is_relative_to(root.resolve());source.rename(source.with_suffix('.preserved-original'))
    elif case=='changed_parent':loop.context.workspace.add('sales',frame.assign(amount=[99.,99.]))
    elif case=='missing_child_snapshot':
        source=next(p for p in (root/'data').glob('ranked.*') if p.suffix in {'.pkl','.parquet'});source.rename(source.with_suffix(source.suffix+'.preserved-original'))
    current=hydrate_refs(refs,trust_records=True)[0];before=__import__('copy').deepcopy(state.to_dict())
    if case=='current':
        assert current['trust_resolution']['status']=='current' and current['row_count']==2 and current['grain']=='unknown'
        assert all(not values for values in current['field_roles'].values()) and current['source_binding']['data_identity']==child
        assert current['id']!=next(r for r in state.dataset_contracts if r.get('dataset')=='sales')['id']
    else:
        assert current['trust_resolution']['status']=='unassessed' and not loop.context.workspace._register_child_contract(rid) and state.to_dict()==before
    (tmp_path/'topn-contract-originals.json').write_text(json.dumps(dict(route=route,case=case,receipt_id=rid,child_identity=child,contract=current,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['select_drops_unit','merge_parent_scope','merge_composite_scope'])
def test_ac25_real_arbitrary_transform_and_multi_parent_scope_keep_unit_gap(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.tools.registry import registry
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.artifact_refs import verified_child_contract_producer
    loop,cfg=engine
    for name,frame in [('left',pd.DataFrame(dict(key=[1,2],amount=[10.,20.],currency=['CNY','CNY']))),('right',pd.DataFrame(dict(key=[1,2],amount_other=[2.,4.],currency_other=['USD','USD'])))]:
        path=tmp_path/(name+'.csv');frame.to_csv(path,index=False);assert 'Error:' not in load_data(str(path),name)
    parents={n:loop.context.workspace.get_data_identity(n) for n in ['left','right']}
    args=dict(name='left',operation='select',columns=['key','amount'],save_as='changed') if case=='select_drops_unit' else dict(name='left',operation='merge',other_name='right',merge_on='key',save_as='changed')
    result=registry.get('transform_data').func(**args) if route=='direct' else registry.execute('transform_data',args).summary;result=json.loads(result);assert result.get('dataset')=='changed',result
    child=loop.context.workspace.get_data_identity('changed');assert parents['left']['version_id'] in child['ancestor_version_ids']
    if case!='select_drops_unit':assert parents['right']['version_id'] in child['ancestor_version_ids'] and len(child['source_origins'])==2
    assert loop.context.workspace._publication_persisted_identity_matches('changed',child)
    assert not [c for c in loop.context.analysis_state.dataset_contracts if c.get('dataset')=='changed'], '118 must not silently expand beyond actual top_n'
    datasets=['changed'] if case=='select_drops_unit' else ['left'] if case=='merge_parent_scope' else ['left','right']
    scope=dict(datasets=datasets,metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}));request(loop,'当前变换的金额不能借父范围或多父复合范围的单位完成；缺原单位字段保留缺口。',dict(kind='measurement',scope=scope));rid,raw,_=_p1_original_call(loop,route,'describe_dataset',dict(name='changed'));snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    assert error is None and answer['requirement_outcomes'][0]['status']!='answered'
    selected={c for q in answer['source_snapshot']['requirements'] for c in q['claim_ids']};assert not any(c['id'] in selected and c['target'].get('statistic')=='sum' and c.get('unit') in {'CNY','USD'} for c in answer['source_snapshot']['claims'])
    assert not verified_child_contract_producer(loop.context,'changed',rid)
    (tmp_path/'arbitrary-multi-parent-unit.json').write_text(json.dumps(dict(route=route,case=case,parents=parents,child=child,transform=result,answer=answer,boundary='durable actual transform;not granted118 child contract or parent/composite monetary authority',Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')



def test_ac25_normal_multi_parent_merge_keeps_operation_rows_and_composite_unit_gap(engine,tmp_path):
    args=dict(name='sales_a',operation='merge',other_name='sales_b',merge_on='key',save_as='combined');content='加载两份附件，将其命名为sales_a和将其命名为sales_b；按key合并保存combined，同时保留各自原行数；多父复合金额没有单位运算证明，不能借父单位完成。'
    specs=[dict(kind='operation',scope=dict(datasets=['sales_a','sales_b'],operation=dict(action='transform_data',arguments=args))),dict(kind='measurement',scope=dict(datasets=['sales_a','sales_b'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))),*[dict(kind='measurement',scope=dict(datasets=[n],quantity='rows')) for n in ['sales_a','sales_b']]]
    model=_Ac25MultiInitial(content,specs);model.tool='transform_data';model.args=args;model.preparatory_calls=[('describe_dataset',dict(name=n)) for n in ['sales_a','sales_b']]
    frames=[pd.DataFrame(dict(key=[1,2],amount=[10.,20.],currency=['CNY','CNY'])),pd.DataFrame(dict(key=[1,2],amount_other=[2.,4.],currency_other=['USD','USD']))];loop,answer=_joint_http_answer(engine,tmp_path,model,['sales_a','sales_b'],frames,'ac25_multi_parent_normal')
    from data_agent.agent.context import use_agent_context
    with use_agent_context(loop.context):
        child=loop.context.workspace._publication_data_identity('combined');durable=loop.context.workspace._publication_persisted_identity_matches('combined',child)
    assert child and len(child['source_origins'])==2 and durable
    contracts=[c for c in loop.context.analysis_state.dataset_contracts if c.get('dataset')=='combined'];assert len(contracts)==1 and contracts[0]['source_binding']['producer_receipt_id'] in {r['id'] for r in loop.context.analysis_state.tool_receipts if r['tool_name']=='transform_data'}
    req=answer['source_snapshot']['requirements'][0];selected=set(req['claim_ids']);visible=[c for c in answer['source_snapshot']['claims'] if c['id'] in selected]
    assert answer['requirement_outcomes'][0]['status']=='partial' and req['effect_ids']
    assert {c['scope']['dataset'] for c in visible if c.get('target',{}).get('statistic')=='rows' and c['value']==2}=={'sales_a','sales_b'}
    assert not any(c.get('target',{}).get('statistic')=='sum' and c.get('unit') in {'CNY','USD'} for c in visible)
    (tmp_path/'ac25-multi-parent-normal.json').write_text(json.dumps(dict(answer=answer,child=child,calls=model.calls,Provider=0,boundary='original operation and independent rows delivered;composite units and arbitrary child contract not granted'),ensure_ascii=False,indent=2),encoding='utf-8')


def test_ac25_normal_select_preserved_amount_and_currency_current_child_after_cold_restore(engine,tmp_path):
    from tests.test_slice3_method_integrity import _joint_http_answer
    from data_agent.llm.client import Response
    from data_agent.agent.publication.contracts import encode
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    args=dict(name='sales',operation='select',columns=['amount','currency'],save_as='ranked');spec=dict(kind='operation',scope=dict(datasets=['sales'],operation=dict(action='transform_data',arguments=args)));content='加载附件将其命名为sales；仅选取amount与currency两列保存全部2条到ranked，保留原数据和派生关系。';initial=_NativeProductModel(content,'sales','transform_data',args,[spec]);loop,first=_joint_http_answer(engine,tmp_path,initial,['sales'],[pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']))],'ac25_select_contract_gap');_,cfg=engine;root=cfg.sessions_resolved/loop.session_id;originals={p:p.read_bytes() for p in root.rglob('*.json') if p.parent.name in {'analyses','analysis_flow','tool_outputs'}}
    class Child(_NativeProductModel):
        def __init__(self):super().__init__('仅计算当前ranked的amount合计，源单位明确为currency，不能用父对象的计划代替。','','describe_dataset',dict(name='ranked'),[dict(kind='measurement',scope=dict(datasets=['ranked'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'})))]);self.public_results=[]
        def chat(self,messages,system='',**kw):
            if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return Response(text=encode(dict(intent_type='directed_analysis',requested_outputs=[dict(kind='result',exact_span=self.content,business_scope=dict(datasets=['ranked']))])))
            self.public_results=[m.get('content','') for m in messages if m.get('role')=='tool'];result=super().chat(messages,system=system,**kw)
            for call in result.tool_calls:
                if call.name=='record_analysis_plan':call.arguments['plan_json']['method_plan'][0]['dataset_inputs']=['ranked']
            return result
    model=Child();factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=factory()
    with app.test_client() as http:
        response=http.post('/api/chat',json=dict(session_id=loop.session_id,message=model.content));events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=http.get('/api/sessions/'+loop.session_id).get_json()
    saved=load_session(loop.session_id);last=next(m for m in reversed(saved['messages']) if m.get('answer_ref'));answer=read_answer(loop.session_id,last['answer_ref'])
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    with use_agent_context(app.config['agent_manager'].get(loop.session_id).context):export=export_assistant_reply(loop.session_id,answer['body'],'md',reply_id=last['reply_id'])
    app.config['agent_manager']=factory()
    with app.test_client() as http:cold=http.get('/api/sessions/'+loop.session_id).get_json()
    (tmp_path/'derived-child-normal.json').write_text(json.dumps(dict(first=first,answer=answer,events=events,refresh=refresh,cold=cold,export=export,calls=model.calls,public_results=model.public_results,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(p.read_bytes()==raw for p,raw in originals.items())
    assert answer['requirement_outcomes'][-1]['status']=='answered' and '30.0 CNY' in answer['body']
    ends=[v for k,v in events if k=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed' and ends[0]['reply_content']==answer['body']
    assert any(m.get('answer_ref')==last['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
    assert export['status']=='exported' and answer['body'] in (root/'reports'/export['artifact_path'].split('/')[-1]).read_text(encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['current','missing_receipt','changed_parent','missing_child_snapshot','contract_failure'])
def test_ac25_select_current_contract_requires_owned_originals_and_independent_quality(engine,tmp_path,monkeypatch,route,case):
    from tests.test_slice3_method_integrity import _joint_trust_original
    from data_agent.agent.artifact_refs import hydrate_refs
    from data_agent.tools import data_io
    loop,cfg=engine;frame=pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY']));_joint_trust_original(loop,'sales',frame);loop.context.workspace.persist_dataset(loop.session_id,'sales');loop.context.workspace.save_meta(loop.session_id)
    args=dict(name='sales',operation='select',columns=['amount','currency'],save_as='ranked');spec=dict(kind='operation',scope=dict(datasets=['sales'],operation=dict(action='transform_data',arguments=args)));request(loop,'将当前sales排序生成ranked，当前子合同须独立检查，不能继承父对象字段角色或方法就绪。',spec)
    original=data_io._record_trust_workflow;fired=[]
    def fail(**kw):
        result=original(**kw)
        if kw.get('dataset')=='ranked':fired.append(True);raise OSError('child contract committed then device unavailable')
        return result
    with monkeypatch.context() as m:
        if case=='contract_failure':m.setattr(data_io,'_record_trust_workflow',fail)
        rid,raw,summary=_p1_original_call(loop,route,'transform_data',args)
    state=loop.context.analysis_state;refs=[r for r in state.dataset_contracts if r.get('dataset')=='ranked'];assert rid and raw.get('dataset')=='ranked'
    if case=='contract_failure':
        assert fired and not refs and loop.context.workspace._publication_data_identity('ranked')
        assert not any('trust_ranked_' in p.name for p in (cfg.sessions_resolved/loop.session_id).rglob('*.json'))
        return
    assert len(refs)==1 and refs[0]['source_binding']['producer_receipt_id']==rid
    child=loop.context.workspace.get_data_identity('ranked');root=cfg.sessions_resolved/loop.session_id
    if case=='missing_receipt':
        receipt=next(r for r in state.tool_receipts if r['id']==rid);source=root/receipt['detail_ref']['path'];assert source.resolve().is_relative_to(root.resolve());source.rename(source.with_suffix('.preserved-original'))
    elif case=='changed_parent':loop.context.workspace.add('sales',frame.assign(amount=[99.,99.]))
    elif case=='missing_child_snapshot':
        source=next(p for p in (root/'data').glob('ranked.*') if p.suffix in {'.pkl','.parquet'});source.rename(source.with_suffix(source.suffix+'.preserved-original'))
    current=hydrate_refs(refs,trust_records=True)[0];before=__import__('copy').deepcopy(state.to_dict())
    if case=='current':
        assert current['trust_resolution']['status']=='current' and current['row_count']==2 and current['grain']=='unknown'
        assert all(not values for values in current['field_roles'].values()) and current['source_binding']['data_identity']==child
        assert current['id']!=next(r for r in state.dataset_contracts if r.get('dataset')=='sales')['id']
    else:
        assert current['trust_resolution']['status']=='unassessed' and not loop.context.workspace._register_child_contract(rid) and state.to_dict()==before
    (tmp_path/'select-contract-originals.json').write_text(json.dumps(dict(route=route,case=case,receipt_id=rid,child_identity=child,contract=current,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')



def _ac25_remaining_transform_input(case):
    frame=pd.DataFrame(dict(key=[1,2,3,4],day=pd.date_range('2026-09-01',periods=4),segment=['A','B','A','B'],amount=[10.,20.,30.,40.],currency=['CNY','CNY','USD','USD']))
    names=['sales'];frames=[frame];metric='amount';unit='currency';extra={}
    if case=='filter':operation='filter';extra=dict(condition='amount >= 30')
    elif case=='sort':operation='sort';extra=dict(sort_by=['amount'],ascending=False)
    elif case=='rename':operation='rename';extra=dict(rename_mapping={'amount':'gross','currency':'ccy'});metric='gross';unit='ccy'
    elif case=='group':operation='group_aggregate';extra=dict(group_by=['currency'],aggregations=[dict(column='amount',functions=['sum'])]);metric='amount_sum'
    elif case=='resample':operation='resample';extra=dict(date_col='day',freq='D',resample_agg={'amount':'sum'})
    elif case=='pivot_wide':operation='pivot';extra=dict(pivot_index='currency',pivot_columns='segment',pivot_values='amount');metric='A'
    elif case=='pivot_long':operation='pivot';extra=dict(melt_id_vars=['currency'],melt_value_vars=['amount']);metric='value'
    else:
        assert case=='merge';operation='merge';extra=dict(other_name='costs',merge_on='key',merge_how='inner');names.append('costs');frames.append(pd.DataFrame(dict(key=[2,2,4],cost=[1.,2.,3.],cost_currency=['CNY','USD','USD'])))
    return names,frames,dict(name='sales',operation=operation,save_as='current_child',**extra),metric,unit


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['filter','sort','rename','group','resample','pivot_wide','pivot_long','merge'])
def test_ac25_remaining_actual_transform_current_child_contract_and_own_unit_scope(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.artifact_refs import hydrate_refs,verified_child_contract_producer
    from data_agent.agent.publication.native import resolve_operation_effect
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;names,frames,args,metric,unit=_ac25_remaining_transform_input(case)
    for name,frame in zip(names,frames):
        path=tmp_path/(name+'.csv');frame.to_csv(path,index=False);assert 'Error:' not in load_data(str(path),name)
    request(loop,'执行具名变换，当前子对象的结构与质量需独立核定；父单位和复合范围不能自动承接。',dict(kind='operation',scope=dict(datasets=names,operation=dict(action='transform_data',arguments=args))));rid,raw,_=_p1_original_call(loop,route,'transform_data',args);state=loop.context.analysis_state;child=loop.context.workspace.get_data_identity('current_child');effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid);assert effect and effect['object']['identity']==child and set(effect['before']['source_data_identities'])==set(names)
    assert loop.context.workspace._publication_persisted_identity_matches('current_child',child)
    refs=[c for c in state.dataset_contracts if c.get('dataset')=='current_child'];verified=verified_child_contract_producer(loop.context,'current_child',rid)
    (tmp_path/'remaining-transform-contract.json').write_text(json.dumps(dict(case=case,route=route,operation=args,original=raw,effect=effect,child=child,contracts=refs,verified=verified,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert verified and len(refs)==1,'Actual current child is durable and owned, but its producer cannot register an independent current contract'
    contract=hydrate_refs(refs,trust_records=True)[0];assert contract['row_count']==raw['rows'] and contract['grain']=='unknown' and all(not values for values in contract['field_roles'].values())
    specs=[dict(kind='measurement',scope=dict(datasets=['current_child'],metrics=[metric],quantity='sum',parameters=dict(source_unit_columns={metric:unit}))),dict(kind='measurement',scope=dict(datasets=['current_child'],quantity='rows'))];request(loop,'仅计算明确当前子对象的原金额与行数，不合并单位、不继承父方法；单位缺列或混合仅相关金额保留缺口。',specs);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['current_child'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'remaining_'+case)
    receipt,_,_=_p1_original_call(loop,route,'describe_dataset',dict(name='current_child'));snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;assert error is None
    selected={cid for q in answer['source_snapshot']['requirements'] for cid in q['claim_ids']};claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in selected];assert any(c['value']==raw['rows'] and c['target'].get('statistic')=='rows' for c in claims)
    monetary=[c for c in claims if c.get('target',{}).get('metric')==metric and c['target'].get('statistic')=='sum']
    if case=='filter':assert len(monetary)==1 and monetary[0]['value']==70 and monetary[0]['unit']=='USD'
    else:assert not monetary and answer['requirement_outcomes'][-1]['status']!='answered'
    (tmp_path/'remaining-transform-unit.json').write_text(json.dumps(dict(case=case,route=route,contract=contract,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('case',['sort','merge','merge_mixed'])
def test_ac25_normal_other_transform_cold_current_child_units_remain_independent(engine,tmp_path,case):
    from data_agent.llm.client import Response
    from data_agent.agent.publication.contracts import encode
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    names=['sales'] if case=='sort' else ['sales_a','sales_b'];frames=[pd.DataFrame(dict(key=[1,2],amount=[10.,20.],currency=['CNY','CNY']))]+([] if case=='sort' else [pd.DataFrame(dict(key=[1,2],cost=[2.,4.],cost_currency=['USD','CNY' if case=='merge_mixed' else 'USD']))]);args=dict(name=names[0],operation='sort',sort_by=['amount'],ascending=False,save_as='current_child') if case=='sort' else dict(name='sales_a',operation='merge',other_name='sales_b',merge_on='key',save_as='current_child');spec=dict(kind='operation',scope=dict(datasets=names,operation=dict(action='transform_data',arguments=args)));content=('加载附件将其命名为sales；' if case=='sort' else '加载两附件，将其命名为sales_a和将其命名为sales_b；')+'按明确参数生成current_child，先保留实际变换原件和来源。'
    if case=='sort':initial=_NativeProductModel(content,'sales','transform_data',args,[spec])
    else:initial=_Ac25MultiInitial(content,[spec]);initial.tool='transform_data';initial.args=args;initial.preparatory_calls=[('describe_dataset',dict(name=n)) for n in names]
    loop,first=_joint_http_answer(engine,tmp_path,initial,names,frames,'other_child_'+case);_,cfg=engine;root=cfg.sessions_resolved/loop.session_id;originals={p:p.read_bytes() for p in root.rglob('*.json') if p.parent.name in {'analyses','analysis_flow','tool_outputs'}};pairs=[('amount','currency')]+([] if case=='sort' else [('cost','cost_currency')])
    class Child(_NativeProductModel):
        def __init__(self):super().__init__('仅核当前current_child的amount，单位字段currency；'+('同时独立核cost，单位字段cost_currency，不合并两种金额。' if case!='sort' else '不借父范围或父合同替代。'),'','describe_dataset',dict(name='current_child'),[dict(kind='measurement',scope=dict(datasets=['current_child'],metrics=[metric],quantity='sum',parameters=dict(source_unit_columns={metric:unit}))) for metric,unit in pairs]);self.public_results=[]
        def chat(self,messages,system='',**kw):
            if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return Response(text=encode(dict(intent_type='directed_analysis',requested_outputs=[dict(kind='result',exact_span=self.content,business_scope=dict(datasets=['current_child']))])))
            self.public_results=[m.get('content','') for m in messages if m.get('role')=='tool'];response=super().chat(messages,system=system,**kw)
            for call in response.tool_calls:
                if call.name=='record_analysis_plan':call.arguments['plan_json']['method_plan'][0]['dataset_inputs']=['current_child']
            return response
    model=Child();factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=factory()
    with app.test_client() as http:
        response=http.post('/api/chat',json=dict(session_id=loop.session_id,message=model.content));events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=http.get('/api/sessions/'+loop.session_id).get_json()
    last=next(m for m in reversed(load_session(loop.session_id)['messages']) if m.get('answer_ref'));answer=read_answer(loop.session_id,last['answer_ref'])
    with use_agent_context(app.config['agent_manager'].get(loop.session_id).context):export=export_assistant_reply(loop.session_id,answer['body'],'md',reply_id=last['reply_id'])
    app.config['agent_manager']=factory()
    with app.test_client() as http:cold=http.get('/api/sessions/'+loop.session_id).get_json()
    (tmp_path/'other-transform-cold-normal.json').write_text(json.dumps(dict(case=case,first=first,answer=answer,events=events,refresh=refresh,cold=cold,export=export,calls=model.calls,public_results=model.public_results,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(p.read_bytes()==raw for p,raw in originals.items())
    assert '30.0 CNY' in answer['body']
    assert answer['requirement_outcomes'][-1]['status']==('partial' if case=='merge_mixed' else 'answered')
    if case=='merge_mixed':assert '混合源单位' in answer['body'] and '6.0 USD' not in answer['body']
    if case=='merge':assert '6.0 USD' in answer['body'] and '36.0' not in answer['body']
    ends=[v for k,v in events if k=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed' and ends[0]['reply_content']==answer['body']
    assert any(m.get('answer_ref')==last['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
    assert export['status']=='exported' and answer['body'] in (root/'reports'/export['artifact_path'].split('/')[-1]).read_text(encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
def test_ac25_actual_auto_named_transform_child_contract_uses_original_effect_target(engine,tmp_path,route):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.native import resolve_operation_effect
    loop,cfg=engine;path=tmp_path/'auto.csv';pd.DataFrame(dict(amount=[10.,20.],currency=['CNY','CNY'])).to_csv(path,index=False);load_data(str(path),'sales');args=dict(name='sales',operation='sort',sort_by=['amount'],ascending=False);request(loop,'排序并保留工具实际自动命名的新表，其后独立核当前子对象，不凭模型自报名字。',dict(kind='operation',scope=dict(datasets=['sales'],operation=dict(action='transform_data',arguments=args))));rid,raw,_=_p1_original_call(loop,route,'transform_data',args);effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid);target=raw['dataset'];identity=loop.context.workspace.get_data_identity(target);assert effect['object']['name']==target and effect['object']['identity']==identity and loop.context.workspace._publication_persisted_identity_matches(target,identity)
    refs=[c for c in loop.context.analysis_state.dataset_contracts if c.get('dataset')==target];(tmp_path/'auto-child-contract.json').write_text(json.dumps(dict(route=route,target=target,receipt_id=rid,effect=effect,contracts=refs,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8');assert len(refs)==1 and refs[0]['source_binding']['producer_receipt_id']==rid


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('fault',['second_parent_changed','second_parent_snapshot_missing','original_permission_changed','child_changed'])
def test_ac25_multi_parent_current_contract_rechecks_all_originals(engine,tmp_path,route,fault):
    from copy import deepcopy
    from data_agent.tools.data_io import load_data
    from data_agent.agent.artifact_refs import hydrate_refs,verified_child_contract_producer
    loop,cfg=engine;names,frames,args,_,_=_ac25_remaining_transform_input('merge')
    for name,frame in zip(names,frames):
        path=tmp_path/(name+'.csv');frame.to_csv(path,index=False);load_data(str(path),name)
    request(loop,'真实双父原件核定当前子合同；任一父版本、原权限或子快照不能核时只保原记录。',dict(kind='operation',scope=dict(datasets=names,operation=dict(action='transform_data',arguments=args))));rid,_,_=_p1_original_call(loop,route,'transform_data',args);state=loop.context.analysis_state;refs=[c for c in state.dataset_contracts if c.get('dataset')=='current_child'];assert len(refs)==1;root=cfg.sessions_resolved/loop.session_id
    if fault=='second_parent_changed':loop.context.workspace.add('costs',frames[1].assign(cost=[99.,99.,99.]))
    elif fault=='second_parent_snapshot_missing':
        p=next(p for p in (root/'data').glob('costs.*') if p.suffix in {'.pkl','.parquet'});p.rename(p.with_suffix(p.suffix+'.preserved-original'))
    elif fault=='original_permission_changed':next(r for r in state.tool_receipts if r['id']==rid)['operation_binding']['permission_scope']='another_permission'
    else:loop.context.workspace.add('current_child',loop.context.workspace.get('current_child').assign(amount=999.))
    before=deepcopy(state.to_dict());files={p:p.read_bytes() for p in root.rglob('*') if p.is_file()};view=hydrate_refs(refs,trust_records=True)[0]
    assert view['trust_resolution']['status']=='unassessed' and not verified_child_contract_producer(loop.context,'current_child',rid) and not loop.context.workspace._register_child_contract(rid)
    assert state.to_dict()==before and all(p.read_bytes()==raw for p,raw in files.items())
    (tmp_path/'multi-parent-original-boundary.json').write_text(json.dumps(dict(route=route,fault=fault,contract=view,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['group','formula','parent','composite'])
def test_ac25_actual_merged_comparison_cannot_borrow_simple_or_parent_unit_proof(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine
    frames=[pd.DataFrame(dict(key=[1,2],day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY'],segment=['A','A'],orders=[1.,1.])),pd.DataFrame(dict(key=[1,2],cost=[2.,4.],cost_currency=['USD','USD']))]
    for name,frame in zip(['sales','costs'],frames):
        path=tmp_path/(name+'.csv');frame.to_csv(path,index=False);load_data(str(path),name)
    args=dict(name='sales',operation='merge',other_name='costs',merge_on='key',save_as='current_child');request(loop,'按明确key生成真实双父当前子表；独立当前合同不证明复合单位代数。',dict(kind='operation',scope=dict(datasets=['sales','costs'],operation=dict(action='transform_data',arguments=args))));_p1_original_call(loop,route,'transform_data',args)
    metric='cost_per_order' if case=='formula' else 'amount';formulas={metric:dict(operator='ratio_of_sums',numerator='cost',denominator='orders')} if case=='formula' else {};dimensions=['segment'] if case=='group' else [];names=['sales'] if case=='parent' else ['sales','costs'] if case=='composite' else ['current_child'];a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';params=dict(source_unit_columns={metric:'cost_currency' if case=='formula' else 'currency'},comparison_date_col='day',comparison_dimensions=dimensions,comparison_formulas=formulas,period_a=a,period_b=b)
    specs=[dict(kind='measurement',scope=dict(datasets=names,metrics=[metric],quantity='sum',parameters=params)),dict(kind='measurement',scope=dict(datasets=['current_child'],quantity='rows'))];request(loop,'核指定双窗口的当前子表；分组、公式与父/复合范围不借简单单位合同，独立当前行数仍保留。',specs);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,list(dict.fromkeys(['current_child',*names])),[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'compound_'+case)
    _p1_original_call(loop,route,'describe_dataset',dict(name='current_child'));rid,raw,_=_p1_original_call(loop,route,'compare_periods',dict(name='current_child',date_col='day',metrics=metric,dimensions=','.join(dimensions),metric_formulas=formulas,period_a=a,period_b=b));assert not raw.get('error'),raw
    item=raw['comparisons'][0][metric] if case=='group' else raw['metrics'][metric];exact=item['exact_aggregates'];assert set(exact.values())==({2.,4.} if case=='formula' else {10.,20.}),exact
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;assert error is None
    assert (answer['requirement_outcomes'][-1]['status']=='answered')==(case=='group')
    target=next(q for q in answer['source_snapshot']['requirements'] if q['id']==goal);selected=[c for c in answer['source_snapshot']['claims'] if c['id'] in target['claim_ids']];assert any(c['target'].get('statistic')=='rows' and c['value']==2 for c in selected)
    monetary=[c for c in selected if c.get('unit') in {'CNY','USD'} and c.get('target',{}).get('metric')==metric]
    (tmp_path/'122-group-proof-detail.json').write_text(json.dumps(dict(receipt_id=rid,workspace_identity=loop.context.workspace._publication_data_identity('current_child'),monetary=monetary,answer=answer),ensure_ascii=False,indent=2),encoding='utf-8')
    if case=='group':
        assert {c['value'] for c in monetary}=={10.,20.} and all(c['unit']=='CNY' for c in monetary)
        assert all(c['scope']['dataset']=='current_child' and c['target']['source_unit_proof']['source_identity']==loop.context.workspace._publication_data_identity('current_child') and all(b['receipt_id']==rid and b['tool_name']=='compare_periods' for b in c['basis_refs']) for c in monetary)
    else:assert not monetary
    (tmp_path/'merged-comparison-unit-boundary.json').write_text(json.dumps(dict(route=route,case=case,receipt_id=rid,result=raw,answer=answer,boundary='122 current-child grouped sum one original currency' if case=='group' else 'Actual arithmetic retained;formula/parent/composite unit authority remains unassessed,not conversion or algebra',Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same','mixed','missing','outside_window'])
def test_ac25_grouped_original_sum_and_current_single_source_unit_applicability(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-01','2026-09-02','2026-09-02'],segment=['A','B','A','B'],amount=[10.,100.,20.,200.],currency=['CNY','USD' if case=='mixed' else 'CNY','CNY','USD' if case=='mixed' else 'CNY']));
    if case=='missing':frame.loc[1,'currency']=None
    if case=='outside_window':frame=pd.concat([frame,pd.DataFrame(dict(day=['2026-09-03'],segment=['A'],amount=[999.],currency=['USD']))],ignore_index=True)
    path=tmp_path/'groups.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';params=dict(source_unit_columns={'amount':'currency'},comparison_date_col='day',comparison_dimensions=['segment'],comparison_formulas={},comparison_output='comparison',period_a=a,period_b=b);specs=[dict(kind='table',scope=dict(datasets=['sales'],metrics=['amount'],parameters=params)),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))];request(loop,'按segment分别交付两个指定日历窗口的amount原合计和差；单位字段currency，只有实际比较范围整体同币时核简单源单位，混币不相加、不换汇。',specs);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'group_units_'+case);_p1_original_call(loop,route,'describe_dataset',dict(name='sales'));rid,raw,_=_p1_original_call(loop,route,'compare_periods',dict(name='sales',date_col='day',metrics='amount',dimensions='segment',period_a=a,period_b=b))
    expected={'A':dict(a=10.,b=20.,diff=10.),'B':dict(a=100.,b=200.,diff=100.)};assert {row['dimension']:row['amount']['exact_aggregates'] for row in raw['comparisons']}==expected
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;assert error is None;target=next(q for q in answer['source_snapshot']['requirements'] if q['id']==goal);selected=[c for c in answer['source_snapshot']['claims'] if c['id'] in target['claim_ids']];assert any(c['value']==len(frame) and c['target'].get('statistic')=='rows' for c in selected)
    (tmp_path/'group-sum-unit-applicability.json').write_text(json.dumps(dict(route=route,case=case,original=raw,answer=answer,expected_original=expected,boundary='Same original grouped sum;proposed only one current source unit over full actual comparison range,no per-group currency algebra',Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    if case in {'same','outside_window'}:assert answer['requirement_outcomes'][-1]['status']=='answered' and any(c['target'].get('source_unit_proof',{}).get('units')==['CNY'] for c in selected)
    else:assert answer['requirement_outcomes'][-1]['status']!='answered' and not any(c['target'].get('source_unit_proof',{}).get('verified') for c in selected)


def test_ac25_normal_grouped_single_currency_original_table_save_cold_exact_export(engine,tmp_path):
    content='加载附件将其命名为sales；按segment分别比较2026-09-01至2026-09-01与2026-09-02至2026-09-02两个含首尾日期窗口的amount原合计与差值；原单位来自currency，实际范围整体同币才核，保留独立行数。';a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';params=dict(source_unit_columns={'amount':'currency'},comparison_date_col='day',comparison_dimensions=['segment'],comparison_formulas={},comparison_output='comparison',period_a=a,period_b=b);specs=[dict(kind='table',scope=dict(datasets=['sales'],metrics=['amount'],parameters=params)),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))];frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-01','2026-09-02','2026-09-02'],segment=['A','B','A','B'],amount=[10.,100.,20.,200.],currency=['CNY']*4));model=_NativeProductModel(content,'sales','compare_periods',dict(name='sales',date_col='day',metrics='amount',dimensions='segment',period_a=a,period_b=b),specs,preparatory_calls=[('describe_dataset',dict(name='sales'))]);loop,answer=_joint_http_answer(engine,tmp_path,model,['sales'],[frame],'grouped_source_units');selected={cid for q in answer['source_snapshot']['requirements'] for cid in q['claim_ids']};claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in selected];tables=[c for c in claims if c['basis_refs'][0]['result_path']==['comparisons']];assert len(tables)==1;claim=tables[0]
    assert {row['dimension']:row['amount']['exact_aggregates'] for row in claim['value']}=={'A':dict(a=10.,b=20.,diff=10.),'B':dict(a=100.,b=200.,diff=100.)}
    assert claim['target']['source_unit_proof']['units']==['CNY'] and claim['target']['source_unit_proof']['valid_rows']==4 and '核定源单位：CNY' in answer['body']
    assert answer['requirement_outcomes'][0]['status']=='answered' and any(c['value']==4 and c['target'].get('statistic')=='rows' for c in claims)
    (tmp_path/'normal-grouped-source-unit.json').write_text(json.dumps(dict(answer=answer,calls=model.calls,Provider=0,boundary='Original grouped sums;one source label over actual whole range;not unit algebra'),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same','separate_units','second_mixed'])
def test_ac25_actual_multi_metric_whole_table_keeps_each_original_unit_and_independent_amount(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY'],cost=[2.,4.],cost_currency=['CNY','CNY'] if case=='same' else ['USD','USD'] if case=='separate_units' else ['USD','CNY']));path=tmp_path/'multi.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';params=dict(source_unit_columns={'amount':'currency','cost':'cost_currency'},comparison_date_col='day',comparison_dimensions=[],comparison_formulas={},comparison_output='comparison',period_a=a,period_b=b);specs=[dict(kind='table',scope=dict(datasets=['sales'],metrics=['amount','cost'],parameters=params)),dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))];request(loop,'交付两个指定窗口amount与cost的完整原表，逐指标源单位分别来自currency和cost_currency，不能给整表套单一币种；同时独立交付amount合计及行数，相关单位失败不得抹掉独立结果。',specs);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'multi_units_'+case);_p1_original_call(loop,route,'describe_dataset',dict(name='sales'));rid,raw,_=_p1_original_call(loop,route,'compare_periods',dict(name='sales',date_col='day',metrics='amount,cost',period_a=a,period_b=b));expected={'amount':dict(period_a=10.,period_b=20.,diff=10.),'cost':dict(period_a=2.,period_b=4.,diff=2.)};assert {m:r['exact_aggregates'] for m,r in raw['metrics'].items()}==expected
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;assert error is None;target=next(q for q in answer['source_snapshot']['requirements'] if q['id']==goal);claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in target['claim_ids']];assert any(c['value']==2 and c['target'].get('statistic')=='rows' for c in claims);assert any(c['value']==30 and c['unit']=='CNY' and c['target'].get('metric')=='amount' for c in claims)
    tables=[c for c in claims if c['basis_refs'][0]['receipt_id']==rid and c['basis_refs'][0]['result_path']==['metrics']]
    (tmp_path/'multi-metric-original-unit.json').write_text(json.dumps(dict(case=case,route=route,original=raw,answer=answer,tables=tables,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    if case=='second_mixed':assert not tables and answer['requirement_outcomes'][-1]['status']!='answered'
    else:
        assert len(tables)==1 and tables[0]['value']==raw['metrics'] and answer['requirement_outcomes'][-1]['status']=='answered'
        assert 'amount' in body and 'cost' in body and 'CNY' in body and (case=='same' or 'USD' in body)


def test_ac25_normal_multi_metric_original_table_and_separate_units_save_cold_export(engine,tmp_path):
    a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';params=dict(source_unit_columns={'amount':'currency','cost':'cost_currency'},comparison_date_col='day',comparison_dimensions=[],comparison_formulas={},comparison_output='comparison',period_a=a,period_b=b);specs=[dict(kind='table',scope=dict(datasets=['sales'],metrics=['amount','cost'],parameters=params)),dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))];content='加载附件将其命名为sales；交付2026-09-01至2026-09-01与2026-09-02至2026-09-02原amount/cost完整比较表；amount单位currency、cost单位cost_currency，分别呈现，不把两币相加；独立amount合计与行数保留。';frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY'],cost=[2.,4.],cost_currency=['USD','USD']));model=_NativeProductModel(content,'sales','compare_periods',dict(name='sales',date_col='day',metrics='amount,cost',period_a=a,period_b=b),specs,preparatory_calls=[('describe_dataset',dict(name='sales'))]);loop,answer=_joint_http_answer(engine,tmp_path,model,['sales'],[frame],'multi_metric_units');target=answer['source_snapshot']['requirements'][0];selected=[c for c in answer['source_snapshot']['claims'] if c['id'] in target['claim_ids']];tables=[c for c in selected if c['basis_refs'][0]['result_path']==['metrics']];assert len(tables)==1 and answer['requirement_outcomes'][0]['status']=='answered';assert tables[0]['value']['amount']['exact_aggregates']==dict(period_a=10.,period_b=20.,diff=10.) and tables[0]['value']['cost']['exact_aggregates']==dict(period_a=2.,period_b=4.,diff=2.);assert 'CNY' in answer['body'] and 'USD' in answer['body'] and any(c['value']==30 and c['unit']=='CNY' for c in selected) and any(c['value']==2 and c['target'].get('statistic')=='rows' for c in selected)
    (tmp_path/'normal-multi-metric-units.json').write_text(json.dumps(dict(answer=answer,calls=model.calls,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same_unit','different_units','zero_denominator'])
def test_ac25_actual_formula_cannot_borrow_output_source_label_for_operand_unit_algebra(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY'],cost=[0.,4.] if case=='zero_denominator' else [2.,4.],cost_currency=['USD','USD'] if case=='different_units' else ['CNY','CNY']));path=tmp_path/'formula.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';formula={'amount_per_cost':dict(operator='ratio_of_sums',numerator='amount',denominator='cost')};params=dict(source_unit_columns={'amount_per_cost':'currency'},comparison_date_col='day',comparison_dimensions=[],comparison_formulas=formula,comparison_output='comparison',period_a=a,period_b=b);specs=[dict(kind='table',scope=dict(datasets=['sales'],metrics=['amount_per_cost'],parameters=params)),dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum',parameters=dict(source_unit_columns={'amount':'currency'}))),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))];request(loop,'只核原两窗口amount合计除以cost合计，不允许从输出别名或一个currency列推定分子分母单位；未知单位关系保留缺口，独立amount与行数继续。',specs);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'formula_old_label_'+case);_p1_original_call(loop,route,'describe_dataset',dict(name='sales'));rid,raw,_=_p1_original_call(loop,route,'compare_periods',dict(name='sales',date_col='day',metrics='amount_per_cost',metric_formulas=formula,period_a=a,period_b=b));exact=raw['metrics']['amount_per_cost']['exact_aggregates'];assert exact==dict(period_a=None if case=='zero_denominator' else 5.,period_b=5.,diff=None if case=='zero_denominator' else 0.)
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;assert error is None and answer['requirement_outcomes'][-1]['status']!='answered';target=next(q for q in answer['source_snapshot']['requirements'] if q['id']==goal);claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in target['claim_ids']];assert any(c['value']==30 and c['unit']=='CNY' for c in claims) and any(c['value']==2 and c['target'].get('statistic')=='rows' for c in claims);assert not any(c['basis_refs'][0]['receipt_id']==rid and c.get('target',{}).get('source_unit_proof') for c in claims)
    (tmp_path/'formula-original-unit-applicability.json').write_text(json.dumps(dict(case=case,route=route,original=raw,answer=answer,Provider=0,boundary='Actual ratio numeric contract unchanged;output label mapping is not a two-operand unit contract'),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same','different','missing','zero','current_child','parent','composite','wrong_formula'])
def test_ac25_explicit_original_ratio_operand_units_keep_exact_numeric_and_scope(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;child=case in {'current_child','parent','composite'}
    frame=pd.DataFrame(dict(key=[1,2],day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY'],cost=[0.,4.] if case=='zero' else [2.,4.],cost_currency=['USD','USD'] if case=='different' else ['CNY',None] if case=='missing' else ['CNY','CNY']))
    path=tmp_path/'operand.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');name='sales'
    if child:
        path2=tmp_path/'costs.csv';frame[['key','cost','cost_currency']].to_csv(path2,index=False);load_data(str(path2),'costs')
        # Keep two distinct actual parents without duplicate operand columns.
        path3=tmp_path/'left.csv';frame.drop(columns=['cost','cost_currency']).to_csv(path3,index=False);load_data(str(path3),'left')
        args=dict(name='left',operation='merge',other_name='costs',merge_on='key',save_as='current_child');request(loop,'按key生成当前双父子表，不继承父单位或范围。',dict(kind='operation',scope=dict(datasets=['left','costs'],operation=dict(action='transform_data',arguments=args))));_p1_original_call(loop,route,'transform_data',args);name='current_child'
    a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';formula={'amount_per_cost':dict(operator='ratio_of_sums',numerator='amount',denominator='cost')};names=['left'] if case=='parent' else ['left','costs'] if case=='composite' else [name]
    params=dict(formula_unit_columns={'amount_per_cost':dict(numerator='currency',denominator='cost_currency')},comparison_date_col='day',comparison_dimensions=[],comparison_formulas=formula,comparison_output='comparison',period_a=a,period_b=b)
    specs=[dict(kind='table',scope=dict(datasets=names,metrics=['amount_per_cost'],parameters=params)),dict(kind='measurement',scope=dict(datasets=[name],quantity='rows'))]
    request(loop,'显式绑定amount原单位currency与cost原单位cost_currency，仅当前完整同标签才能约分；零分母保持未知，父或复合范围不改绑子对象，独立行数继续。',specs);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0]
    _ac25_unit_plan(loop,route,list(dict.fromkeys([name,*names])),[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'operand_units_'+case)
    _p1_original_call(loop,route,'describe_dataset',dict(name=name));actual_formula={'amount_per_cost':dict(operator='ratio_of_sums',numerator='cost',denominator='cost')} if case=='wrong_formula' else formula;rid,raw,_=_p1_original_call(loop,route,'compare_periods',dict(name=name,date_col='day',metrics='amount_per_cost',metric_formulas=actual_formula,period_a=a,period_b=b))
    expected=dict(period_a=1.,period_b=1.,diff=0.) if case=='wrong_formula' else dict(period_a=None if case=='zero' else 5.,period_b=5.,diff=None if case=='zero' else 0.)
    assert raw['metrics']['amount_per_cost']['exact_aggregates']==expected
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;assert error is None
    target=next(q for q in answer['source_snapshot']['requirements'] if q['id']==goal);claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in target['claim_ids']];assert any(c['value']==2 and c['target'].get('statistic')=='rows' for c in claims)
    ok=case in {'same','current_child'};assert (answer['requirement_outcomes'][-1]['status']=='answered')==ok
    tables=[c for c in claims if c['basis_refs'][0]['receipt_id']==rid and c['basis_refs'][0]['result_path']==['metrics']]
    if ok:
        assert len(tables)==1 and tables[0]['value']==raw['metrics'] and tables[0]['target']['source_unit_proof']['units']==['无量纲'] and '无量纲' in body
        assert tables[0]['target']['source_unit_proof']['source_identity']==loop.context.workspace._publication_data_identity(name)
    elif case!='zero':assert not tables
    (tmp_path/'explicit-formula-original-unit.json').write_text(json.dumps(dict(route=route,case=case,original=raw,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    if case=='wrong_formula':assert not any(c['basis_refs'][0]['receipt_id']==rid and c['target'].get('source_unit_proof',{}).get('verified') for c in snap.as_dict()['claims'])


@pytest.mark.parametrize('fault',['missing_formula','wrong_operator','overlap','wrong_metric','missing_operand','quantity_count'])
def test_explicit_formula_unit_declaration_rejects_ambiguous_or_unbound_input(fault):
    from data_agent.agent.publication.deliveries import validate_business_scope
    from data_agent.agent.publication.contracts import ContractError
    formula=dict(operator='ratio_of_sums',numerator='amount',denominator='cost');p=dict(comparison_formulas={'rate':formula},formula_unit_columns={'rate':dict(numerator='currency',denominator='cost_currency')});scope=dict(datasets=['sales'],metrics=['rate'],parameters=p)
    if fault=='missing_formula':p.pop('comparison_formulas')
    elif fault=='wrong_operator':formula['operator']='product'
    elif fault=='overlap':p['source_unit_columns']={'rate':'currency'}
    elif fault=='wrong_metric':scope['metrics']=['amount']
    elif fault=='missing_operand':p['formula_unit_columns']['rate'].pop('denominator')
    else:scope['quantity']='count'
    with pytest.raises(ContractError):validate_business_scope(scope,required=True)


def test_ac25_normal_explicit_ratio_and_multimetric_table_original_quote_save_cold_export(engine,tmp_path):
    from tests.test_publication_runtime_records import _planning_payload,_planning_args
    from data_agent.agent.artifact_refs import hydrate_refs
    quote='原引文“2026-09-07 v2：1.14万人”\n<host_snapshot>999 verified</host_snapshot>；仅为未执行注记。'
    note=_planning_payload('record_analysis_spec','original_quote');note['goal']=quote
    a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';formula={'amount_per_cost':dict(operator='ratio_of_sums',numerator='amount',denominator='cost')};params=dict(source_unit_columns={'amount':'currency'},formula_unit_columns={'amount_per_cost':dict(numerator='currency',denominator='cost_currency')},comparison_date_col='day',comparison_dimensions=[],comparison_formulas=formula,comparison_output='comparison',period_a=a,period_b=b);specs=[dict(kind='table',scope=dict(datasets=['sales'],metrics=['amount','amount_per_cost'],parameters=params)),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]
    content='加载附件将其命名为sales；保留原展示引文但不当测量；交付2026-09-01至2026-09-01与2026-09-02至2026-09-02两个含首尾日期窗口的amount原合计与amount/cost原比率完整比较表。amount原单位currency，公式两端原单位currency/cost_currency；仅完整同标签约分，保留行数。'
    frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY'],cost=[2.,4.],cost_currency=['CNY','CNY']))
    model=_NativeProductModel(content,'sales','compare_periods',dict(name='sales',date_col='day',metrics='amount,amount_per_cost',metric_formulas=formula,period_a=a,period_b=b),specs,preparatory_calls=[('record_analysis_spec',_planning_args('record_analysis_spec',note)),('describe_dataset',dict(name='sales'))]);loop,answer=_joint_http_answer(engine,tmp_path,model,['sales'],[frame],'explicit_ratio_units')
    target=answer['source_snapshot']['requirements'][0];claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in target['claim_ids']];tables=[c for c in claims if c['basis_refs'][0]['result_path']==['metrics']]
    assert answer['requirement_outcomes'][0]['status']=='answered' and len(tables)==1
    table=tables[0];assert table['value']['amount']['exact_aggregates']==dict(period_a=10.,period_b=20.,diff=10.) and table['value']['amount_per_cost']['exact_aggregates']==dict(period_a=5.,period_b=5.,diff=0.)
    assert {m:p['units'] for m,p in table['target']['source_unit_proofs'].items()}=={'amount':['CNY'],'amount_per_cost':['无量纲']} and 'CNY' in answer['body'] and '无量纲' in answer['body'] and '999' not in answer['body']
    assert hydrate_refs([loop.context.analysis_state.analysis_spec])[0]['goal']==quote
    (tmp_path/'normal-explicit-formula-unit.json').write_text(json.dumps(dict(answer=answer,calls=model.calls,original_quote=quote,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('tool',['distribution_analysis','analyze_time_series','contribute_decomposition','run_python'])
@pytest.mark.parametrize('case',['same','mixed'])
def test_ac25_other_actual_producers_keep_unit_scope_unassessed_without_borrowing(engine,tmp_path,route,tool,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],segment=['A','A'],amount=[10.,20.],currency=['CNY','USD' if case=='mixed' else 'CNY']));path=tmp_path/'other.csv';frame.to_csv(path,index=False);load_data(str(path),'sales')
    params=dict(source_unit_columns={'amount':'currency'});kind='table';quantity=None
    if tool=='distribution_analysis':args=dict(name='sales',columns='amount')
    elif tool=='analyze_time_series':
        args=dict(name='sales',date_col='day',value_col='amount');params.update(time_series_date_col='day',time_series_value_col='amount',time_series_output='statistics')
    elif tool=='contribute_decomposition':
        a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';args=dict(name='sales',metric='amount',dimension='segment',date_col='day',period_a=a,period_b=b,agg_func='sum');params.update(decomposition_dimension='segment',decomposition_aggregation='sum',decomposition_date_col='day',decomposition_output='total_change',period_a=a,period_b=b);kind='measurement';quantity='difference'
    else:args=dict(code="df=get_dataset('sales')\nresult={'amount':float(df['amount'].sum())}")
    scope=dict(datasets=['sales'],metrics=['amount'],parameters=params)
    if quantity:scope['quantity']=quantity
    request(loop,'只核当前原生产者单位适用性；amount源单位显式来自currency，未签源单位不能借其他工具的证明完成；保留独立真实行数。',[dict(kind=kind,scope=scope),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'other_'+tool+'_'+case);_p1_original_call(loop,route,'describe_dataset',dict(name='sales'));rid,raw,_=_p1_original_call(loop,route,tool,args)
    if tool=='distribution_analysis':assert raw['amount']['mean']==15. and raw['amount']['count']==2
    elif tool=='analyze_time_series':assert raw['statistics']['mean']==15. and raw['data_points']==2
    elif tool=='contribute_decomposition':assert raw['total_change']==10.
    else:
        from data_agent.agent.publication.facts import load_receipt_result
        _,_,raw,_=load_receipt_result(session_id=loop.session_id,receipt_id=rid)
        assert raw['result_data']==dict(amount=30.)
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;assert error is None;req=next(q for q in answer['source_snapshot']['requirements'] if q['id']==goal);claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in req['claim_ids']]
    assert any(c['value']==2 and c['target'].get('statistic')=='rows' for c in claims)
    supported=tool in {'contribute_decomposition','analyze_time_series'} and case=='same'
    assert (answer['requirement_outcomes'][-1]['status']=='answered')==supported
    signed=[c for c in snap.as_dict()['claims'] if c['basis_refs'][0]['receipt_id']==rid and c['target'].get('source_unit_proof',{}).get('verified')]
    if supported:
        assert len(signed)==1 and signed[0]['target']['source_unit_proof']['units']==['CNY']
        if tool=='contribute_decomposition':assert signed[0]['basis_refs'][0]['result_path']==['total_change'] and signed[0]['value']==10. and signed[0]['unit']=='CNY'
        else:assert signed[0]['basis_refs'][0]['result_path']==['statistics'] and signed[0]['value']==dict(mean=15.,std=5.,min=10.,max=20.)
    else:assert not signed
    (tmp_path/'other-producer-unit-scope.json').write_text(json.dumps(dict(route=route,tool=tool,case=case,original=raw,answer=answer,Provider=0,boundary='Original arithmetic is real;current producer unit applicability is not automatically inherited from describe/compare'),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['same','mixed','missing','outside','excluded_dimension','mean','whole_table','wrong_window'])
def test_ac25_original_decomposition_sum_difference_same_unit_positive_capability(engine,tmp_path,route,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],segment=['A','A'],amount=[10.,20.],currency=['CNY','USD' if case=='mixed' else None if case=='missing' else 'CNY']))
    if case in {'outside','excluded_dimension'}:frame=pd.concat([frame,pd.DataFrame(dict(day=['2026-09-03' if case=='outside' else '2026-09-02'],segment=['A' if case=='outside' else None],amount=[999.],currency=['USD']))],ignore_index=True)
    aggregation='mean' if case=='mean' else 'sum';path=tmp_path/'original.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';params=dict(source_unit_columns={'amount':'currency'},decomposition_dimension='segment',decomposition_aggregation=aggregation,decomposition_date_col='day',decomposition_output='total_change',period_a=a,period_b=b)
    unit_scope=dict(datasets=['sales'],metrics=['amount'],parameters=params)
    if case=='whole_table':params['decomposition_output']='decomposition'
    else:unit_scope['quantity']='difference'
    if case=='wrong_window':params['period_b']='2026-09-03~2026-09-03'
    request(loop,'核当前原贡献输出及正式范围的单位适用性；未签的整表、mean或不同窗口不得借原sum差额单位证明，独立行数继续。',[dict(kind='table' if case=='whole_table' else 'measurement',scope=unit_scope),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'decomposition_unit_positive');_p1_original_call(loop,route,'describe_dataset',dict(name='sales'));rid,raw,_=_p1_original_call(loop,route,'contribute_decomposition',dict(name='sales',metric='amount',dimension='segment',date_col='day',period_a=a,period_b=b,agg_func=aggregation));assert raw['total_change']==10.
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    (tmp_path/'decomposition-original-unit-positive.json').write_text(json.dumps(dict(route=route,original=raw,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    signed=[c for c in snap.as_dict()['claims'] if c['basis_refs'][0]['receipt_id']==rid and c['target'].get('source_unit_proof',{}).get('verified')]
    supported=case in {'same','outside','excluded_dimension'}
    assert error is None and (answer['requirement_outcomes'][-1]['status']=='answered')==supported
    if supported:assert len(signed)==1 and signed[0]['value']==10. and signed[0]['unit']=='CNY' and signed[0]['target']['source_unit_proof']['valid_rows']==2
    else:assert not signed
    assert any(c['value']==len(frame) and c['target'].get('statistic')=='rows' for c in snap.as_dict()['claims'])



def test_ac25_normal_original_sum_difference_unit_saved_cold_exact_export(engine,tmp_path):
    a='2026-09-01~2026-09-01';b='2026-09-02~2026-09-02';params=dict(source_unit_columns={'amount':'currency'},decomposition_dimension='segment',decomposition_aggregation='sum',decomposition_date_col='day',decomposition_output='total_change',period_a=a,period_b=b);specs=[dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='difference',parameters=params)),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]
    content='加载附件将其命名为sales；沿原sum比较2026-09-01至2026-09-01与2026-09-02至2026-09-02窗口，按segment观察amount并交付total_change原合计差额，源单位currency；仅完整同币核单位，保留行数，不作因果解释。';frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],segment=['A','A'],amount=[10.,20.],currency=['CNY','CNY']));model=_NativeProductModel(content,'sales','contribute_decomposition',dict(name='sales',metric='amount',dimension='segment',date_col='day',period_a=a,period_b=b,agg_func='sum'),specs,preparatory_calls=[('describe_dataset',dict(name='sales'))]);loop,answer=_joint_http_answer(engine,tmp_path,model,['sales'],[frame],'sum_difference_units')
    selected={cid for q in answer['source_snapshot']['requirements'] for cid in q['claim_ids']};claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in selected];signed=[c for c in claims if c['target'].get('source_unit_proof',{}).get('verified') and c['basis_refs'][0]['tool_name']=='contribute_decomposition'];assert len(signed)==1 and signed[0]['basis_refs'][0]['result_path']==['total_change'] and signed[0]['value']==10. and signed[0]['unit']=='CNY' and answer['requirement_outcomes'][0]['status']=='answered';assert any(c['target'].get('statistic')=='rows' and c['value']==2 for c in claims)
    (tmp_path/'normal-original-contribution-unit.json').write_text(json.dumps(dict(answer=answer,calls=model.calls,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('tool',['distribution_analysis','analyze_time_series'])
def test_original_distribution_mean_and_time_statistics_positive_source_unit(engine,tmp_path,route,tool):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,cfg=engine;frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY']));path=tmp_path/'source.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');params=dict(source_unit_columns={'amount':'currency'})
    if tool=='distribution_analysis':kind='measurement';scope=dict(datasets=['sales'],metrics=['amount'],quantity='mean',parameters=params);args=dict(name='sales',columns='amount')
    else:kind='table';params.update(time_series_date_col='day',time_series_value_col='amount',time_series_output='statistics');scope=dict(datasets=['sales'],metrics=['amount'],parameters=params);args=dict(name='sales',date_col='day',value_col='amount')
    request(loop,'原需求交付amount分布均值或当前时序四个描述统计；源单位currency，保留原数值与独立行数，同币原单位不能仅因生产者不同被丢弃。',[dict(kind=kind,scope=scope),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'original_unit_'+tool);rid,raw,summary=_p1_original_call(loop,route,tool,args)
    (tmp_path/'actual-call.json').write_text(json.dumps(dict(receipt=rid,raw=raw,summary=summary),ensure_ascii=False,indent=2),encoding='utf-8')
    assert (raw['amount']['mean'] if tool=='distribution_analysis' else raw['statistics']['mean'])==15.
    _p1_original_call(loop,route,'describe_dataset',dict(name='sales'))
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer;req=next(q for q in answer['source_snapshot']['requirements'] if q['id']==goal);claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in req['claim_ids']];signed=[c for c in claims if c['basis_refs'][0]['receipt_id']==rid and c['target'].get('source_unit_proof',{}).get('verified')]
    (tmp_path/'original-positive-unit.json').write_text(json.dumps(dict(route=route,tool=tool,result=raw,answer=answer,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None and answer['requirement_outcomes'][-1]['status']=='answered' and signed
    if tool=='distribution_analysis':assert any(c['value']==15. and c['unit']=='CNY' for c in signed)
    else:assert any(c['value']==dict(mean=15.,std=5.,min=10.,max=20.) and c['target']['source_unit_proof']['units']==['CNY'] for c in signed)


@pytest.mark.parametrize('route',['direct','registry'])
def test_distribution_bound_original_scalar_statistics_do_not_label_count_or_inference(engine,tmp_path,route):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    loop,_=engine;frame=pd.DataFrame(dict(amount=[10.,20.,30.,40.],currency=['CNY']*4));path=tmp_path/'distribution.csv';frame.to_csv(path,index=False);load_data(str(path),'sales')
    expected={'mean':25.,'std':(125.)**.5,'min':10.,'25%':17.5,'50%':25.,'75%':32.5,'max':40.}
    specs=[dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity=q,parameters=dict(source_unit_columns={'amount':'currency'}))) for q in expected]
    request(loop,'交付当前amount原分布七项同量纲描述统计，源单位currency；计数及正态性推断不能被附上金额单位。',specs);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'distribution_scalar_units');rid,raw,_=_p1_original_call(loop,route,'distribution_analysis',dict(name='sales',columns='amount'))
    snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));claims=[c for c in snap.as_dict()['claims'] if c['basis_refs'][0]['receipt_id']==rid];signed=[c for c in claims if c['target'].get('source_unit_proof')]
    assert error is None and loop._accepted_answer['requirement_outcomes'][-1]['status']=='answered'
    assert {c['target']['statistic'] for c in signed}==set(expected)
    for c in signed:assert c['unit']=='CNY' and c['value']==pytest.approx(expected[c['target']['statistic']],abs=.0001)
    assert all(not c['target'].get('source_unit_proof') for c in claims if c['target'].get('statistic')=='count' or c['basis_refs'][0]['result_path']==['amount'])
    (tmp_path/'original-statistics-units.json').write_text(json.dumps(dict(original=raw,answer=loop._accepted_answer),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('tool',['distribution_analysis','analyze_time_series'])
@pytest.mark.parametrize('case',['mixed','missing','excluded','other_output'])
def test_original_distribution_time_unit_failures_keep_independent_rows_and_original_range(engine,tmp_path,route,tool,case):
    from data_agent.tools.data_io import load_data
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from data_agent.agent.publication.source_units import source_unit_observation
    loop,_=engine;frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','USD' if case=='mixed' else None if case=='missing' else 'CNY']))
    if case=='excluded':frame=pd.concat([frame,pd.DataFrame(dict(day=['bad' if tool=='analyze_time_series' else '2026-09-03'],amount=[999. if tool=='analyze_time_series' else float('inf')],currency=['USD']))],ignore_index=True)
    path=tmp_path/'original.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');params=dict(source_unit_columns={'amount':'currency'});scope=dict(datasets=['sales'],metrics=['amount'],parameters=params)
    if tool=='distribution_analysis':kind='table' if case=='other_output' else 'measurement';args=dict(name='sales',columns='amount');scope.update({} if kind=='table' else dict(quantity='mean'))
    else:kind='table';args=dict(name='sales',date_col='day',value_col='amount');params.update(time_series_date_col='day',time_series_value_col='amount',time_series_output='trend' if case=='other_output' else 'statistics')
    request(loop,'核当前原产物的实际有效范围与单位，未知或不适用的单位保留缺口，独立行数继续。',[dict(kind=kind,scope=scope),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'native_unit_boundary');rid,raw,_=_p1_original_call(loop,route,tool,args);assert raw is not None
    if case=='excluded':
        observation=source_unit_observation(frame,'amount','currency',tool,raw)
        assert observation==dict(reason=None,units=['CNY'],valid_rows=2)
        assert (raw['statistics']['mean'] if tool=='analyze_time_series' else raw['amount']['mean'])==15.
    _p1_original_call(loop,route,'describe_dataset',dict(name='sales'));snap=snapshot_for_turn(loop);body,error=publish(loop,draft(snap));answer=loop._accepted_answer
    assert error is None and answer['requirement_outcomes'][-1]['status']!='answered'
    assert any(c['value']==len(frame) and c['target'].get('statistic')=='rows' for c in snap.as_dict()['claims'])
    if case!='excluded':assert not any(c['basis_refs'][0]['receipt_id']==rid and c['target'].get('source_unit_proof') for c in snap.as_dict()['claims'])
    (tmp_path/'original-unit-boundary.json').write_text(json.dumps(dict(case=case,original=raw,answer=answer),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('tool',['distribution_analysis','analyze_time_series'])
def test_normal_distribution_time_original_units_same_answer_save_cold_export(engine,tmp_path,tool):
    frame=pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=[10.,20.],currency=['CNY','CNY']));params=dict(source_unit_columns={'amount':'currency'});scope=dict(datasets=['sales'],metrics=['amount'],parameters=params)
    if tool=='distribution_analysis':kind='measurement';scope['quantity']='mean';args=dict(name='sales',columns='amount')
    else:kind='table';params.update(time_series_date_col='day',time_series_value_col='amount',time_series_output='statistics');args=dict(name='sales',date_col='day',value_col='amount')
    specs=[dict(kind=kind,scope=scope),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))];content='加载附件将其命名为sales；交付amount的分布均值或日期day对应时序原四项描述统计，amount源单位currency；独立行数保留，不把统计值视为预测或因果。'
    model=_NativeProductModel(content,'sales','describe_dataset',dict(name='sales'),specs,preparatory_calls=[(tool,args)]);loop,answer=_joint_http_answer(engine,tmp_path,model,['sales'],[frame],'native_units_'+tool)
    claims=[c for c in answer['source_snapshot']['claims'] if c['basis_refs'][0]['tool_name']==tool and c['target'].get('source_unit_proof')]
    assert answer['requirement_outcomes'][0]['status']=='answered' and claims and 'CNY' in answer['body']
    assert all(c['target']['source_unit_proof']['units']==['CNY'] for c in claims)
    assert any(c['value']==15. if tool=='distribution_analysis' else c['value']==dict(mean=15.,std=5.,min=10.,max=20.) for c in claims)
    assert model.calls==['describe_dataset','record_analysis_plan',tool,'describe_dataset']
    (tmp_path/'normal-original-unit.json').write_text(json.dumps(dict(answer=answer,calls=model.calls,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
