"""Finite C/B/AC25 joint conditions; frozen semantic decisions are not model acceptance."""
import datetime
import json
from types import SimpleNamespace
import pandas as pd
import pytest
from tests.test_trusted_publication_semantics import engine,execute
from tests.support.publication_runtime import _NativeProductModel,request,draft
from tests.test_slice3_method_integrity import _joint_http_answer,_n_audit_response,_n_retention_input
from data_agent.agent.publication.contracts import encode


def _time_input(case):
    dates=['not-a-time-'+str(i) for i in range(30)] if case=='unparseable' else [(datetime.date(2025,1,1)+datetime.timedelta(days=i*(i+1)//2)).isoformat() for i in range(30)]
    return pd.DataFrame(dict(day=dates,amount=range(1,31)))


def _time_oracle(case,data):
    obs=data['observation']
    assert 'forecast' not in data and data['status']!='supported' and obs['interval'] is None
    if case=='unparseable':assert obs['invalid_date']==30 and obs['effective_rows']==0 and data['date_range'] is None
    else:assert obs['effective_rows']==30 and obs['equal_intervals'] is False and data['reason_code']=='missing_time_intervals'


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['unparseable','unknown_frequency'])
def test_original_c06_invalid_time_or_unknown_frequency_real_interfaces(engine,tmp_path,case,route):
    from data_agent.tools.registry import registry
    loop,_=engine;loop.context.workspace.add('experiment',_time_input(case))
    args=dict(name='experiment',date_col='day',target_col='amount',periods=3,method='auto')
    raw=registry.get('forecast').func(**args) if route=='direct' else registry.execute('forecast',args).summary
    data=json.loads(raw);(tmp_path/'c06-counter.json').write_text(json.dumps(dict(route=route,case=case,result=data),ensure_ascii=False,indent=2),encoding='utf-8');_time_oracle(case,data)


@pytest.mark.parametrize('case',['unparseable','unknown_frequency'])
def test_original_c06_normal_same_unknown_observation_and_saved_answer(engine,tmp_path,case):
    args=dict(name='experiment',date_col='day',target_col='amount',periods=3,method='auto')
    params=dict(forecast_periods=3,forecast_date_col='day',forecast_method='auto')
    specs=[dict(kind='forecast' if out=='forecast' else 'table',scope=dict(datasets=['experiment'],metrics=['amount'],parameters=dict(params,forecast_output=out))) for out in ['forecast','observation']]
    content='加载附件将其命名为experiment；评估amount未来3期预测和真实时间范围，时段无法解析或频率未知时明确未知限制，不编造窗口充分性。'
    model=_NativeProductModel(content,'experiment','forecast',args,specs)
    loop,answer=_joint_http_answer(engine,tmp_path,model,['experiment'],[_time_input(case)],'original_c06_'+case)
    claims=answer['source_snapshot']['claims'];values={c['basis_refs'][0]['result_path'][0]:c['value'] for c in claims}
    assert answer['requirement_outcomes'][0]['status']!='answered' and 'forecast' not in values
    obs=values['observation'];assert obs['interval'] is None
    if case=='unparseable':assert obs['invalid_date']==30 and obs['effective_rows']==0
    else:assert obs['effective_rows']==30 and obs['equal_intervals'] is False
    assert model.calls==['describe_dataset','record_analysis_plan','forecast']


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['zero','missing','nonfinite','negative'])
def test_original_ac25_actual_period_denominators_and_exclusions(engine,tmp_path,route,case):
    from data_agent.tools.registry import registry
    loop,_=engine;values={'zero':[0.,1.],'missing':[None,1.],'nonfinite':[float('inf'),1.],'negative':[-2.,1.]}[case]
    loop.context.workspace.add('orders',pd.DataFrame(dict(day=['2026-09-01','2026-09-02'],amount=values)))
    args=dict(name='orders',date_col='day',metrics='amount',period_a='2026-09-01~2026-09-01',period_b='2026-09-02~2026-09-02')
    raw=registry.get('compare_periods').func(**args) if route=='direct' else registry.execute('compare_periods',args).summary
    result=json.loads(raw);(tmp_path/'ac25-actual.json').write_text(json.dumps(dict(route=route,case=case,result=result),ensure_ascii=False,indent=2),encoding='utf-8')
    metric=result['metrics']['amount']
    if case=='zero':assert metric['change_pct'] is None
    elif case in {'missing','nonfinite'}:assert metric['period_a'] is None and metric['change_pct'] is None
    else:
        assert metric['period_a']==-2 and metric['period_b']==1 and metric['diff']==3
        # Current native method explicitly uses abs(base); this is not a new conventional signed-base rate.
        assert metric['change_pct']==150


class _TextModel(_NativeProductModel):
    def __init__(self,*a,texts,**kw):super().__init__(*a,**kw);self.texts=texts;self.audits=[]
    def chat(self,messages,system='',**kw):
        from data_agent.llm.client import Response
        if system.startswith('审核数据相关开放片段'):
            q=json.loads(messages[0]['content']);self.audits.append(q)
            return Response(text=_n_audit_response(q,{text:decision for purpose,text,decision in self.texts}))
        if self.ticket is None and system=='你是一个JSON输出器，只返回JSON，不要其他内容。':
            return Response(text=encode(dict(intent_type='directed_analysis',requested_outputs=[dict(kind='result',exact_span=self.content,business_scope=dict(datasets=[self.dataset]),purposes=list(dict.fromkeys(p for p,t,d in self.texts)))])))
        response=super().chat(messages,system=system,**kw)
        if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':
            value=json.loads(response.text);value['requested_outputs'][0]['purposes']=list(dict.fromkeys(p for p,t,d in self.texts));return Response(text=encode(value))
        if response.tool_calls:return response
        value=json.loads(response.text)
        for section in value['sections']:
            refs=[p['ref'] for p in section['parts'] if p['kind']=='claim']
            section['parts'] += [dict(kind='text',purpose=p,text=t,claim_refs=refs) for p,t,d in self.texts]
        return Response(text=encode(value))


def test_original_b01_c04_same_sales_advice_bias_boundary_and_cold_original(engine,tmp_path):
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from scripts.testing.run_p7_browser_rehearsal import _write_fixtures
    _,cfg=engine;(cfg.workspace_resolved/'inbox').mkdir(parents=True,exist_ok=True);_write_fixtures(cfg.workspace_resolved.parent)
    frame=pd.read_csv(cfg.workspace_resolved/'inbox/F-SALES.csv')
    texts=[('interpretation','当前12条完整原记录的amount合计120；这些记录不能证明来自随机抽样，也不能代表市场总体。','accept'),('conditional_action','建议先检查渠道覆盖；若确认口径一致再开展对照验证，否则不扩大预算。','accept'),('interpretation','样本够大，因此已经排除选择偏差并代表市场总体。','reject')]
    specs=[dict(kind='measurement',scope=dict(datasets=['sales'],metrics=['amount'],quantity='sum')),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]
    content='加载附件将其命名为sales；中文分析当前原文件amount合计和记录数，并给出有条件建议，不将当前原记录外推市场。'
    model=_TextModel(content,'sales','describe_dataset',dict(name='sales'),specs,texts=texts)
    loop,answer=_joint_http_answer(engine,tmp_path,model,['sales'],[frame],'original_b01_c04',filenames={'sales':'F-SALES.csv'})
    assert len(model.audits)==1 and all((t in answer['body'])==(d=='accept') for p,t,d in texts)
    owned=answer['source_snapshot']['claims'];assert any(c['value']==120 for c in owned) and any(c['label']=='记录数' and c['value']==12 for c in owned)
    sid=loop.session_id;app=create_app();app.config['agent_manager']=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    with app.test_client() as http:
        refreshed=http.get('/api/sessions/'+sid).get_json();workbench=http.get('/api/sessions/'+sid+'/trust').get_json()
    (tmp_path/'b01-workbench.json').write_text(json.dumps(dict(answer=answer,refresh=refreshed,workbench=workbench,semantic_model='unassessed;frozen decisions',visual='unassessed'),ensure_ascii=False,indent=2),encoding='utf-8')
    traces={t['ref']:t['rendered_text'] for t in answer['render_trace'] if t['kind']=='claim' and t['disposition']=='accepted'}
    assert workbench['workbench']['verified_conclusions']
    for claim in workbench['workbench']['verified_conclusions']:
        assert claim['id'] in traces and claim['summary']==traces[claim['id']] and claim['summary'] in answer['body']


def test_original_b02_same_session_d7_then_bad_d30_never_public_delta(engine,tmp_path):
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.llm.client import Response
    from scripts.testing.run_p7_browser_rehearsal import _write_fixtures
    _,cfg=engine;(cfg.workspace_resolved/'inbox').mkdir(parents=True,exist_ok=True);_write_fixtures(cfg.workspace_resolved.parent)
    frame=pd.read_csv(cfg.workspace_resolved/'inbox/F-RET7.csv');_,args,spec=_n_retention_input();args['name']='ret_a'
    good='D7 为 10%，当前不能预测 D30。';bad='不能预测 D30，但 D30 大约是 5%。'
    model=_TextModel('加载附件将其命名为ret_a；留存为小数比例，交付D1至D7全部实际观察，说明不能预测D30。','ret_a','curve_fitting',args,[spec],texts=[('interpretation',good,'accept')])
    loop,first=_joint_http_answer(engine,tmp_path,model,['ret_a'],[frame],'original_b02',filenames={'ret_a':'F-RET7.csv'})
    sid=loop.session_id;root=cfg.sessions_resolved/sid;old=next(m for m in reversed(load_session(sid)['messages']) if m.get('answer_ref'));oldbytes=(root/old['answer_ref']['path']).read_bytes()
    model=_TextModel('沿用ret_a当前原文件，留存仍为小数比例；复核D7与D30边界，不增加未来数据。','ret_a','curve_fitting',args,[spec],texts=[('interpretation',good,'accept'),('interpretation',bad,'reject')]);model.step=1
    app=create_app();app.config['agent_manager']=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    with app.test_client() as http:
        response=http.post('/api/chat',json=dict(session_id=sid,message=model.content));rows=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=http.get('/api/sessions/'+sid).get_json()
    saved=load_session(sid);msg=next(m for m in reversed(saved['messages']) if m.get('answer_ref'));answer=read_answer(sid,msg['answer_ref'])
    (tmp_path/'b02-continuation.json').write_text(json.dumps(dict(events=rows,first=first,answer=answer,saved=saved,refresh=refresh,semantic_model='unassessed;frozen decisions',Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')
    assert [v['status'] for k,v in rows if k=='turn_end']==['completed']
    assert good in first['body'] and good in answer['body'] and bad not in answer['body']
    assert bad not in ''.join(v['text'] for k,v in rows if k=='text_delta')
    assert msg['answer_ref']!=old['answer_ref'] and (root/old['answer_ref']['path']).read_bytes()==oldbytes and read_answer(sid,old['answer_ref'])==first
    assert any(t['kind']=='text' and t['disposition']=='reject' for t in answer['render_trace'])
    with app.test_client() as http:
        exported=http.post('/api/sessions/'+sid+'/export-reply',json=dict(reply_id=msg['reply_id'],format='markdown'));assert exported.status_code==200
        file=cfg.sessions_resolved.parent/exported.get_json()['artifact_path'];assert answer['body'] in file.read_text(encoding='utf-8')
    app.config['agent_manager']=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    with app.test_client() as http:cold=http.get('/api/sessions/'+sid).get_json()
    assert any(m.get('answer_ref')==msg['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
    assert read_answer(sid,old['answer_ref'])==first and (root/old['answer_ref']['path']).read_bytes()==oldbytes


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('audit_state',['reject','unavailable'])
def test_original_c04_large_selected_sample_never_grants_population_authority(engine,tmp_path,route,audit_state):
    from data_agent.tools.registry import registry
    from data_agent.llm.client import Response
    from data_agent.agent.publication.runtime import snapshot_for_turn,publish
    from tests.test_slice3_method_integrity import _p1_original_call
    loop,_=engine;loop.context.workspace.add('selected',pd.DataFrame(dict(amount=[10.]*600,channel=['only_channel_A']*600)))
    spec=dict(kind='measurement',scope=dict(datasets=['selected'],metrics=['amount'],quantity='sum'))
    request(loop,'描述当前600条单一渠道记录，不因样本大而断言已经排除选择偏差或代表市场总体。',spec,purposes=['interpretation'])
    _,actual,_=_p1_original_call(loop,route,'describe_dataset',dict(name='selected'))
    text='样本够大，因此已经排除选择偏差并代表市场总体。';audits=[]
    def assess(messages,**kw):
        q=json.loads(messages[0]['content']);audits.append(q)
        if audit_state=='unavailable':raise OSError('Controlled unavailable semantic auditor')
        return Response(text=_n_audit_response(q,{text:'reject'}))
    loop.auxiliary_llm_client=SimpleNamespace(chat=assess);snap=snapshot_for_turn(loop);host=snap.as_dict();req=host['requirements'][0];payload=json.loads(draft(snap));payload['sections'][0]['parts'].append(dict(kind='text',purpose='interpretation',text=text,claim_refs=req['claim_ids']))
    body,error=publish(loop,encode(payload));answer=loop._accepted_answer
    (tmp_path/'c04-selection.json').write_text(json.dumps(dict(route=route,audit_state=audit_state,actual=actual,answer=answer,audits=audits,semantic_model='unassessed;frozen or unavailable'),ensure_ascii=False,indent=2),encoding='utf-8')
    assert error is None and len(audits)==1 and text not in body
    assert any(c['value']==6000 for c in host['claims']) and '6000' in body
    assert not any('population' in c.get('target',{}) for c in host['claims'])
    assert any(t['kind']=='text' and t['disposition']==('reject' if audit_state=='reject' else 'unassessed') for t in answer['render_trace'])
