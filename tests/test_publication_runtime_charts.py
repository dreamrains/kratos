from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: charts. Shared fixtures have one owner."""
from copy import deepcopy
from data_agent.agent.publication.contracts import encode
from data_agent.tools.registry import registry
from pathlib import Path
from tests.test_trusted_publication_semantics import execute
from types import SimpleNamespace
import base64
import hashlib
import io
import json
import math
import os
import pandas as pd
import pytest
import struct
from tests.support.publication_runtime import _NativeProductModel, request
from tests.test_publication_runtime_records import E

def _save_chart_binding_probe(n,d): (E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['funnel_json','line_json','result_data','result_missing','result_json','result_only','result_same','json_only_funnel','json_only_line','dataset_only_funnel','result_tamper','result_ambiguous'])
def test_chart_selectors_source_binding_s3_chart_binding(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,cfg=engine;w=loop.context.workspace;w.add('orders',pd.DataFrame({'x':[1,2,3,4,5],'y':[100,50,30,20,10],'step':['A','B','C','D','E'],'count':[100,50,30,20,10]}));w.add('alternative',pd.DataFrame({'x':[1,2,3,4],'actual':[999,998,997,996]}));loop._reset_turn_tracking()
 p={'chart_type':'line','x_col':'x','y_col':'y','data':'orders','data_json':'[{"x":1,"y":999},{"x":2,"y":888}]'}
 before={n:w.get_data_identity(n) for n in w.list_datasets()};saved=[]
 if case in {'funnel_json','json_only_funnel','dataset_only_funnel'}:p={'chart_type':'funnel','data':'orders','data_json':'[{"step":"A","count":999},{"step":"B","count":1}]'}
 if case=='json_only_funnel':p.pop('data')
 if case=='dataset_only_funnel':p.pop('data_json')
 if case=='json_only_line':p.pop('data')
 if case.startswith('result_'):
  rid,_=execute(loop,'curve_fitting',{'name':'orders','x_col':'x','y_col':'y','zero_values':'keep'});ref=next(z for z in loop.context.analysis_state.tool_receipts if z['id']==rid)['detail_ref']['path'];p={'chart_type':'line','x_col':'x','y_col':'actual','result_ref':ref}
  if case=='result_data':p['data']='alternative'
  if case=='result_missing':p['data']='not_loaded'
  if case=='result_json':p['data_json']='[{"x":1,"actual":999},{"x":2,"actual":888}]'
  if case=='result_same':p['data']='orders'
  if case=='result_tamper':(cfg.sessions_resolved/loop.session_id/ref).write_bytes(b'{"chart_data":[]}')
  if case=='result_ambiguous':loop.context.analysis_state.tool_receipts[-1]['data_identities']['alternative']=w.get_data_identity('alternative')
 def stop(fig,title,metadata):saved.append({'metadata':deepcopy(metadata),'figure':json.loads(fig.to_json())});raise RuntimeError('stop before file write')
 monkeypatch.setattr(v,'_save_chart',stop);result=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 after={n:w.get_data_identity(n) for n in w.list_datasets()};_save_chart_binding_probe(case+'_'+route+'.json',{'input':p,'saved':saved,'result':result,'before':before,'after':after,'actual_chart_writes':0,'provider_calls':0});assert before==after
 if case in {'funnel_json','line_json','result_data','result_missing','result_json','result_tamper','result_ambiguous'}:
  assert not saved,'Conflicting or unverified chart source reached save'
  err=json.loads(result);assert err['error_type']=='chart_validation' and err['error_code']==('chart_source_conflict' if case in {'funnel_json','line_json','result_json'} else 'chart_result_source_invalid')
 else:
  assert len(saved)==1
  meta=saved[0]['metadata']
  if case.startswith('json_only'):assert meta['dataset']=='' and meta['data_identity']=={} and meta['source_kind']=='inline_json' and meta['purpose']=='exploratory'
  else:assert meta['dataset']=='orders' and meta['data_identity']['version_id']==before['orders']['version_id']
  if case in {'result_same','result_only'}:assert meta['result_binding']['result_ref']==p['result_ref'] and meta['source_kind']=='result_ref'
  if case=='dataset_only_funnel':assert saved[0]['figure']['data'][0]['x']==[100,50,30,20,10]


@pytest.mark.parametrize('case',['funnel_conflict','line_conflict','inline_only','dataset_funnel','result_omitted','result_same','result_mismatch','result_json'])
def test_normal_actual_chart_source_binding_s3_chart_binding(engine,monkeypatch,case):
 import re,io
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled static renderer unavailable; actual HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png)
 content='加载上传文件，将其命名为experiment；根据真实注册数据或其已计算回执绘图，JSON只作探索，不得替代上传数据。'
 args={'chart_type':'funnel','data':'experiment','title':'Bound source '+case};raw=b'x,y,step,count\n1,100,A,100\n2,50,B,50\n3,30,C,30\n4,20,D,20\n5,10,E,10\n';prep=[]
 if case in {'funnel_conflict','inline_only'}:args['data_json']='[{"step":"A","count":999},{"step":"B","count":1}]'
 if case=='inline_only':args.pop('data')
 if case=='line_conflict':args.update(chart_type='line',x_col='x',y_col='y',data_json='[{"x":1,"y":999},{"x":2,"y":888}]')
 if case.startswith('result_'):
  args.update(chart_type='line',x_col='x',y_col='actual');args.pop('data');prep=[('curve_fitting',{'name':'experiment','x_col':'x','y_col':'y','zero_values':'keep'})]
  if case=='result_same':args['data']='experiment'
  if case=='result_mismatch':args['data']='not_loaded'
  if case=='result_json':args['data_json']='[{"x":1,"actual":999},{"x":2,"actual":888}]'
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   if self.step==3 and prep and system!='你是一个JSON输出器，只返回JSON，不要其他内容。':
    last=next(m['content'] for m in reversed(messages) if m.get('role')=='tool');match=re.search(r'\[detail: (tool_outputs/[^\] ]+_detail\.json)\]',last);assert match,last;self.args['result_ref']=match.group(1)
   response=super().chat(messages,system=system,**kw)
   if response.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return response
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[r['id']],'parts':[{'kind':'artifact','ref':aid} for aid in r.get('artifact_ids',[])]} for r in view['requirements'] if not r['withdrawn']]}))
 model=Model(content,'experiment','create_chart',args,[{'kind':'chart','scope':{'datasets':['experiment']}}],prep);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_binding_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;res=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in res.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(p.with_suffix('.json').read_text(encoding='utf-8')) for p in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_chart_binding_probe('normal_'+case+'.json',{'case':case,'input':args,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(p) for p in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed','static_png':'controlled first failure'})
 assert len(ends)==1
 if case in {'dataset_funnel','result_omitted','result_same'}:
  assert ends[0]['status']=='completed' and answer['requirement_outcomes'][0]['status']=='answered',events
  assert len(html)==1 and metadata[0]['dataset']=='experiment' and md['status']=='exported'
  figure=metadata[0]['figure'];assert figure['data'][0]['x']==([100,50,30,20,10] if case=='dataset_funnel' else [1.,2.,3.,4.,5.])
  assert metadata[0]['source_kind']==('dataset' if case=='dataset_funnel' else 'result_ref')
  if prep:assert args['data']=='experiment' and metadata[0]['result_binding']['result_ref']==args['result_ref']
  assert answer['body']==saved['messages'][-1]['content']==ends[0]['reply_content']
 elif case=='inline_only':
  assert len(html)==1 and metadata[0]['data_identity']=={} and metadata[0]['source_kind']=='inline_json'
  assert answer['requirement_outcomes'][0]['status']!='answered' and not answer['artifact_refs']
  assert next(t for t in state['tool_receipts'] if t['tool_name']=='create_chart')['data_identities']=={}
 else:
  assert ends[0]['status']=='failed' and not html and not any(t['tool_name']=='create_chart' for t in state['tool_receipts'])


AGG_E=Path(os.environ.get('DATA_AGENT_S3_CHART_AGGREGATION_EVIDENCE','tmp/s3-chart-aggregation-20261014-r3/evidence'));AGG_E.mkdir(exist_ok=True)


AGG_E=Path(os.environ.get('DATA_AGENT_S3_CHART_AGGREGATION_EVIDENCE','tmp/s3-chart-aggregation-20261014-r3/evidence'));AGG_E.mkdir(exist_ok=True)


def _save_chart_aggregation_probe(n,d):(AGG_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _chart_aggregation_values(v):
 if isinstance(v,list):return [None if isinstance(x,float) and x!=x else x for x in v]
 code={'i1':'b','i2':'h','i4':'i','i8':'q','u1':'B','u2':'H','u4':'I','u8':'Q','f4':'f','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return [None if isinstance(x,float) and x!=x else x for x in struct.unpack('<'+code*(len(b)//struct.calcsize(code)),b)]


def _chart_aggregation_frame(case):
 if case.startswith('count'):return pd.DataFrame({'group':['A','A','B','B','C'],'day':['2026-10-01','2026-10-01','2026-10-02','2026-10-02','2026-10-03'],'segment':['X']*5,'user_id':{'count_text':['alice','bob',None,'carol','dave'],'count_numeric':[1001,1002,None,1003,1004],'count_empty':[None]*5,'count_mixed':['alice',2,None,'carol',0]}[case]})
 return pd.DataFrame({'group':['A','A','B','B','C'],'day':['2026-10-01','2026-10-01','2026-10-02','2026-10-02','2026-10-03'],'amount':[2.,3.,None,None,0.],'segment':['X']*5})


def _chart_aggregation_args(case,dataset):
 typ=case if case in {'bar','line','pie','stacked_bar'} else 'bar'
 p={'chart_type':typ,'data':dataset,'x_col':'day' if typ=='line' else 'group','y_col':'user_id' if case.startswith('count') else 'amount','aggregation':'count' if case.startswith('count') else 'sum','title':'Actual aggregate '+case}
 if typ=='stacked_bar':p['color_col']='segment'
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['bar','line','pie','stacked_bar','count_text','count_numeric','count_empty','count_mixed'])
def test_cross_interface_aggregation_s3_chart_aggregation(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,cfg=engine;f=_chart_aggregation_frame(case);loop.context.workspace.add('aggregate_input',f);before=loop.context.workspace.get_data_identity('aggregate_input');p=_chart_aggregation_args(case,'aggregate_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe stop before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_chart_aggregation_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'result':r,'captured':captured,'before':before,'after':loop.context.workspace.get_data_identity('aggregate_input'),'actual_chart_writes':0,'provider_calls':0})
 if case=='pie':
  assert not captured and json.loads(r)['error_code']=='unknown_pie_measure';return
 assert len(captured)==1,r
 t=captured[0]['figure']['data'][0];actual=_chart_aggregation_values(t['values'] if case=='pie' else t['y']);expected=([0,0,0] if case=='count_empty' else [2,1,1]) if case.startswith('count') else [5,None,0]
 assert actual==expected,{'actual':actual,'expected':expected}


@pytest.mark.parametrize('case',['bar','line','pie','stacked_bar','count_text','count_numeric','count_empty','count_mixed'])
def test_normal_aggregation_user_chain_s3_chart_aggregation(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled static renderer unavailable; actual HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png)
 content='加载上传文件，将其命名为experiment；按明确指定的聚合方式绘图，保留真实零、未知值和原始来源。';p=_chart_aggregation_args(case,'experiment');f=_chart_aggregation_frame(case);raw=f.to_csv(index=False).encode('utf-8')
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_aggregate_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md',reply_id=msg['reply_id'])
  if md['status']=='exported':(AGG_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 with use_agent_context(manager.get(sid).context):actual_frame=manager.get(sid).context.workspace.get('experiment')
 _save_chart_aggregation_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'loaded_rows':actual_frame.to_dict('records') if actual_frame is not None else None,'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed','static_png':'controlled first failure'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case=='pie':
  assert not html and answer['requirement_outcomes'][0]['status']!='answered' and not answer['artifact_refs'];assert md['status']=='exported';return
 assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events
 t=metadata[0]['figure']['data'][0];actual=_chart_aggregation_values(t['values'] if case=='pie' else t['y']);expected=([0,0,0] if case=='count_empty' else [2,1,1]) if case.startswith('count') else [5,None,0]
 assert actual==expected,{'actual':actual,'expected':expected,'loaded':actual_frame.to_dict('records') if actual_frame is not None else None}
 assert md['status']=='exported' and answer['body']==saved['messages'][-1]['content']==ends[0]['reply_content']
 audit=metadata[0]['aggregation_audit'];assert [g['valid_counts'][p['y_col']] for g in audit['groups']]==([0,0,0] if case=='count_empty' else [2,1,1] if case.startswith('count') else [2,0,1]);assert all('有效观测数=' in s for s in t['text'])
 if not case.startswith('count'):assert audit['unknown_group_count']==1 and any('未知不是0' in a.get('text','') and 'amount有效观测数=0' in a.get('text','') for a in metadata[0]['figure']['layout']['annotations'])
 if case=='count_empty':
  original=(root/msg['answer_ref']['path']).read_bytes();app.config['agent_manager']=AgentManager(client_factory=lambda **kw:object(),auxiliary_client_factory=lambda:object())
  with app.test_client() as http:cold=http.get('/api/sessions/'+sid).get_json()
  assert any(m.get('reply_id')==msg['reply_id'] and m.get('answer_ref')==msg['answer_ref'] and m['content']==answer['body'] for m in cold['messages'])
  assert read_answer(sid,msg['answer_ref'])==answer and (root/msg['answer_ref']['path']).read_bytes()==original
  (AGG_E/'normal_count_empty_cold.json').write_text(json.dumps(dict(cold=cold,answer=answer,export=md,Provider=0),ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('typ',['line','bar'])
@pytest.mark.parametrize('mode',['raw','normalize','index100'])
@pytest.mark.parametrize('route',['direct','registry'])
def test_scale_control_s3_chart_aggregation(engine,monkeypatch,typ,mode,route):
 from data_agent.tools.registry import registry
 import data_agent.tools.visualization as v
 loop,_=engine;f=pd.DataFrame({'day':['2026-10-01','2026-10-02','2026-10-03'],'group':['A','B','C'],'amount':[2.,4.,-8.]});loop.context.workspace.add('scale_input',f);captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':metadata});raise RuntimeError('safe save interception')
 monkeypatch.setattr(v,'_save_chart',stop);p={'chart_type':typ,'data':'scale_input','x_col':'day' if typ=='line' else 'group','y_col':'amount','scale_mode':mode};r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 (AGG_E/('scale_'+typ+'_'+mode+'_'+route+'.json')).write_bytes(json.dumps({'input':p,'result':r,'captured':captured,'actual_chart_writes':0,'provider_calls':0},ensure_ascii=False,indent=2).encode())
 if typ=='bar' and mode=='index100':assert not captured and json.loads(r)['error_code']=='unsupported_scale_mode'
 else:assert len(captured)==1 and _chart_aggregation_values(captured[0]['figure']['data'][0]['y'])==({'raw':[2,4,-8],'normalize':[25,50,-100],'index100':[100,200,-400]}[mode])


@pytest.mark.parametrize('route',['direct','registry'])
def test_composite_labels_control_s3_chart_aggregation(engine,monkeypatch,route):
 from data_agent.tools.registry import registry
 import data_agent.tools.visualization as v
 loop,_=engine;f=pd.DataFrame({'region':['A | B','A',None,'null'],'segment':['C','B | C','X','X'],'amount':[2,3,4,5]});loop.context.workspace.add('label_input',f);captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':metadata});raise RuntimeError('safe save interception')
 monkeypatch.setattr(v,'_save_chart',stop);p={'chart_type':'bar','data':'label_input','label_columns':'region,segment','y_col':'amount'};r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 (AGG_E/('labels_'+route+'.json')).write_bytes(json.dumps({'input':p,'result':r,'captured':captured,'actual_chart_writes':0,'provider_calls':0},ensure_ascii=False,indent=2).encode());assert len(captured)==1,r
 t=captured[0]['figure']['data'][0];assert [json.loads(x) for x in t['x']]==[['A | B','C'],['A','B | C'],[None,'X'],['null','X']];assert _chart_aggregation_values(t['y'])==[2,3,4,5];assert loop.context.workspace.get('label_input').equals(f)


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('typ',['bar','line','stacked_bar','pie'])
@pytest.mark.parametrize('case',['count_text','count_empty'])
def test_all_original_count_modes_s3_chart_aggregation(engine,monkeypatch,route,typ,case):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_chart_aggregation_frame(case);loop.context.workspace.add('count_input',f);p=_chart_aggregation_args(case,'count_input');p.update(chart_type=typ,x_col='day' if typ=='line' else 'group')
 if typ=='stacked_bar':p['color_col']='segment'
 captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':metadata});raise RuntimeError('safe interception')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_chart_aggregation_probe('count_mode_'+typ+'_'+case+'_'+route+'.json',{'input':p,'result':r,'captured':captured,'actual_chart_writes':0,'provider_calls':0});assert len(captured)==1,r
 t=captured[0]['figure']['data'][0];assert _chart_aggregation_values(t['values'] if typ=='pie' else t['y'])==([0,0,0] if case=='count_empty' else [2,1,1])
 assert captured[0]['metadata']['aggregation_audit']['unknown_group_count']==0


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('typ',['bar','line','stacked_bar'])
@pytest.mark.parametrize('method',['sum','mean','median'])
def test_group_method_original_values_s3_chart_aggregation(engine,monkeypatch,route,typ,method):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_chart_aggregation_frame(typ);loop.context.workspace.add('methods_input',f);p=_chart_aggregation_args(typ,'methods_input');p['aggregation']=method;captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':metadata});raise RuntimeError('safe interception')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_chart_aggregation_probe('method_'+typ+'_'+method+'_'+route+'.json',{'input':p,'result':r,'captured':captured,'actual_chart_writes':0,'provider_calls':0});assert len(captured)==1,r
 assert _chart_aggregation_values(captured[0]['figure']['data'][0]['y'])==[5 if method=='sum' else 2.5,None,0]
 assert [g['valid_counts']['amount'] for g in captured[0]['metadata']['aggregation_audit']['groups']]==[2,0,1]


SERIES_E=Path(os.environ.get('DATA_AGENT_S3_CHART_SERIES_EVIDENCE','tmp/s3-chart-series-20261014-r2/evidence'));SERIES_E.mkdir(exist_ok=True)


SERIES_E=Path(os.environ.get('DATA_AGENT_S3_CHART_SERIES_EVIDENCE','tmp/s3-chart-series-20261014-r2/evidence'));SERIES_E.mkdir(exist_ok=True)


def _save_chart_series_probe(n,d):(SERIES_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _chart_series_values(v):
 if isinstance(v,list):return [None if isinstance(x,float) and x!=x else x for x in v]
 code={'i1':'b','i2':'h','i4':'i','i8':'q','u1':'B','u2':'H','u4':'I','u8':'Q','f4':'f','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return [None if isinstance(x,float) and x!=x else x for x in struct.unpack('<'+code*(len(b)//struct.calcsize(code)),b)]


def _chart_series_frame(case=''):
 f=pd.DataFrame({'group':['A','A','B','B'],'day':['2026-10-01','2026-10-01','2026-10-02','2026-10-02'],'segment':['X','Y','X','Y'],'revenue':[10,100,20,200],'exposure':[1000000,10000000,2000000,20000000]})
 if case=='count_color':f['user_id']=['u1',None,'u2','u3'];f['record_id']=['r1','r2',None,'r4']
 if case=='unknown_color':f['revenue']=f['revenue'].astype(float);f.loc[3,'revenue']=float('nan')
 return f


def _chart_series_args(case,name):
 p={'chart_type':'line' if case=='line_color' else 'bar','data':name,'x_col':'day' if case=='line_color' else 'group','y_col':'user_id,record_id' if case=='count_color' else 'revenue' if case in {'single_color','single_normalize'} else 'revenue,exposure','scale_mode':'normalize' if case in {'color_normalize','single_normalize'} else 'raw','aggregation':'count' if case=='count_color' else 'sum','title':'Grouped metrics '+case}
 if case not in {'raw_warning','multi_no_color'}:p['color_col']='segment'
 return p


def _chart_series_expected(case):
 if case in {'raw_warning','multi_no_color'}:return {'revenue':[110,220],'exposure':[11000000,22000000]}
 if case=='single_color':return {'X':[10,20],'Y':[100,200]}
 if case=='single_normalize':return {'X':[50,100],'Y':[50,100]}
 if case=='count_color':return {'X - user_id':[1,1],'Y - user_id':[0,1],'X - record_id':[1,0],'Y - record_id':[1,1]}
 if case=='unknown_color':return {'X - revenue':[10,20],'Y - revenue':[100,None],'X - exposure':[1000000,2000000],'Y - exposure':[10000000,20000000]}
 return {cat+' - '+col:([50,100] if case=='color_normalize' else raw) for col,groups in {'revenue':{'X':[10,20],'Y':[100,200]},'exposure':{'X':[1000000,2000000],'Y':[10000000,20000000]}}.items() for cat,raw in groups.items()}


def _check_chart_series(case,metadata):
 traces=metadata['figure']['data'];actual={t['name']:_chart_series_values(t['y']) for t in traces};assert actual==_chart_series_expected(case),{'actual':actual,'_chart_series_expected':_chart_series_expected(case)}
 if case not in {'color_normalize','single_normalize'}:assert not any('normalized' in w.lower() for w in metadata['validation_warnings']),metadata['validation_warnings']
 if case in {'color_normalize','single_normalize'}:
  assert {t['name']:_chart_series_values(t['customdata']) for t in traces}==_chart_series_expected('single_color' if case=='single_normalize' else 'color_raw')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['color_raw','color_normalize','raw_warning','single_color','line_color','multi_no_color','count_color','unknown_color','single_normalize'])
def test_series_cross_interfaces_s3_chart_series(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_chart_series_frame(case);loop.context.workspace.add('series_input',f);before=loop.context.workspace.get_data_identity('series_input');p=_chart_series_args(case,'series_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_chart_series_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'result':r,'captured':captured,'before':before,'after':loop.context.workspace.get_data_identity('series_input'),'actual_chart_writes':0,'provider_calls':0});assert len(captured)==1,r;m=dict(captured[0]['metadata'],figure=captured[0]['figure']);_check_chart_series(case,m)


@pytest.mark.parametrize('case', ['color_raw', 'color_normalize', 'raw_warning', 'single_color', 'line_color', 'count_color', 'unknown_color', 'single_normalize'])
def test_normal_series_user_chain_s3_chart_series(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure; actual HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；按显式参数绘图，color_col指定时按segment区分各指标，raw保留原值，normalize显示归一化值及原值。';p=_chart_series_args(case,'experiment');raw=_chart_series_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_series_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(SERIES_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_chart_series_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed','PNG':'controlled first failure'})
 assert len(ends)==1 and ends[0]['status']=='completed' and len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events
 assert md['status']=='exported' and answer['body']==saved['messages'][-1]['content']==ends[0]['reply_content'];_check_chart_series(case,metadata[0])


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('mode',['raw','normalize'])
@pytest.mark.parametrize('variant',['missing_color','composite_labels'])
def test_series_identity_and_label_controls_s3_chart_series(engine,monkeypatch,route,mode,variant):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_chart_series_frame();p=_chart_series_args('color_raw','series_extra');p['scale_mode']=mode
 if variant=='missing_color':f.loc[f['segment']=='X','segment']=None
 else:f['product']=['p | a','p | a','p | b','p | b'];p.pop('x_col');p['label_columns']='group,product'
 loop.context.workspace.add('series_extra',f);captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe save interception')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_chart_series_probe('extra_'+variant+'_'+mode+'_'+route+'.json',{'input':p,'result':r,'captured':captured,'rows':f.to_dict('records'),'actual_chart_writes':0,'provider_calls':0});assert len(captured)==1,r
 traces=captured[0]['figure']['data'];assert len(traces)==4 and all(len(t['x'])==2 for t in traces)
 for trace in traces:
  metric=trace['meta']['metric'];color=trace['meta']['color_value'];part=f[f['segment'].isna() if color is None else f['segment']==color];original=part[metric].tolist();expected=original if mode=='raw' else [x/max(map(abs,original))*100 for x in original];assert _chart_series_values(trace['y'])==expected
  assert trace['text']==['有效观测数=1；聚合=sum']*2
  if mode=='normalize':assert _chart_series_values(trace['customdata'])==original
  if variant=='composite_labels':assert [json.loads(x) for x in trace['x']]==[['A','p | a'],['B','p | b']]


MODES_E=Path(os.environ.get('DATA_AGENT_S3_CHART_MODES_EVIDENCE','tmp/s3-chart-modes-20261014-r2/evidence'));MODES_E.mkdir(exist_ok=True)


MODES_E=Path(os.environ.get('DATA_AGENT_S3_CHART_MODES_EVIDENCE','tmp/s3-chart-modes-20261014-r2/evidence'));MODES_E.mkdir(exist_ok=True)


_S3_MODES_CASES=['heat_dup','heat_dup_y','heat_color','heat_aggregation','heat_finite','heat_ok','heat_constant','heat_yonly','histogram_multi','box_multi','pie_multi','stacked_bar_multi','histogram_single','box_single','pie_single','stacked_bar_single']


_S3_MODES_REFUSE={'heat_dup','heat_dup_y','heat_color','heat_aggregation','histogram_multi','box_multi','pie_multi','stacked_bar_multi'}


def _save_chart_modes_probe(n,d):(MODES_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _chart_modes_values(v):
 if isinstance(v,list):return v
 code={'i1':'b','i2':'h','i4':'i','i8':'q','u1':'B','u2':'H','u4':'I','u8':'Q','f4':'f','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return [None if isinstance(x,float) and x!=x else x for x in struct.unpack('<'+code*(len(b)//struct.calcsize(code)),b)]


def _chart_modes_frame(case):
 f=pd.DataFrame({'a':[10,20,30,10,20,30],'b':[1,2,3,3,2,1],'c':[2,4,6,6,4,2],'segment':['X']*3+['Y']*3})
 if case=='heat_constant':f['a']=10
 if case=='heat_finite':f['a']=[10.,20.,float('inf'),40.,50.,60.];f['b']=[1.,float('nan'),3.,4.,5.,6.]
 return f


def _chart_modes_args(case,name):
 p={'chart_type':'heatmap','data':name,'x_col':'a','y_col':'b','title':'Original modes '+case}
 if case=='heat_dup':p['y_col']='a'
 if case=='heat_dup_y':p['y_col']='b,b'
 if case=='heat_color':p['color_col']='segment'
 if case=='heat_aggregation':p['aggregation']='mean'
 if case=='heat_yonly':p.update(x_col='',y_col='a,b')
 if not case.startswith('heat_'):
  typ=case.rsplit('_',1)[0];p.update(chart_type=typ,x_col='segment',y_col='b,c' if case.endswith('_multi') else 'b')
  if typ=='histogram':p['x_col']=''
  if typ=='pie':p['aggregation']='sum'
  if typ=='stacked_bar':p.update(x_col='a',color_col='segment',aggregation='sum')
 return p


def _check_chart_modes(case,m):
 t=m['figure']['data'][0]
 if case.startswith('heat_'):
  assert t['x']==['a','b'] and t['y']==['a','b'];z=_chart_modes_values(t['z']);z=[x for row in z for x in row] if z and isinstance(z[0],list) else z
  if case=='heat_constant':assert z==[None,None,None,1]
  elif case=='heat_finite':
   assert all(math.isclose(x,1,abs_tol=1e-12) for x in z);audit=m['correlation_audit'];assert audit['pairwise_counts']=={'a':{'a':5,'b':4},'b':{'a':4,'b':5}} and audit['columns']['a']['nonfinite_count']==1 and audit['columns']['b']['missing_count']==1
  else:assert all(math.isclose(x,y,abs_tol=1e-12) for x,y in zip(z,[1,0,0,1]))
 elif case=='histogram_single':assert _chart_modes_values(t['x'])==[1,2,3,3,2,1] and t['name']=='b'
 elif case=='box_single':assert _chart_modes_values(t['y'])==[1,2,3,3,2,1]
 elif case=='pie_single':assert _chart_modes_values(t['values'])==[6,6]
 else:assert len(m['figure']['data'])==2


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_MODES_CASES)
def test_modes_cross_interfaces_s3_chart_modes(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_chart_modes_frame(case);loop.context.workspace.add('mode_input',f);p=_chart_modes_args(case,'mode_input');captured=[];before=loop.context.workspace.get_data_identity('mode_input')
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_chart_modes_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'result':r,'captured':captured,'before':before,'after':loop.context.workspace.get_data_identity('mode_input'),'actual_chart_writes':0,'provider_calls':0})
 if case in _S3_MODES_REFUSE:assert not captured,'Ignored or duplicate selector reached chart _save_chart_modes_probe';assert json.loads(r)['error_type']=='chart_validation';return
 assert len(captured)==1,r;_check_chart_modes(case,dict(captured[0]['metadata'],figure=captured[0]['figure']))


@pytest.mark.parametrize('case', ['heat_dup', 'heat_color', 'heat_finite', 'heat_ok', 'heat_constant', 'histogram_multi', 'histogram_single'])
def test_normal_modes_user_chain_s3_chart_modes(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;actual HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；按明确参数展示所选列，颜色分组不得改成总体，多指标不得换为其他列；披露真实相关范围和未知。';p=_chart_modes_args(case,'experiment');raw=_chart_modes_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_modes_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(MODES_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_chart_modes_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed','PNG':'controlled first failure'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case in _S3_MODES_REFUSE:assert not html and answer['requirement_outcomes'][0]['status']!='answered' and not answer['artifact_refs'];return
 assert len(html)==1 and answer['requirement_outcomes'][0]['status']==('partial' if case=='heat_finite' else 'answered') and md['status']=='exported',events
 _check_chart_modes(case,metadata[0]);assert answer['body']==saved['messages'][-1]['content']==ends[0]['reply_content']


WRITE_E=Path(os.environ.get('DATA_AGENT_S3_CHART_WRITE_EVIDENCE','tmp/s3-chart-modes-20261014-r2/evidence-writes'));WRITE_E.mkdir(exist_ok=True)


WRITE_E=Path(os.environ.get('DATA_AGENT_S3_CHART_WRITE_EVIDENCE','tmp/s3-chart-modes-20261014-r2/evidence-writes'));WRITE_E.mkdir(exist_ok=True)


_S3_WRITE_PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf5cAAAAASUVORK5CYII=')


def _save_chart_write_probe(n,d):(WRITE_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _chart_write_files(root):return {p.relative_to(root).as_posix():p.read_bytes().hex() for p in root.rglob('*') if p.is_file() and (p.parent.name=='charts' or p.name=='artifacts.json')}


def _inject_chart_write_faults(monkeypatch,fault):
 import data_agent.tools.visualization as v
 import data_agent.utils.atomic_files as atomic
 import plotly.graph_objects as go
 fired=[];oldtext=Path.write_text;oldreplace=atomic.replace_file;oldhtml=go.Figure.write_html
 def matches(path):
  if fault=='manifest_after':return path.name=='artifacts.json' and any(x.get('type')=='chart' for x in json.loads(path.read_text(encoding='utf-8')))
  return path.parent.name=='charts' and path.suffix==('.html' if fault=='html_after' else '.json')
 def text(path,*a,**kw):
  value=oldtext(path,*a,**kw)
  if not fired and matches(path):fired.append(str(path));raise OSError('injected '+fault+' after write')
  return value
 def replace(source,destination,*a,**kw):
  value=oldreplace(source,destination,*a,**kw)
  if not fired and matches(destination):fired.append(str(destination));raise OSError('injected '+fault+' after replace')
  return value
 def html(fig,file,*a,**kw):
  value=oldhtml(fig,file,*a,**kw)
  if fault=='html_after' and not fired and isinstance(file,(str,Path)) and matches(Path(file)):fired.append(str(file));raise OSError('injected html after write')
  return value
 monkeypatch.setattr(Path,'write_text',text);monkeypatch.setattr(atomic,'replace_file',replace);monkeypatch.setattr(go.Figure,'write_html',html);monkeypatch.setattr(go.Figure,'to_image',lambda *a,**kw:_S3_WRITE_PNG)
 return fired


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('fault',['html_after','metadata_after','manifest_after'])
def test_chart_failure_rolls_back_across_interfaces_s3_chart_write(engine,monkeypatch,route,fault):
 import data_agent.tools.visualization as v
 from data_agent.session.history import session_charts_dir,list_artifacts
 loop,cfg=engine;loop.context.workspace.add('chart_input',pd.DataFrame({'group':['A','B'],'amount':[10,20]}));root=cfg.sessions_resolved/loop.session_id;session_charts_dir(loop.session_id);before=_chart_write_files(root);fired=_inject_chart_write_faults(monkeypatch,fault);p={'chart_type':'bar','data':'chart_input','x_col':'group','y_col':'amount','title':'Owned chart'};r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;after=_chart_write_files(root)
 _save_chart_write_probe('persist_'+fault+'_'+route+'.json',{'input':p,'result':str(r),'before':before,'after':after,'fired':fired,'catalogue':v.get_chart_entries(loop.session_id),'manifest':list_artifacts(loop.session_id),'root':str(root),'provider_calls':0});assert fired;assert after==before,'Failed chart left durable _chart_write_files or manifest changes'


@pytest.mark.parametrize('route',['direct','registry'])
def test_chart_uuid_collision_does_not_overwrite_existing_s3_chart_write(engine,monkeypatch,route):
 import data_agent.tools.visualization as v
 from data_agent.session.history import session_charts_dir,register_artifact
 import plotly.graph_objects as go
 loop,cfg=engine;root=cfg.sessions_resolved/loop.session_id;charts=session_charts_dir(loop.session_id);loop.context.workspace.add('chart_input',pd.DataFrame({'group':['A','B'],'amount':[10,20]}));old=charts/'Owned_chart_aabbcc.html';old.write_bytes(go.Figure(go.Bar(x=['old'],y=[7])).to_html(include_plotlyjs='/static/js/plotly-3.5.0.min.js').encode());old.with_suffix('.json').write_bytes(b'{"old_metadata":true}');old.with_suffix('.png').write_bytes(_S3_WRITE_PNG);register_artifact(loop.session_id,'sessions/'+loop.session_id+'/charts/'+old.name,'chart','old');before=_chart_write_files(root);monkeypatch.setattr(v,'uuid',SimpleNamespace(uuid4=lambda:SimpleNamespace(hex='aabbcc')));monkeypatch.setattr(go.Figure,'to_image',lambda *a,**kw:_S3_WRITE_PNG);p={'chart_type':'bar','data':'chart_input','x_col':'group','y_col':'amount','title':'Owned chart'};r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;after=_chart_write_files(root)
 _save_chart_write_probe('persist_collision_'+route+'.json',{'result':str(r),'before':before,'after':after,'root':str(root),'provider_calls':0});assert after==before,'New chart overwrote existing chart/metadata/manifest';assert 'Error' in str(r)


@pytest.mark.parametrize('fault',['metadata_after','manifest_after'])
def test_normal_chart_write_failure_user_chain_s3_chart_write(engine,monkeypatch,fault):
 import data_agent.tools.visualization as v
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False);fired=_inject_chart_write_faults(monkeypatch,fault);content='加载上传文件，将其命名为experiment；绘制真实amount柱图，失败时不能留下可下载的半成品。';p={'chart_type':'bar','data':'experiment','x_col':'group','y_col':'amount','title':'Owned chart'};raw=b'group,amount\nA,10\nB,20\n'
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_write_'+fault
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json();root=cfg.sessions_resolved/sid;downloads={q.name:h.get('/api/_chart_write_files/sessions/'+sid+'/charts/'+q.name).status_code for q in (root/'charts').glob('*.html')}
 saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None;before_md=_chart_write_files(root)
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(WRITE_E/('normal_persist_'+fault+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_chart_write_probe('normal_persist_'+fault+'.json',{'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'state':state,'session_dir':str(root),'fired':fired,'files_after_chart_failure_before_md':before_md,'downloads':downloads,'catalogue':v.get_chart_entries(sid),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert fired and len(ends)==1 and ends[0]['status']=='completed',events;assert answer['requirement_outcomes'][0]['status']!='answered' and not answer['artifact_refs'];assert not any(k.startswith('charts/') for k in before_md) and not downloads,'Failed chart remains downloadable or enumerated';assert not v.get_chart_entries(sid)


@pytest.mark.parametrize('stage',['collection','commit'])
def test_heatmap_metadata_immutable_range_proof_s3_chart_modes(engine,stage):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,collect_products
 loop,cfg=engine;loop.context.workspace.add('orders',_chart_modes_frame('heat_finite'));request(loop,'交付热图',{'kind':'chart','scope':{'datasets':['orders']}});rid,result=execute(loop,'create_chart',_chart_modes_args('heat_finite','orders'))
 assert result['completion_gap'] and result['correlation_audit']['pairwise_counts']['a']['b']==4
 path=cfg.sessions_resolved/loop.session_id/result['chart_metadata_ref'];raw=path.read_bytes();before=list(loop.context.analysis_state.accepted_answers)
 if stage=='commit':
  snap=snapshot_for_turn(loop);host=snap.as_dict();proposal=encode({'schema':'answer_bindings.v2','snapshot_digest':snap.digest,'sections':[{'requirement_ids':[r['id']],'parts':[{'kind':'artifact','ref':aid} for aid in r['artifact_ids']]} for r in host['requirements'] if not r['withdrawn']]});body,error=publish(loop,proposal);assert error is None;assert host['artifacts'][0]['target']['completion_gap'];path.write_bytes(raw+b' ');error=commit(loop,{'role':'assistant'},body);assert error and loop.context.analysis_state.accepted_answers==before
 else:
  path.write_bytes(raw+b' ');claims,artifacts,gaps,identities,effects=collect_products(loop.context.analysis_state,loop.session_id);assert not artifacts and any(g['code']=='chart_metadata' for g in gaps)
 _save_chart_modes_probe('metadata_tamper_'+stage+'.json',{'stage':stage,'result':result,'actual_metadata_path':str(path),'old_sha256':hashlib.sha256(raw).hexdigest(),'new_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'accepted_answers_unchanged':loop.context.analysis_state.accepted_answers==before,'provider_calls':0})


@pytest.mark.parametrize('route',['direct','registry'])
def test_chart_png_write_failure_retains_html_without_residual_png_s3_chart_write(engine,monkeypatch,route):
 import data_agent.tools.visualization as v
 import data_agent.utils.atomic_files as atomic
 import plotly.graph_objects as go
 loop,cfg=engine;loop.context.workspace.add('chart_input',pd.DataFrame({'group':['A','B'],'amount':[10,20]}));fired=[];native=atomic.replace_file
 def replace(source,destination,*a,**kw):
  result=native(source,destination,*a,**kw)
  if destination.suffix=='.png' and not fired:fired.append(str(destination));raise OSError('injected PNG after replace')
  return result
 monkeypatch.setattr(atomic,'replace_file',replace);monkeypatch.setattr(go.Figure,'to_image',lambda *a,**kw:_S3_WRITE_PNG);p={'chart_type':'bar','data':'chart_input','x_col':'group','y_col':'amount','title':'PNG first failure'};r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;charts=cfg.sessions_resolved/loop.session_id/'charts';metadata=json.loads(next(charts.glob('*.json')).read_text(encoding='utf-8'));assert fired and 'Chart saved:' in str(r) and len(list(charts.glob('*.html')))==1 and not list(charts.glob('*.png'));assert metadata['static_image']['status']=='failed' and metadata['static_image']['attempts']==1
 _save_chart_write_probe('png_after_'+route+'.json',{'result':str(r),'fired':fired,'files':_chart_write_files(cfg.sessions_resolved/loop.session_id),'metadata':metadata,'provider_calls':0})


def test_chart_concurrent_publications_keep_successful_manifests_after_failure_s3_chart_write(engine,monkeypatch):
 import data_agent.tools.visualization as v
 import data_agent.utils.atomic_files as atomic
 import plotly.graph_objects as go
 from concurrent.futures import ThreadPoolExecutor
 from data_agent.agent.context import use_agent_context
 from data_agent.session.history import list_artifacts
 loop,cfg=engine;loop.context.workspace.add('chart_input',pd.DataFrame({'group':['A','B'],'amount':[10,20]}));fired=[];native=atomic.replace_file
 def replace(source,destination,*a,**kw):
  result=native(source,destination,*a,**kw)
  if destination.name=='artifacts.json' and not fired and json.loads(destination.read_text(encoding='utf-8'))[-1].get('description')=='Fail chart':fired.append(str(destination));raise OSError('injected chart manifest after replace')
  return result
 monkeypatch.setattr(atomic,'replace_file',replace)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure')
 monkeypatch.setattr(go.Figure,'to_image',no_png)
 def run(title):
  with use_agent_context(loop.context):return str(v.create_chart('bar',data='chart_input',x_col='group',y_col='amount',title=title))
 titles=['Good1','Fail chart','Good2','Good3']
 with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,titles))
 root=cfg.sessions_resolved/loop.session_id;manifest=list_artifacts(loop.session_id);assert fired and sum('Chart saved:' in r for r in results)==3 and len(manifest)==3;assert {m['description'] for m in manifest}=={'Good1','Good2','Good3'} and len(list((root/'charts').glob('*.html')))==3 and not list((root/'charts').glob('Fail*'))
 for m in manifest:assert m['sha256']=='sha256:'+hashlib.sha256((root/'charts'/Path(m['path']).name).read_bytes()).hexdigest()
 _save_chart_write_probe('concurrent_manifest.json',{'titles':titles,'results':results,'fired':fired,'manifest':manifest,'root':str(root),'files':_chart_write_files(root),'provider_calls':0,'scope':'in-process original chart publications;not power loss/OS race/global app concurrency'})


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('title',['../escape','..\\escape','C:\\outside','GMV/订单数','普通标题'])
@pytest.mark.parametrize('writer',['original_preimage','current'])
def test_chart_display_title_never_becomes_file_path_s3_chart_write(engine,monkeypatch,route,title,writer):
 import ast
 import plotly.graph_objects as go
 import data_agent.tools.visualization as v
 import data_agent.utils.atomic_files as atomic
 loop,cfg=engine;loop.context.workspace.add('chart_input',pd.DataFrame({'group':['A','B'],'amount':[10,20]}));chosen=v._save_chart
 if writer=='original_preimage':
  raw=Path('tmp/s3-chart-modes-20261014-r2/preimages/src/data_agent/tools/visualization.py').read_bytes();node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='_save_chart');ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'original_writer_preimage','exec'),v.__dict__,ns);chosen=ns['_save_chart']
 targets=[];display=[]
 def observe(fig,caption,metadata):display.append(fig.layout.title.text);return chosen(fig,caption,metadata)
 def stop_html(fig,file,*a,**kw):targets.append(str(file));raise OSError('safe interception before output write')
 def stop_atomic(path,text):
  if path.suffix=='.html':targets.append(str(path));raise OSError('safe interception before output write')
  raise AssertionError('unexpected write before HTML')
 monkeypatch.setattr(v,'_save_chart',observe);monkeypatch.setattr(go.Figure,'write_html',stop_html);monkeypatch.setattr(atomic,'write_text_atomic',stop_atomic);p={'chart_type':'bar','data':'chart_input','x_col':'group','y_col':'amount','title':title};result=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;assert len(targets)==1 and display==[title];charts=(cfg.sessions_resolved/loop.session_id/'charts').resolve();bounded=Path(targets[0]).resolve().parent==charts;assert bounded==(writer=='current' or title=='普通标题');assert not list(charts.glob('*.html'))
 _save_chart_write_probe('title_'+writer+'_'+str(['../escape','..\\escape','C:\\outside','GMV/订单数','普通标题'].index(title))+'_'+route+'.json',{'input':p,'writer':writer,'target':targets[0],'display_title':display[0],'direct_owned_chart_child':bounded,'actual_writes':0,'result':str(result),'provider_calls':0,'original_probe_scope':'isolated original writer AST replay under current caller;not whole original source matrix'})


LINE_TIME_E=Path(os.environ.get('DATA_AGENT_S3_LINE_TIME_EVIDENCE','tmp/s3-line-time-20261014-r2/evidence'));LINE_TIME_E.mkdir(exist_ok=True)


LINE_TIME_E=Path(os.environ.get('DATA_AGENT_S3_LINE_TIME_EVIDENCE','tmp/s3-line-time-20261014-r2/evidence'));LINE_TIME_E.mkdir(exist_ok=True)


_S3_LINE_TIME_CASES=['hour_noagg','hour_sum','hour_index','daily_order','exact_sum','exact_noagg','daily_control']


def _save_line_time_probe(n,d):(LINE_TIME_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _line_time_values(v):
 if isinstance(v,list):return v
 code={'i1':'b','i2':'h','i4':'i','i8':'q','u1':'B','u2':'H','u4':'I','u8':'Q','f4':'f','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+code*(len(b)//struct.calcsize(code)),b))


def _line_time_frame(case):
 times=['2026-10-14 09:00:00','2026-10-14 10:00:00','2026-10-14 11:00:00'];values=[10,20,30]
 if case=='daily_order':times=['2026-10-03','2026-10-01','2026-10-02'];values=[30,10,20]
 if case=='daily_control':times=['2026-10-01','2026-10-02','2026-10-03']
 if case in {'exact_sum','exact_noagg'}:times=[times[0],*times];values=[5,5,20,30]
 return pd.DataFrame({'event_time':times,'amount':values})


def _line_time_args(case,name):
 p={'chart_type':'line','data':name,'x_col':'event_time','y_col':'amount','title':'Observed time '+case}
 if case in {'hour_sum','hour_index','exact_sum','daily_control'}:p['aggregation']='sum'
 if case=='hour_index':p['scale_mode']='index100'
 return p


def _check_line_time(case,m):
 trace=m['figure']['data'][0];xs=[str(x).replace('T',' ')[:19] for x in trace['x']];xs=[x+' 00:00:00' if len(x)==10 else x for x in xs];expected=['2026-10-01 00:00:00','2026-10-02 00:00:00','2026-10-03 00:00:00'] if case in {'daily_order','daily_control'} else ['2026-10-14 09:00:00','2026-10-14 10:00:00','2026-10-14 11:00:00'];assert xs==expected,{'actual':xs,'expected':expected};assert _line_time_values(trace['y'])==([100,200,300] if case=='hour_index' else [10,20,30])


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_LINE_TIME_CASES)
def test_time_axis_cross_interfaces_s3_line_time(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_line_time_frame(case);loop.context.workspace.add('time_input',f);before=loop.context.workspace.get_data_identity('time_input');p=_line_time_args(case,'time_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;_save_line_time_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'before':before,'after':loop.context.workspace.get_data_identity('time_input'),'actual_chart_writes':0,'provider_calls':0})
 if case=='exact_noagg':assert not captured and json.loads(r)['error_code']=='aggregation_required';return
 assert len(captured)==1,r;_check_line_time(case,dict(captured[0]['metadata'],figure=captured[0]['figure']))


@pytest.mark.parametrize('case',_S3_LINE_TIME_CASES)
def test_normal_time_axis_user_chain_s3_line_time(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；按event_time的完整时间戳顺序绘制amount趋势，仅对相同时间戳的重复记录按明确参数聚合，不改成每日总量。';p=_line_time_args(case,'experiment');raw=_line_time_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='line_time_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(LINE_TIME_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_line_time_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case=='exact_noagg':assert not html and answer['requirement_outcomes'][0]['status']!='answered';return
 assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered' and md['status']=='exported',events;_check_line_time(case,metadata[0])


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['precision_timezone','color_distinct','color_duplicates'])
def test_timestamp_precision_color_scope_s3_line_time(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,_=engine
 if case=='precision_timezone':
  stamps=[pd.Timestamp('2026-10-14T09:00:00.123456782+08:00'),pd.Timestamp('2026-10-14T09:00:00.123456781+08:00'),pd.Timestamp('2026-10-14T09:00:00.123456783+08:00')];f=pd.DataFrame({'event_time':stamps,'amount':[20,10,30]});p={'chart_type':'line','data':'time_input','x_col':'event_time','y_col':'amount','title':'Timestamp precision'}
 else:
  f=pd.DataFrame({'event_time':pd.to_datetime(['2026-10-14 10:00:00','2026-10-14 09:00:00','2026-10-14 10:00:00','2026-10-14 09:00:00']),'amount':[200,10,20,100],'segment':['Y','X','X','Y']});p={'chart_type':'line','data':'time_input','x_col':'event_time','y_col':'amount','color_col':'segment','title':'Timestamp groups'}
  if case=='color_duplicates':f.loc[1,'amount']=3;f=pd.concat([f,pd.DataFrame({'event_time':[pd.Timestamp('2026-10-14 09:00:00')],'amount':[7],'segment':['X']})],ignore_index=True);p['aggregation']='sum'
 loop.context.workspace.add('time_input',f);before=loop.context.workspace.get_data_identity('time_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;_save_line_time_probe('extra_'+case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'before':before,'after':loop.context.workspace.get_data_identity('time_input'),'actual_chart_writes':0,'provider_calls':0});assert len(captured)==1,r;ts=captured[0]['figure']['data']
 if case=='precision_timezone':assert ts[0]['x']==[t.isoformat() for t in sorted(stamps)] and _line_time_values(ts[0]['y'])==[10,20,30]
 else:
  assert {t['name']:_line_time_values(t['y']) for t in ts}=={'X':[10,20],'Y':[100,200]};assert all(t['x']==['2026-10-14T09:00:00','2026-10-14T10:00:00'] for t in ts)
 if case=='color_duplicates':assert sorted(g['row_count'] for g in captured[0]['metadata']['aggregation_audit']['groups'])==[1,1,1,2]


STACKED_GROUPS_E=Path(os.environ.get('DATA_AGENT_S3_STACKED_GROUPS_EVIDENCE','tmp/s3-stacked-groups-20261014-r2/evidence'));STACKED_GROUPS_E.mkdir(exist_ok=True)


STACKED_GROUPS_E=Path(os.environ.get('DATA_AGENT_S3_STACKED_GROUPS_EVIDENCE','tmp/s3-stacked-groups-20261014-r2/evidence'));STACKED_GROUPS_E.mkdir(exist_ok=True)


_S3_STACKED_GROUPS_CASES=['missing_color','complete_color']


def _save_stacked_groups_probe(n,d):(STACKED_GROUPS_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _stacked_groups_values(v):
 if isinstance(v,list):return v
 code={'i1':'b','i2':'h','i4':'i','i8':'q','u1':'B','u2':'H','u4':'I','u8':'Q','f4':'f','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+code*(len(b)//struct.calcsize(code)),b))


def _stacked_groups_frame(case):return pd.DataFrame({'category':['A','B','A','B'],'amount':[10,20,100,200],'segment':['X','X',None,None] if case=='missing_color' else ['X','X','Y','Y']})


def _stacked_groups_args(case,name):return {'chart_type':'stacked_bar','data':name,'x_col':'category','y_col':'amount','color_col':'segment','aggregation':'sum','title':'All groups '+case}


def _check_stacked_groups(case,m):
 traces=m['figure']['data'];assert len(traces)==2 and all(len(_stacked_groups_values(t['y']))==2 for t in traces),traces;assert sorted(v for t in traces for v in _stacked_groups_values(t['y']))==[10,20,100,200]


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_STACKED_GROUPS_CASES)
def test_stacked_groups_cross_interfaces_s3_stacked_groups(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_stacked_groups_frame(case);loop.context.workspace.add('time_input',f);before=loop.context.workspace.get_data_identity('time_input');p=_stacked_groups_args(case,'time_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;_save_stacked_groups_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'before':before,'after':loop.context.workspace.get_data_identity('time_input'),'actual_chart_writes':0,'provider_calls':0})
 if case=='exact_noagg':assert not captured and json.loads(r)['error_code']=='aggregation_required';return
 assert len(captured)==1,r;_check_stacked_groups(case,dict(captured[0]['metadata'],figure=captured[0]['figure']))


@pytest.mark.parametrize('case',_S3_STACKED_GROUPS_CASES)
def test_normal_stacked_groups_user_chain_s3_stacked_groups(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；按category绘制amount堆叠柱图，按segment分组求和，完整保留所有分组，包括缺失segment的记录。';p=_stacked_groups_args(case,'experiment');raw=_stacked_groups_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='stacked_groups_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(STACKED_GROUPS_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_stacked_groups_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case=='exact_noagg':assert not html and answer['requirement_outcomes'][0]['status']!='answered';return
 assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered' and md['status']=='exported',events;_check_stacked_groups(case,metadata[0])


FINITE_CHART_E=Path(os.environ.get('DATA_AGENT_S3_CHART_FINITE_EVIDENCE','tmp/s3-chart-finite-scope-20261014-r2/evidence'));FINITE_CHART_E.mkdir(exist_ok=True)


FINITE_CHART_E=Path(os.environ.get('DATA_AGENT_S3_CHART_FINITE_EVIDENCE','tmp/s3-chart-finite-scope-20261014-r2/evidence'));FINITE_CHART_E.mkdir(exist_ok=True)


_S3_FINITE_CHART_CASES=['bar_nonfinite','scatter_nonfinite','histogram_nonfinite','bar_control','scatter_control','histogram_control']


def _save_finite_chart_probe(n,d):(FINITE_CHART_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _finite_chart_values(v):
 if isinstance(v,list):return v
 code={'i1':'b','i2':'h','i4':'i','i8':'q','u1':'B','u2':'H','u4':'I','u8':'q','f4':'f','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+code*(len(b)//struct.calcsize(code)),b))


def _finite_chart_frame(case):return pd.DataFrame({'group':['A','A','B','C'],'input_value':[1.,2.,3.,4.],'amount':[10.,float('inf') if case.endswith('nonfinite') else 5.,20.,30.]})


def _finite_chart_args(case,name):
 typ=case.split('_',1)[0];p={'chart_type':typ,'data':name,'x_col':'group' if typ=='bar' else 'input_value' if typ=='scatter' else '', 'y_col':'amount','title':'Finite scope '+case}
 if typ=='bar':p['aggregation']='sum'
 return p


def _check_finite_chart(case,m):
 if case.endswith('nonfinite'):
  assert m.get('completion_gap',{}).get('status')=='evidence_insufficient','Nonfinite original scope silently reported complete'
  assert m.get('observation_audit',{}).get('columns',{}).get('amount',{}).get('nonfinite_count')==1,'Nonfinite exclusion not disclosed separately'
 else:assert not m.get('completion_gap')


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_FINITE_CHART_CASES)
def test_finite_chart_cross_interfaces_s3_chart_finite(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_finite_chart_frame(case);loop.context.workspace.add('time_input',f);before=loop.context.workspace.get_data_identity('time_input');p=_finite_chart_args(case,'time_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;_save_finite_chart_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'before':before,'after':loop.context.workspace.get_data_identity('time_input'),'actual_chart_writes':0,'provider_calls':0})
 if case=='exact_noagg':assert not captured and json.loads(r)['error_code']=='aggregation_required';return
 assert len(captured)==1,r;_check_finite_chart(case,dict(captured[0]['metadata'],figure=captured[0]['figure']))


@pytest.mark.parametrize('case',_S3_FINITE_CHART_CASES)
def test_normal_finite_chart_user_chain_s3_chart_finite(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；绘制amount图，完整保留请求范围并如实披露非有限值造成的缺口，不能声称原范围全部完成。';p=_finite_chart_args(case,'experiment');raw=_finite_chart_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_finite_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(FINITE_CHART_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_finite_chart_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case=='exact_noagg':assert not html and answer['requirement_outcomes'][0]['status']!='answered';return
 assert len(html)==1 and answer['requirement_outcomes'][0]['status']==('partial' if case.endswith('nonfinite') else 'answered') and md['status']=='exported',events;_check_finite_chart(case,metadata[0])


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('chart_type',['line','bar','stacked_bar','scatter','box','histogram','pie'])
@pytest.mark.parametrize('mode',['nonfinite','conversion_failed','missing'])
def test_actual_fields_range_s3_chart_finite(engine,monkeypatch,route,chart_type,mode):
 import data_agent.tools.visualization as v
 loop,_=engine;values=list(range(1,11));values[1]=float('inf') if mode=='nonfinite' else 'bad-value' if mode=='conversion_failed' else None
 f=pd.DataFrame({'group':['A']*5+['B']*5,'segment':['X','Y']*5,'when':pd.date_range('2026-10-01',periods=10).astype(str),'input_value':list(range(1,11)),'amount':values});p={'chart_type':chart_type,'data':'scope_input','x_col':'when' if chart_type=='line' else 'input_value' if chart_type=='scatter' else '' if chart_type=='histogram' else 'group','y_col':'amount','title':'Actual selected fields'}
 if chart_type in {'line','bar','stacked_bar','pie'}:p['aggregation']='sum'
 if chart_type=='stacked_bar':p['color_col']='segment'
 loop.context.workspace.add('scope_input',f);before=loop.context.workspace.get_data_identity('scope_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;_save_finite_chart_probe('range_'+chart_type+'_'+mode+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'before':before,'after':loop.context.workspace.get_data_identity('scope_input'),'actual_chart_writes':0,'provider_calls':0});assert len(captured)==1,r;m=captured[0]['metadata'];audit=m['observation_audit'];col=audit['columns']['amount'];assert col=={'source_rows':10,'missing_count':int(mode=='missing'),'non_numeric_count':int(mode=='conversion_failed'),'nonfinite_count':int(mode=='nonfinite'),'finite_count':9};assert set(audit['columns'])==({'input_value','amount'} if chart_type=='scatter' else {'amount'});assert audit['joint_unusable_numeric_rows']==int(mode!='missing');assert bool(m.get('completion_gap'))==(mode!='missing');assert any('实际数值范围' in z['text'] for z in captured[0]['figure']['layout']['annotations'])


@pytest.mark.parametrize('route',['direct','registry'])
def test_count_nonfinite_entries_remains_count_s3_chart_finite(engine,monkeypatch,route):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_finite_chart_frame('bar_nonfinite');loop.context.workspace.add('count_input',f);captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);p={'chart_type':'bar','data':'count_input','x_col':'group','y_col':'amount','aggregation':'count'};r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;_save_finite_chart_probe('count_nonfinite_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'actual_chart_writes':0,'provider_calls':0});assert len(captured)==1,r;m=captured[0]['metadata'];assert _finite_chart_values(captured[0]['figure']['data'][0]['y'])==[2,1,1] and not m.get('completion_gap');assert m['aggregation_audit']['count_semantics'].startswith('original_column_nonmissing')


@pytest.mark.parametrize('stage',['collection','commit'])
@pytest.mark.parametrize('chart_type',['bar','scatter','histogram'])
def test_finite_chart_metadata_proof_s3_chart_finite(engine,monkeypatch,stage,chart_type):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit,collect_products
 import plotly.graph_objects as go
 def no_png(*a,**kw):raise RuntimeError('controlled original first PNG failure')
 monkeypatch.setattr(go.Figure,'to_image',no_png);loop,cfg=engine;case=chart_type+'_nonfinite';loop.context.workspace.add('orders',_finite_chart_frame(case));request(loop,'交付原范围图表',{'kind':'chart','scope':{'datasets':['orders']}});rid,result=execute(loop,'create_chart',_finite_chart_args(case,'orders'));assert result['completion_gap'] and result['observation_audit']['columns']['amount']['nonfinite_count']==1;path=cfg.sessions_resolved/loop.session_id/result['chart_metadata_ref'];raw=path.read_bytes();before=list(loop.context.analysis_state.accepted_answers)
 if stage=='commit':
  snap=snapshot_for_turn(loop);host=snap.as_dict();proposal=encode({'schema':'answer_bindings.v2','snapshot_digest':snap.digest,'sections':[{'requirement_ids':[r['id']],'parts':[{'kind':'artifact','ref':aid} for aid in r['artifact_ids']]} for r in host['requirements'] if not r['withdrawn']]});body,error=publish(loop,proposal);assert error is None;assert host['artifacts'][0]['target']['completion_gap'];path.write_bytes(raw+b' ');error=commit(loop,{'role':'assistant'},body);assert error and loop.context.analysis_state.accepted_answers==before
 else:
  path.write_bytes(raw+b' ');claims,artifacts,gaps,identities,effects=collect_products(loop.context.analysis_state,loop.session_id);assert not artifacts and any(g['code']=='chart_metadata' for g in gaps)
 _save_finite_chart_probe('tamper_'+chart_type+'_'+stage+'.json',{'input':_finite_chart_args(case,'orders'),'stage':stage,'result':result,'actual_metadata_path':str(path),'old_sha256':hashlib.sha256(raw).hexdigest(),'new_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'accepted_answers_unchanged':loop.context.analysis_state.accepted_answers==before,'provider_calls':0})


PARTIAL_SELECTORS_E=Path(os.environ.get('DATA_AGENT_S3_CHART_SELECTORS_EVIDENCE','tmp/s3-chart-partial-selectors-20261014-r2/evidence'));PARTIAL_SELECTORS_E.mkdir(exist_ok=True)


PARTIAL_SELECTORS_E=Path(os.environ.get('DATA_AGENT_S3_CHART_SELECTORS_EVIDENCE','tmp/s3-chart-partial-selectors-20261014-r2/evidence'));PARTIAL_SELECTORS_E.mkdir(exist_ok=True)


_S3_PARTIAL_SELECTORS_CASES=['line_yonly','bar_yonly','box_yonly','scatter_xonly','scatter_yonly','line_default','bar_default','box_default','scatter_default','scatter_explicit']


def _save_partial_selectors_probe(n,d):(PARTIAL_SELECTORS_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _partial_selectors_values(v):
 if isinstance(v,list):return v
 code={'i1':'b','i2':'h','i4':'i','i8':'q','u1':'B','u2':'H','u4':'I','u8':'Q','f4':'f','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+code*(len(b)//struct.calcsize(code)),b))


def _partial_selectors_frame(case):return pd.DataFrame({'a':[1,2,3],'b':[10,20,30],'c':[100,200,300]})


def _partial_selectors_args(case,name):
 typ,mode=case.split('_',1);p={'chart_type':typ,'data':name,'title':'Explicit selected measure '+case}
 if mode=='yonly':p['y_col']='b' if typ!='scatter' else 'c'
 if mode=='xonly':p['x_col']='c'
 if mode=='explicit':p.update(x_col='c',y_col='b')
 return p


def _check_partial_selectors(case,m):
 ts=m['figure']['data'];typ,mode=case.split('_',1)
 if mode=='yonly':assert len(ts)==1 and _partial_selectors_values(ts[0]['y'])==([100,200,300] if typ=='scatter' else [10,20,30]),ts
 elif mode=='xonly':assert _partial_selectors_values(ts[0]['x'])==[100,200,300],ts
 elif mode=='explicit':assert _partial_selectors_values(ts[0]['x'])==[100,200,300] and _partial_selectors_values(ts[0]['y'])==[10,20,30]
 elif typ=='scatter':assert _partial_selectors_values(ts[0]['x'])==[1,2,3] and _partial_selectors_values(ts[0]['y'])==[10,20,30]
 else:assert {t['name']:_partial_selectors_values(t['y']) for t in ts}=={'a':[1,2,3],'b':[10,20,30],'c':[100,200,300]}


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_PARTIAL_SELECTORS_CASES)
def test_partial_selectors_cross_interfaces_s3_chart_selectors(engine,monkeypatch,route,case):
 import data_agent.tools.visualization as v
 loop,_=engine;f=_partial_selectors_frame(case);loop.context.workspace.add('time_input',f);before=loop.context.workspace.get_data_identity('time_input');p=_partial_selectors_args(case,'time_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':json.loads(fig.to_json()),'metadata':deepcopy(metadata)});raise RuntimeError('safe interception before chart write')
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary;_save_partial_selectors_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'before':before,'after':loop.context.workspace.get_data_identity('time_input'),'actual_chart_writes':0,'provider_calls':0})
 if case in {'scatter_xonly','scatter_yonly'}:assert not captured and json.loads(r)['error_code']=='incomplete_scatter_axes';return
 assert len(captured)==1,r;_check_partial_selectors(case,dict(captured[0]['metadata'],figure=captured[0]['figure']))


@pytest.mark.parametrize('case', ['line_yonly', 'bar_default', 'box_yonly', 'scatter_xonly', 'scatter_yonly', 'scatter_explicit'])
def test_normal_partial_selectors_user_chain_s3_chart_selectors(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按我明确指定的轴列和指标绘图，不得改选其他列。';p=_partial_selectors_args(case,'experiment');raw=_partial_selectors_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='partial_selector_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(PARTIAL_SELECTORS_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_partial_selectors_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case in {'scatter_xonly','scatter_yonly'}:assert not html and answer['requirement_outcomes'][0]['status']!='answered' and not answer['artifact_refs'];return
 assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered' and md['status']=='exported',events;_check_partial_selectors(case,metadata[0])


CHART_ERROR_E=Path(os.environ.get('DATA_AGENT_S3_CHART_ERROR_EVIDENCE','tmp/s3-chart-error-delivery-20261014-r3/evidence-promoted'));CHART_ERROR_E.mkdir(exist_ok=True)


CHART_ERROR_E=Path(os.environ.get('DATA_AGENT_S3_CHART_ERROR_EVIDENCE','tmp/s3-chart-error-delivery-20261014-r3/evidence-promoted'));CHART_ERROR_E.mkdir(exist_ok=True)


_S3_CHART_ERROR_CASES=['scatter_incomplete','heat_aggregation','histogram_multi']


def _save_chart_error_probe(n,d):(CHART_ERROR_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _chart_error_frame(case):return pd.DataFrame({'a':[1,2,3],'b':[10,20,30],'c':[100,200,300]})


def _chart_error_args(case,name):
 p={'chart_type':'scatter','data':name,'x_col':'c','title':'Known typed rejection'}
 if case=='heat_aggregation':p.update(chart_type='heatmap',x_col='a',y_col='b',aggregation='mean')
 if case=='histogram_multi':p.update(chart_type='histogram',x_col='',y_col='b,c')
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_CHART_ERROR_CASES)
def test_s3_chart_error_failed_producer_result_is_retained_with_binding(engine,route,case):
 from data_agent.tools.visualization import create_chart
 loop,cfg=engine;loop.context.workspace.add('error_input',_chart_error_frame(case));request(loop,'交付指定图表，明确失败原因',{'kind':'chart','scope':{'datasets':['error_input']}});plan=loop.context.analysis_state.analysis_plan;step=plan['method_plan'][0];p=_chart_error_args(case,'error_input');binding=loop._capture_tool_execution_binding('create_chart',p);binding.update(plan_id=plan['id'],plan_sha256=plan['plan_sha256'],step_id=step['step_id'],requirement_ids=step['requirement_ids'],required_delivery_ids=[d['id'] for d in step['required_deliveries']]);r=create_chart(**p) if route=='direct' else registry.execute('create_chart',p);summary=str(r) if route=='direct' else r.summary;structured=json.loads(summary) if route=='direct' else r.data;rid=loop._record_turn_tool_result('create_chart',summary,p,'failed-chart-call',structured,execution_binding=binding);_save_chart_error_probe('record_'+case+'_'+route+'.json',{'input':p,'structured_error':structured,'binding':binding,'recorded_id':rid,'receipts':loop.context.analysis_state.tool_receipts,'provider_calls':0,'scope':'unit-isolated before-execution fixture binding;not normal app'});assert structured.get('error_type')=='chart_validation';assert not rid, 'A failed producer must not grant a successful receipt'
 from data_agent.agent.publication.deliveries import project_deliveries
 _,projection=project_deliveries(loop.context.analysis_state.answer_requirements,[])
 gap=projection[step['required_deliveries'][0]['id']]['gap']
 assert gap['status']=='failed' and structured['error'] in gap['reason'], 'Known typed rejection must survive in the existing necessary-delivery gap'


@pytest.mark.parametrize('case',_S3_CHART_ERROR_CASES+['scatter_retry'])
def test_s3_chart_error_normal_rejection_reason_reaches_final_answer(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按我明确指定的轴列和指标绘图，不得改选其他列。';p=_chart_error_args(case,'experiment');p.update({'y_col':'b'} if case=='scatter_retry' else {});raw=_chart_error_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}],preparatory_calls=[('create_chart',_chart_error_args('scatter_incomplete','experiment'))] if case=='scatter_retry' else []);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_error_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(CHART_ERROR_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_chart_error_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case=='scatter_retry':
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered' and model.calls==['describe_dataset','record_analysis_plan','create_chart','create_chart'],events
  assert not state['answer_requirements'][0].get('source_binding',{}).get('delivery_failures')
  return
 assert not html and answer['requirement_outcomes'][0]['status']!='answered',events
 failure=next(v['web']['data'] for k,v in events if k=='tool_result' and v['name']=='create_chart')
 assert failure['error'] in answer['body'],'Known typed producer rejection disappeared from the final goal gap'


def _chart_error_attempt(loop):
 from data_agent.tools.visualization import create_chart
 loop.context.workspace.add('error_input',_chart_error_frame('scatter_incomplete'))
 request(loop,'交付指定图表，明确失败原因',{'kind':'chart','scope':{'datasets':['error_input']}})
 plan=loop.context.analysis_state.analysis_plan;step=plan['method_plan'][0];p=_chart_error_args('scatter_incomplete','error_input');binding=loop._capture_tool_execution_binding('create_chart',p)
 binding.update(plan_id=plan['id'],plan_sha256=plan['plan_sha256'],step_id=step['step_id'],requirement_ids=step['requirement_ids'],required_delivery_ids=[d['id'] for d in step['required_deliveries']])
 r=create_chart(**p);return p,binding,json.loads(str(r)),step


@pytest.mark.parametrize('fault',['unbound','session','arguments','plan','digest','step','requirement','delivery','identity','source','error_type'])
def test_s3_chart_error_failed_attempt_cannot_borrow_other_binding(engine,fault):
 loop,_=engine;p,b,e,step=_chart_error_attempt(loop);state=loop.context.analysis_state;before=deepcopy(state.answer_requirements)
 if fault=='unbound':b=None
 elif fault=='session':b.setdefault('producer_binding',{})['session_id']='other'
 elif fault=='arguments':p=dict(p,y_col='b')
 elif fault=='plan':b['plan_id']='other'
 elif fault=='digest':b['plan_sha256']='other'
 elif fault=='step':b['step_id']='other'
 elif fault=='requirement':b['requirement_ids']=['other']
 elif fault=='delivery':b['required_delivery_ids']=['other']
 elif fault=='identity':b['input_data_identities']['error_input']['version_id']='other'
 elif fault=='source':p=dict(p,data='orders')
 elif fault=='error_type':e['error_type']='untrusted'
 rid=loop._record_turn_tool_result('create_chart',json.dumps(e),p,'invalid-binding',e,execution_binding=b)
 _save_chart_error_probe('guard_'+fault+'.json',{'fault':fault,'binding':b,'arguments':p,'error':e,'requirements_unchanged':state.answer_requirements==before,'recorded_id':rid,'provider_calls':0})
 assert not rid and state.answer_requirements==before


@pytest.mark.parametrize('change',['plan','source'])
def test_s3_chart_error_failure_reason_is_not_reused_after_binding_changes(engine,change):
 from data_agent.agent.publication.deliveries import project_deliveries
 loop,_=engine;p,b,e,step=_chart_error_attempt(loop);loop._record_turn_tool_result('create_chart',json.dumps(e),p,'bound-failure',e,execution_binding=b);state=loop.context.analysis_state
 _,before=project_deliveries(state.answer_requirements,[]);assert before[step['required_deliveries'][0]['id']]['gap']['status']=='failed'
 if change=='plan':state.analysis_plan=dict(state.analysis_plan,id='changed')
 else:loop.context.workspace.add('error_input',pd.DataFrame({'a':[4,5,6],'b':[40,50,60],'c':[400,500,600]}))
 _,after=project_deliveries(state.answer_requirements,[]);gap=after[step['required_deliveries'][0]['id']]['gap'];_save_chart_error_probe('stale_'+change+'.json',{'before':before,'after':after,'provider_calls':0});assert gap['status']=='not_computed' and e['error'] not in gap['reason']


def test_s3_chart_error_failed_annotation_save_rolls_back(engine,monkeypatch):
 loop,_=engine;p,b,e,step=_chart_error_attempt(loop);state=loop.context.analysis_state;before=deepcopy(state.answer_requirements)
 def fail():raise OSError('controlled existing goal persistence failure')
 monkeypatch.setattr(state,'save',fail)
 with pytest.raises(OSError,match='controlled existing goal'):loop._record_turn_tool_result('create_chart',json.dumps(e),p,'persist-fail',e,execution_binding=b)
 assert state.answer_requirements==before
 _save_chart_error_probe('save_rollback.json',{'requirements_unchanged':True,'provider_calls':0})


CHART_PARAMETERS_E=Path(os.environ.get('DATA_AGENT_S3_CHART_PARAMETERS_EVIDENCE','tmp/s3-chart-ignored-parameters-20261014-r2/evidence-promoted'));CHART_PARAMETERS_E.mkdir(exist_ok=True)


CHART_PARAMETERS_E=Path(os.environ.get('DATA_AGENT_S3_CHART_PARAMETERS_EVIDENCE','tmp/s3-chart-ignored-parameters-20261014-r2/evidence-promoted'));CHART_PARAMETERS_E.mkdir(exist_ok=True)


def _save_chart_parameters_probe(n,d):(CHART_PARAMETERS_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


_S3_CHART_PARAMETERS_CASES=['box_color','histogram_color','pie_color','box_aggregation','histogram_aggregation','scatter_aggregation']


def _chart_parameters_frame(case):return pd.DataFrame({'group':['A','A','B','B'],'segment':['X','Y','X','Y'],'a':[1,2,3,4],'b':[10,20,30,40]})


def _chart_parameters_args(case,name):
 typ,mode,*rest=case.split('_');p={'chart_type':typ,'data':name,'x_col':'a' if typ=='scatter' else '' if typ=='histogram' else 'group','y_col':'b','title':'Explicit requested parameter '+case}
 if typ=='pie':p['aggregation']='sum'
 if not rest:p['color_col' if mode=='color' else 'aggregation']='segment' if mode=='color' else 'sum'
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_CHART_PARAMETERS_CASES+[c+'_control' for c in _S3_CHART_PARAMETERS_CASES])
def test_explicit_chart_parameter_cannot_be_silently_ignored_s3_chart_parameters(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_chart_parameters_frame(case);loop.context.workspace.add('parameter_input',f);captured=[];p=_chart_parameters_args(case,'parameter_input')
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_chart_parameters_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 if case.endswith('_control'):assert len(captured)==1;return
 assert not captured,'Unsupported explicit parameter reached chart _save_chart_parameters_probe and was ignored'
 error=json.loads(str(r));assert error['error_type']=='chart_validation' and error['error_code']==('unsupported_chart_color' if '_color' in case else 'unsupported_chart_aggregation')


@pytest.mark.parametrize('case',['box_color','box_color_control','histogram_color_control','pie_color_control','scatter_aggregation_control'])
def test_normal_rejection_reason_reaches_final_answer_s3_chart_parameters(engine,monkeypatch,case):
 import plotly.graph_objects as go
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 from data_agent.llm.client import Response
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;HTML retained')
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按我明确指定的轴列和指标绘图，不得改选其他列。';p=_chart_parameters_args(case,'experiment');raw=_chart_parameters_frame(case).to_csv(index=False).encode()
 class Model(_NativeProductModel):
  def chat(self,messages,system='',**kw):
   r=super().chat(messages,system=system,**kw)
   if r.tool_calls or system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return r
   view=ScriptedClient._current_host_snapshot(messages,system);return Response(text=encode({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[z['id']],'parts':[{'kind':'artifact','ref':aid} for aid in z.get('artifact_ids',[])]} for z in view['requirements'] if not z['withdrawn']]}))
 model=Model(content,'experiment','create_chart',p,[{'kind':'chart','scope':{'datasets':['experiment']}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='chart_error_'+case
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;html=list((root/'charts').glob('*.html'));metadata=[json.loads(z.with_suffix('.json').read_text(encoding='utf-8')) for z in html];state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));ends=[v for k,v in events if k=='turn_end'];md=None
 if ends and ends[0]['status']=='completed' and answer:
  with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
  if md['status']=='exported':(CHART_PARAMETERS_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_chart_parameters_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case.endswith('_control'):assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events;return
 assert not html and answer['requirement_outcomes'][0]['status']=='failed','Explicit unsupported parameter was ignored but goal was answered'
 error=next(v['web']['data'] for k,v in events if k=='tool_result' and v['name']=='create_chart');assert error['error'] in answer['body']


AXIS_SELECTION_E=Path(os.environ.get('DATA_AGENT_S3_AXIS_SELECTION_EVIDENCE','tmp/s3-chart-axis-selection-20261014-r2/evidence-promoted'));AXIS_SELECTION_E.mkdir(exist_ok=True)


AXIS_SELECTION_E=Path(os.environ.get('DATA_AGENT_S3_AXIS_SELECTION_EVIDENCE','tmp/s3-chart-axis-selection-20261014-r2/evidence-promoted'));AXIS_SELECTION_E.mkdir(exist_ok=True)



def _original_blocked_count_chart(engine,tmp_path,monkeypatch,route,typ,fault=''):
 import data_agent.tools.visualization as v
 from data_agent.tools.data_io import load_data
 from data_agent.agent.publication.facts import load_receipt_result
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish
 from tests.test_source_unit_boundary import _ac25_unit_plan
 from tests.test_slice3_method_integrity import _p1_original_call
 loop,cfg=engine;frame=_chart_aggregation_frame('count_empty')
 if fault=='sum':frame['amount']=[1]*len(frame)
 path=tmp_path/'source.csv';frame.to_csv(path,index=False);load_data(str(path),'sales');p=_chart_aggregation_args('count_empty','sales');p.update(chart_type=typ,x_col='day' if typ=='line' else 'group',aggregation='sum' if fault=='sum' else 'count')
 if typ=='stacked_bar':p['color_col']='segment'
 if fault=='sum':p['y_col']='amount'
 request(loop,'按原指定列的非缺失记录数绘图，零计数也保留；不能据此声称人数去重、坏表可分析或方法就绪。',[dict(kind='chart',scope=dict(datasets=['sales'],parameters=dict(chart_type=typ))),dict(kind='measurement',scope=dict(datasets=['sales'],quantity='rows'))]);state=loop.context.analysis_state;goal=loop.context.turn_requirement_ids[0];_ac25_unit_plan(loop,route,['sales'],[dict(id=d['id']) for q in state.answer_requirements if q['id']==goal for d in q['necessary_deliveries']],'count_diagnostic')
 def no_png(*a,**kw):raise RuntimeError('controlled first PNG failure;actual HTML retained')
 monkeypatch.setattr(v.go.Figure,'to_image',no_png);save=v._save_chart
 def original_result(fig,title,metadata):
  if fault=='value':fig.data[0].y=[9]*len(fig.data[0].y)
  if fault=='axis':fig.data[0].x=['wrong']*len(fig.data[0].x)
  if fault=='effective_count':metadata['aggregation_audit']['groups'][0]['valid_counts']['user_id']=9
  return save(fig,title,metadata)
 monkeypatch.setattr(v,'_save_chart',original_result)
 from data_agent.tools.registry import _to_tool_result
 binding=loop._capture_tool_execution_binding('create_chart',p);plan=state.analysis_plan;step=plan['method_plan'][0]
 binding.update(plan_id=plan['id'],plan_sha256=plan['plan_sha256'],step_id=step['step_id'],requirement_ids=step['requirement_ids'],required_delivery_ids=[d['id'] for d in step['required_deliveries']])
 call=_to_tool_result(registry.get('create_chart').func(**p)) if route=='direct' else registry.execute('create_chart',p)
 rid=loop._record_turn_tool_result('create_chart',call.summary,p,'count_original',call.data,execution_binding=binding)
 context,receipt,result,binding=load_receipt_result(session_id=loop.session_id,receipt_id=rid)
 root=cfg.sessions_resolved/loop.session_id;html=root/'charts'/Path(result['artifact_path']).name;meta=html.with_suffix('.json');original_meta=meta.read_bytes();original_html=html.read_bytes()
 _p1_original_call(loop,route,'describe_dataset',dict(name='sales'))
 if fault in {'missing_metadata','missing_html'}:
  source=meta if fault=='missing_metadata' else html;destination=tmp_path/('retained-original'+source.suffix)
  assert source.resolve().is_relative_to(tmp_path.resolve()) and destination.resolve().is_relative_to(tmp_path.resolve()) and not destination.exists();source.replace(destination)
 if fault=='metadata_bytes':(tmp_path/'metadata-before.json').write_bytes(original_meta);meta.write_bytes(original_meta+b'\n')
 snap=snapshot_for_turn(loop);host=snap.as_dict();parts=[dict(kind='claim',ref=cid) for q in host['requirements'] for cid in q['claim_ids']]+[dict(kind='artifact',ref=aid) for q in host['requirements'] for aid in q.get('artifact_ids',[])]
 body,error=publish(loop,encode(dict(schema='answer_bindings.v2',snapshot_digest=snap.digest,sections=[dict(requirement_ids=[goal],parts=parts)])));answer=loop._accepted_answer
 (tmp_path/'original-count-delivery.json').write_text(json.dumps(dict(route=route,type=typ,fault=fault,receipt=receipt,result=result,answer=answer,original_metadata=json.loads(original_meta),html_sha256=hashlib.sha256(original_html).hexdigest(),Provider=0,remote_MCP=0),ensure_ascii=False,indent=2),encoding='utf-8')
 assert error is None
 assert any(c['value']==5 and c['target'].get('statistic')=='rows' for c in host['claims'])
 assert (answer['requirement_outcomes'][-1]['status']=='answered')==(not fault)
 if not fault:
  assert len(answer['artifact_refs'])==1
  metadata=json.loads(original_meta);assert [g['valid_counts']['user_id'] for g in metadata['aggregation_audit']['groups']]==[0,0,0]
  assert metadata['aggregation_audit']['count_semantics']=='original_column_nonmissing_entries; not distinct users'
 return answer


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('typ',['bar','line','stacked_bar','pie'])
def test_original_count_chart_cross_interface_quality_gate_keeps_exact_record_zeros(engine,tmp_path,monkeypatch,route,typ):
 _original_blocked_count_chart(engine,tmp_path,monkeypatch,route,typ)


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('fault',['value','axis','effective_count','metadata_bytes','missing_metadata','missing_html','sum'])
def test_original_count_chart_proof_rejects_faults_and_other_method_preserving_rows(engine,tmp_path,monkeypatch,route,fault):
 _original_blocked_count_chart(engine,tmp_path,monkeypatch,route,'bar',fault)
