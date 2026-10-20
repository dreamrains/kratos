from tests.support.publication_runtime import audit_reasons
from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: axes. Shared fixtures have one owner."""
from data_agent.agent.publication.contracts import encode
from data_agent.tools.registry import ToolResult
from data_agent.tools.registry import registry
from pathlib import Path
import io
import json
import os
import pandas as pd
import pytest
from tests.support.publication_runtime import _NativeProductModel
from tests.test_publication_runtime_charts import AXIS_SELECTION_E
from tests.test_publication_runtime_inference import test_normal_app_topn_original_precision_exact_range_and_real_effect_sse_save_refresh_export as _test_normal_app_topn_original_precision_exact_range_and_real_effect_sse_save_refresh_export
from tests.test_publication_runtime_tabular import test_normal_app_period_comparison_real_sums_unknown_scope_sse_save_refresh_export as _test_normal_app_period_comparison_real_sums_unknown_scope_sse_save_refresh_export

def _save_axis_selection_probe(n,d):(AXIS_SELECTION_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


def _axis_selection_frame(case):return pd.DataFrame({'a':[1,2,3],'b':[10,20,30],'c':[100,200,300]})


_S3_AXIS_SELECTION_CASES=['line_xonly','bar_xonly','histogram_conflict']


_S3_AXIS_SELECTION_CONTROLS=[c+'_control' for c in _S3_AXIS_SELECTION_CASES]+['line_yonly_control','bar_yonly_control','line_default_control','bar_default_control','histogram_xonly_control','histogram_yonly_control','histogram_default_control']


def _axis_selection_args(case,name):
 typ=case.split('_')[0];control=case.endswith('_control');p={'chart_type':typ,'data':name,'x_col':'a' if typ=='histogram' else 'c','y_col':('a' if control else 'b') if typ=='histogram' else 'b' if control else '', 'title':'Explicit axis identity '+case}
 if '_yonly_control' in case:p.update(x_col='',y_col='b')
 if '_default_control' in case:p.update(x_col='',y_col='')
 if case=='histogram_xonly_control':p.update(x_col='a',y_col='')
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_S3_AXIS_SELECTION_CASES+_S3_AXIS_SELECTION_CONTROLS)
def test_explicit_axis_cannot_be_silently_ignored_s3_chart_axis_selection(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_axis_selection_frame(case);loop.context.workspace.add('axis_input',f);p=_axis_selection_args(case,'axis_input');captured=[]
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _save_axis_selection_probe(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 if case.endswith('_control'):assert len(captured)==1;return
 assert not captured,'Explicit x axis was silently replaced or discarded'
 error=json.loads(str(r));assert error['error_type']=='chart_validation' and error['error_code']==('conflicting_histogram_selectors' if p['chart_type']=='histogram' else 'missing_explicit_chart_measure')


@pytest.mark.parametrize("case", ['line_xonly', 'bar_xonly', 'histogram_conflict', 'line_yonly_control', 'bar_default_control', 'histogram_yonly_control'])
def test_normal_rejection_reason_reaches_final_answer_s3_chart_axis_selection(engine,monkeypatch,case):
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
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按我明确指定的轴列和指标绘图，不得改选其他列。';p=_axis_selection_args(case,'experiment');raw=_axis_selection_frame(case).to_csv(index=False).encode()
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
  if md['status']=='exported':(AXIS_SELECTION_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _save_axis_selection_probe('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case.endswith('_control'):assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events;return
 assert not html and answer['requirement_outcomes'][0]['status']=='failed','Explicit axis discarded but normal goal answered'
 error=next(v['web']['data'] for k,v in events if k=='tool_result' and v['name']=='create_chart');assert error['error'] in audit_reasons(answer) and error['error'] not in answer['body']


_s3_funnel_line_E=Path(os.environ.get('DATA_AGENT_S3_CHART_FUNNEL_LINE_EVIDENCE','tmp/s3-chart-funnel-and-line-20261014-r3/evidence-promoted'));_s3_funnel_line_E.mkdir(parents=True,exist_ok=True)


_s3_funnel_line_E=Path(os.environ.get('DATA_AGENT_S3_CHART_FUNNEL_LINE_EVIDENCE','tmp/s3-chart-funnel-and-line-20261014-r3/evidence-promoted'));_s3_funnel_line_E.mkdir(parents=True,exist_ok=True)


def _s3_funnel_line_save(n,d):(_s3_funnel_line_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


_s3_funnel_line_EXTRAS=['line_numeric_color','line_category_color','line_mean','line_median','line_count','line_unknown','funnel_xonly','funnel_yonly','funnel_strings','funnel_floatints']


_s3_funnel_line_CASES=['funnel_negative','funnel_fraction','funnel_nonfinite','funnel_selector','funnel_multi','funnel_color','funnel_aggregation','line_category','line_numeric']


def _s3_funnel_line_frame(case):
 control=case.endswith('_control');base=case.removesuffix('_control')
 if case in _s3_funnel_line_EXTRAS:
  if case.startswith('line_'):
   if case=='line_unknown':return pd.DataFrame({'axis':['B','B','A','C'],'amount':[None,None,2.,0.]})
   f=pd.DataFrame({'axis':[2,1,2,1,3,3], 'amount':[10.,2.,30.,6.,None,0.], 'segment':['X','X','X','Y',None,None]})
   if case=='line_category_color':f['axis']=['B','A','B','A','C','C']
   if case=='line_count':f['amount']=['a',None,'b','c',None,'d']
   return f
  return pd.DataFrame({'step':['A','B'],'count':['100','50'] if case=='funnel_strings' else [100.,50.], 'label':['C','D'],'value':[9.,1.]})
 if base.startswith('line_'):
  return pd.DataFrame({'axis':(['A','B'] if base=='line_category' else [1,2]) if control else ['A','A','B'] if base=='line_category' else [1,1,2],'amount':[30,30] if control else [10,20,30]})
 if base=='funnel_aggregation':return pd.DataFrame({'step':['A','A','B'],'count':[60,40,50],'label':['C','D','_s3_funnel_line_E'],'value':[9,1,3],'segment':['X','Y','X']})
 f=pd.DataFrame({'step':['A','B'],'count':[100.,50.],'label':['C','D'],'value':[9.,1.],'segment':['X','Y']})
 if not control and base in {'funnel_negative','funnel_fraction','funnel_nonfinite'}:f.loc[1,'count']={'funnel_negative':-5.,'funnel_fraction':.5,'funnel_nonfinite':float('inf')}[base]
 return f


def _s3_funnel_line_args(case,name):
 control=case.endswith('_control');base=case.removesuffix('_control');p={'chart_type':'line' if base.startswith('line_') else 'funnel','data':name,'title':'Remaining requested mode '+case}
 if case in _s3_funnel_line_EXTRAS:
  if case.startswith('line_'):
   p.update(x_col='axis',y_col='amount',aggregation=case.removeprefix('line_') if case in {'line_mean','line_median','line_count'} else 'sum')
   if case.endswith('_color'):p['color_col']='segment'
  elif case=='funnel_xonly':p['x_col']='label'
  elif case=='funnel_yonly':p['y_col']='value'
  return p
 if base.startswith('line_'):p.update(x_col='axis',y_col='amount',aggregation='' if control else 'sum');return p
 if base=='funnel_selector':p.update(x_col='step' if control else 'label',y_col='count' if control else 'value')
 if base=='funnel_multi':p.update(x_col='step',y_col='count' if control else 'count,value')
 if base=='funnel_color' and not control:p['color_col']='segment'
 if base=='funnel_aggregation':p.update(x_col='step',y_col='count',aggregation='' if control else 'sum')
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_s3_funnel_line_CASES+[c+'_control' for c in _s3_funnel_line_CASES]+_s3_funnel_line_EXTRAS)
def test_cross_interface_s3_chart_funnel_line(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_s3_funnel_line_frame(case);loop.context.workspace.add('remaining_input',f);captured=[];p=_s3_funnel_line_args(case,'remaining_input')
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _s3_funnel_line_save(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 if case.endswith('_control') or case in _s3_funnel_line_EXTRAS:
  assert len(captured)==1;_s3_funnel_line_assert_plot(case,captured[0]['figure'],captured[0]['metadata']);return
 if case=='funnel_selector':
  assert len(captured)==1;trace=captured[0]['figure']['data'][0];assert list(trace['x'])==[9.,1.] and list(trace['y'])==['C','D'];return
 if case.startswith('line_'):
  assert len(captured)==1;_s3_funnel_line_assert_plot(case,captured[0]['figure'],captured[0]['metadata']);return
 assert not captured,'Invalid counts or unsupported explicit grouping/aggregation reached chart _s3_funnel_line_save'


@pytest.mark.parametrize('case',['funnel_negative', 'funnel_nonfinite', 'funnel_selector', 'funnel_multi', 'line_category', 'line_numeric', 'funnel_negative_control', 'funnel_selector_control', 'funnel_aggregation_control', 'line_category_control', 'line_numeric_control', 'line_numeric_color', 'line_category_color', 'line_count', 'line_unknown', 'funnel_xonly', 'funnel_yonly'])
def test_normal_user_chain_s3_chart_funnel_line(engine,monkeypatch,case):
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
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按明确选列、分组及聚合绘图，不得忽略参数，也不得把非法计数当作有效计数。';p=_s3_funnel_line_args(case,'experiment');raw=_s3_funnel_line_frame(case).to_csv(index=False).encode()
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
  if md['status']=='exported':(_s3_funnel_line_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _s3_funnel_line_save('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case.endswith('_control') or case in _s3_funnel_line_EXTRAS:
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events;_s3_funnel_line_assert_plot(case,metadata[0]['figure'],metadata[0]);return
 if case=='funnel_selector':
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered';trace=metadata[0]['figure']['data'][0];assert trace['x']==[9.,1.] and trace['y']==['C','D'];return
 if case.startswith('line_'):
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered';_s3_funnel_line_assert_plot(case,metadata[0]['figure'],metadata[0]);return
 assert not html and answer['requirement_outcomes'][0]['status']!='answered','Invalid counts or ignored explicit parameter was delivered as completed'


def _s3_funnel_line_assert_plot(case,figure,metadata):
 import base64,struct,math,statistics
 def values(v):
  if isinstance(v,list):return v
  c={'i1':'b','i2':'h','i4':'i','i8':'q','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+c*(len(b)//struct.calcsize(c)),b))
 def clean(v):return None if v is None or isinstance(v,float) and not math.isfinite(v) else v
 p=_s3_funnel_line_args(case,'remaining_input');rows=_s3_funnel_line_frame(case).to_dict('records');traces=figure['data']
 if p['chart_type']=='funnel':
  x=p.get('x_col') or 'step';y=p.get('y_col') or 'count'
  assert traces[0]['y']==[str(r[x]) for r in rows]
  assert values(traces[0]['x'])==[float(r[y]) for r in rows];return
 if not p['aggregation']:
  assert [clean(v) for v in values(traces[0]['y'])]==[clean(r['amount']) for r in rows];return
 groups={}
 for r in rows:groups.setdefault((clean(r['axis']),clean(r.get('segment')) if p.get('color_col') else None),[]).append(r['amount'])
 def agg(v):
  finite=[x for x in v if clean(x) is not None]
  if p['aggregation']=='count':return len(finite)
  if not finite:return None
  return sum(finite) if p['aggregation']=='sum' else statistics.mean(finite) if p['aggregation']=='mean' else statistics.median(finite)
 expected={k:agg(v) for k,v in groups.items()}
 audit=metadata['aggregation_audit']['groups']
 assert {(g['group']['axis'],g['group'].get('segment')):g['values']['amount'] for g in audit}==expected
 assert {(g['group']['axis'],g['group'].get('segment')):g['valid_counts']['amount'] for g in audit}=={k:sum(clean(x) is not None for x in v) for k,v in groups.items()}
 for t in traces:
  color=(None if t['name'] in {'nan','None','<NA>'} else t['name']) if p.get('color_col') else None
  keys=[k for k in groups if k[1]==color]
  if all(isinstance(k[0],(int,float)) for k in keys):keys.sort(key=lambda k:k[0])
  assert list(t['x'])==[k[0] for k in keys]
  assert [clean(v) for v in values(t['y'])]==[expected[k] for k in keys]


_s3_box_axis_E=Path(os.environ.get('DATA_AGENT_S3_CHART_BOX_AXIS_EVIDENCE','tmp/s3-chart-box-axis-20261014-r2/evidence-promoted'));_s3_box_axis_E.mkdir(parents=True,exist_ok=True)


_s3_box_axis_E=Path(os.environ.get('DATA_AGENT_S3_CHART_BOX_AXIS_EVIDENCE','tmp/s3-chart-box-axis-20261014-r2/evidence-promoted'));_s3_box_axis_E.mkdir(parents=True,exist_ok=True)


def _s3_box_axis_save(n,d):(_s3_box_axis_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


_s3_box_axis_CASES=['box_xonly'];_s3_box_axis_CONTROLS=['box_xonly_control','box_yonly_control','box_default_control']


_s3_box_axis_CASES=['box_xonly'];_s3_box_axis_CONTROLS=['box_xonly_control','box_yonly_control','box_default_control']


def _s3_box_axis_frame(case):return pd.DataFrame({'segment':['X','X','Y','Y'],'a':[1,2,10,20],'b':[100,200,300,400]})


def _s3_box_axis_args(case,name):
 p={'chart_type':'box','data':name,'title':'Explicit box category'}
 if case=='box_xonly_control':p.update(x_col='segment',y_col='a')
 elif case=='box_yonly_control':p['y_col']='a'
 elif case=='box_default_control':pass
 else:p['x_col']='segment'
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_s3_box_axis_CASES+_s3_box_axis_CONTROLS)
def test_cross_interface_s3_chart_box_axis(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_s3_box_axis_frame(case);loop.context.workspace.add('remaining_input',f);captured=[];p=_s3_box_axis_args(case,'remaining_input')
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _s3_box_axis_save(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 if case.endswith('_control'):
  assert len(captured)==1;_s3_box_axis_assert_plot(case,captured[0]['figure']);return
 assert not captured;error=json.loads(str(r));assert error['error_type']=='chart_validation' and error['error_code']=='missing_explicit_chart_measure'


@pytest.mark.parametrize('case',_s3_box_axis_CASES+_s3_box_axis_CONTROLS)
def test_normal_user_chain_s3_chart_box_axis(engine,monkeypatch,case):
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
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按明确选列、分组及聚合绘图，不得忽略参数，也不得把非法计数当作有效计数。';p=_s3_box_axis_args(case,'experiment');raw=_s3_box_axis_frame(case).to_csv(index=False).encode()
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
  if md['status']=='exported':(_s3_box_axis_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _s3_box_axis_save('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case.endswith('_control'):
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events;_s3_box_axis_assert_plot(case,metadata[0]['figure']);return
 assert not html and answer['requirement_outcomes'][0]['status']=='failed';assert not any(z['tool_name']=='create_chart' for z in state['tool_receipts'])


def _s3_box_axis_assert_plot(case,figure):
 import struct,base64
 def values(v):
  if isinstance(v,list):return v
  c={'i1':'b','i2':'h','i4':'i','i8':'q','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+c*(len(b)//struct.calcsize(c)),b))
 traces=figure['data'];expected=['a','b'] if case=='box_default_control' else ['a']
 assert [t['name'] for t in traces]==expected
 for t in traces:
  assert values(t['y'])==([1,2,10,20] if t['name']=='a' else [100,200,300,400])
  if case=='box_xonly_control':assert list(t['x'])==['X','X','Y','Y']
  else:assert 'x' not in t


_s3_category_scale_E=Path(os.environ.get('DATA_AGENT_S3_CATEGORY_SCALE_EVIDENCE','tmp/s3-chart-category-scale-20261014-r2/evidence-promoted'));_s3_category_scale_E.mkdir(parents=True,exist_ok=True)


_s3_category_scale_E=Path(os.environ.get('DATA_AGENT_S3_CATEGORY_SCALE_EVIDENCE','tmp/s3-chart-category-scale-20261014-r2/evidence-promoted'));_s3_category_scale_E.mkdir(parents=True,exist_ok=True)


def _s3_category_scale_save(n,d):(_s3_category_scale_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


_s3_category_scale_CASES=['category_index'];_s3_category_scale_CONTROLS=['numeric_index_control','time_index_control','category_raw_control']


_s3_category_scale_CASES=['category_index'];_s3_category_scale_CONTROLS=['numeric_index_control','time_index_control','category_raw_control']


def _s3_category_scale_frame(case):
 axis=[2,1,2,3] if case=='numeric_index_control' else ['2026-10-02','2026-10-01','2026-10-02','2026-10-03'] if case=='time_index_control' else ['B','A','B','C']
 return pd.DataFrame({'axis':axis,'amount':[10,20,20,30]})


def _s3_category_scale_args(case,name):return {'chart_type':'line','data':name,'title':'Approved category order and scale','x_col':'axis','y_col':'amount','aggregation':'sum','scale_mode':'raw' if case=='category_raw_control' else 'index100'}


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_s3_category_scale_CASES+_s3_category_scale_CONTROLS)
def test_cross_interface_s3_chart_category_scale(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_s3_category_scale_frame(case);loop.context.workspace.add('remaining_input',f);captured=[];p=_s3_category_scale_args(case,'remaining_input')
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _s3_category_scale_save(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 assert len(captured)==1;_s3_category_scale_assert_plot(case,captured[0]['figure'])


@pytest.mark.parametrize('case',_s3_category_scale_CASES+_s3_category_scale_CONTROLS)
def test_normal_user_chain_s3_chart_category_scale(engine,monkeypatch,case):
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
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按明确选列、分组及聚合绘图，不得忽略参数，也不得把非法计数当作有效计数。';p=_s3_category_scale_args(case,'experiment');raw=_s3_category_scale_frame(case).to_csv(index=False).encode()
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
  if md['status']=='exported':(_s3_category_scale_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _s3_category_scale_save('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered';_s3_category_scale_assert_plot(case,metadata[0]['figure'])


def _s3_category_scale_assert_plot(case,figure):
 import struct,base64
 def values(v):
  if isinstance(v,list):return v
  c={'i1':'b','i2':'h','i4':'i','i8':'q','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+c*(len(b)//struct.calcsize(c)),b))
 t=figure['data'][0];x=list(t['x']);y=values(t['y'])
 if case in {'category_index','category_raw_control'}:
  assert x==['B','A','C'];expected=[30,20,30] if case=='category_raw_control' else [100,200/3,100]
 else:
  assert x==([1,2,3] if case=='numeric_index_control' else ['2026-10-01T00:00:00','2026-10-02T00:00:00','2026-10-03T00:00:00']);expected=[100,150,150]
 assert all(abs(a-b)<1e-10 for a,b in zip(y,expected)) and len(y)==3


_s3_unbound_group_E=Path(os.environ.get('DATA_AGENT_S3_UNBOUND_GROUP_EVIDENCE','tmp/s3-chart-unbound-group-20261014-r2/evidence-promoted'));_s3_unbound_group_E.mkdir(parents=True,exist_ok=True)


_s3_unbound_group_E=Path(os.environ.get('DATA_AGENT_S3_UNBOUND_GROUP_EVIDENCE','tmp/s3-chart-unbound-group-20261014-r2/evidence-promoted'));_s3_unbound_group_E.mkdir(parents=True,exist_ok=True)


def _s3_unbound_group_save(n,d):(_s3_unbound_group_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


_s3_unbound_group_CASES=['line_y_aggregation','bar_y_aggregation','line_y_color','bar_y_color'];_s3_unbound_group_CONTROLS=[c+'_control' for c in _s3_unbound_group_CASES]+['line_labels_control','bar_labels_control']


_s3_unbound_group_CASES=['line_y_aggregation','bar_y_aggregation','line_y_color','bar_y_color'];_s3_unbound_group_CONTROLS=[c+'_control' for c in _s3_unbound_group_CASES]+['line_labels_control','bar_labels_control']


def _s3_unbound_group_frame(case):return pd.DataFrame({'segment':['X','Y','X','Y'],'amount':[1,2,10,20],'cohort':['C1','C2','C1','C2']})


def _s3_unbound_group_args(case,name):
 base=case.removesuffix('_control');p={'chart_type':base.split('_')[0],'data':name,'title':'Explicit group request without axis','y_col':'amount'}
 if base.endswith('aggregation'):p['aggregation']='sum'
 else:p['color_col']='cohort'
 if '_labels_' in case:
  p['label_columns']='segment,cohort';p['aggregation']='sum';p.pop('color_col',None)
 elif case.endswith('_control'):
  p['x_col']='segment';p['aggregation']='sum'
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_s3_unbound_group_CASES+_s3_unbound_group_CONTROLS)
def test_cross_interface_s3_chart_unbound_group(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_s3_unbound_group_frame(case);loop.context.workspace.add('remaining_input',f);captured=[];p=_s3_unbound_group_args(case,'remaining_input')
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _s3_unbound_group_save(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 if case.endswith('_control'):
  assert len(captured)==1;_s3_unbound_group_assert_plot(case,captured[0]['figure']);return
 assert not captured;error=json.loads(str(r));assert error['error_type']=='chart_validation' and error['error_code']=='missing_chart_group_axis'


@pytest.mark.parametrize('case', ['bar_y_aggregation', 'line_y_color', 'line_y_aggregation_control', 'bar_y_aggregation_control', 'line_y_color_control', 'bar_y_color_control', 'line_labels_control', 'bar_labels_control'])
def test_normal_user_chain_s3_chart_unbound_group(engine,monkeypatch,case):
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
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按明确选列、分组及聚合绘图，不得忽略参数，也不得把非法计数当作有效计数。';p=_s3_unbound_group_args(case,'experiment');raw=_s3_unbound_group_frame(case).to_csv(index=False).encode()
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
  if md['status']=='exported':(_s3_unbound_group_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _s3_unbound_group_save('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case.endswith('_control'):
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events;_s3_unbound_group_assert_plot(case,metadata[0]['figure']);return
 assert not html and answer['requirement_outcomes'][0]['status']=='failed';assert not any(z['tool_name']=='create_chart' for z in state['tool_receipts'])


def _s3_unbound_group_assert_plot(case,figure):
 import struct,base64
 def values(v):
  if isinstance(v,list):return v
  c={'i1':'b','i2':'h','i4':'i','i8':'q','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+c*(len(b)//struct.calcsize(c)),b))
 if '_labels_' in case:
  assert [json.loads(x) for x in figure['data'][0]['x']]==[['X','C1'],['Y','C2']];assert values(figure['data'][0]['y'])==[11,22];return
 if '_color' in case:
  assert [t['name'] for t in figure['data']]==['C1','C2'];assert [list(t['x']) for t in figure['data']]==[['X'],['Y']];assert [values(t['y']) for t in figure['data']]==[[11],[22]]
 else:assert list(figure['data'][0]['x'])==['X','Y'] and values(figure['data'][0]['y'])==[11,22]


_s3_numeric_axis_E=Path(os.environ.get('DATA_AGENT_S3_NUMERIC_AXIS_EVIDENCE','tmp/s3-chart-numeric-axis-scope-20261014-r2/evidence-promoted'));_s3_numeric_axis_E.mkdir(parents=True,exist_ok=True)


_s3_numeric_axis_E=Path(os.environ.get('DATA_AGENT_S3_NUMERIC_AXIS_EVIDENCE','tmp/s3-chart-numeric-axis-scope-20261014-r2/evidence-promoted'));_s3_numeric_axis_E.mkdir(parents=True,exist_ok=True)


def _s3_numeric_axis_save(n,d):(_s3_numeric_axis_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


_s3_numeric_axis_CASES=['numeric_axis_raw','numeric_axis_sum','numeric_axis_negative_raw','numeric_axis_negative_sum'];_s3_numeric_axis_CONTROLS=[c+'_control' for c in _s3_numeric_axis_CASES]+['numeric_axis_missing_raw_control','numeric_axis_missing_sum_control']


_s3_numeric_axis_CASES=['numeric_axis_raw','numeric_axis_sum','numeric_axis_negative_raw','numeric_axis_negative_sum'];_s3_numeric_axis_CONTROLS=[c+'_control' for c in _s3_numeric_axis_CASES]+['numeric_axis_missing_raw_control','numeric_axis_missing_sum_control']


def _s3_numeric_axis_frame(case):
 middle=float('nan') if '_missing_' in case else 2. if case.endswith('_control') else -float('inf') if '_negative_' in case else float('inf')
 return pd.DataFrame({'axis':[1.,middle,3.],'amount':[10,20,30]})


def _s3_numeric_axis_args(case,name):return {'chart_type':'line','data':name,'title':'Numeric axis effective range','x_col':'axis','y_col':'amount','aggregation':'sum' if '_sum' in case else ''}


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_s3_numeric_axis_CASES+_s3_numeric_axis_CONTROLS)
def test_cross_interface_s3_chart_numeric_axis(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_s3_numeric_axis_frame(case);loop.context.workspace.add('remaining_input',f);captured=[];p=_s3_numeric_axis_args(case,'remaining_input')
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _s3_numeric_axis_save(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 if case.endswith('_control'):
  assert len(captured)==1;_s3_numeric_axis_assert_plot(case,captured[0]['figure']);return
 assert not captured;error=json.loads(str(r));assert error['error_type']=='chart_validation' and error['error_code']=='invalid_numeric_line_axis'


@pytest.mark.parametrize("case", ['numeric_axis_raw', 'numeric_axis_negative_sum', 'numeric_axis_raw_control', 'numeric_axis_sum_control', 'numeric_axis_missing_raw_control', 'numeric_axis_missing_sum_control'])
def test_normal_user_chain_s3_chart_numeric_axis(engine,monkeypatch,case):
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
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按明确选列、分组及聚合绘图，不得忽略参数，也不得把非法计数当作有效计数。';p=_s3_numeric_axis_args(case,'experiment');raw=_s3_numeric_axis_frame(case).to_csv(index=False).encode()
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
  if md['status']=='exported':(_s3_numeric_axis_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _s3_numeric_axis_save('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case.endswith('_control'):
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events;_s3_numeric_axis_assert_plot(case,metadata[0]['figure']);return
 assert not html and answer['requirement_outcomes'][0]['status']=='failed';assert not any(z['tool_name']=='create_chart' for z in state['tool_receipts'])


def _s3_numeric_axis_assert_plot(case,figure):
 import struct,base64
 def values(v):
  if isinstance(v,list):return v
  c={'i1':'b','i2':'h','i4':'i','i8':'q','f8':'d'}[v['dtype']];b=base64.b64decode(v['bdata']);return list(struct.unpack('<'+c*(len(b)//struct.calcsize(c)),b))
 t=figure['data'][0]
 if '_missing_' in case:
  import math
  x=[None if a is None or isinstance(a,float) and not math.isfinite(a) else a for a in t['x']];assert x==([1.,3.,None] if '_sum' in case else [1.,None,3.]);assert values(t['y'])==([10,30,20] if '_sum' in case else [10,20,30]);return
 assert list(t['x'])==[1.,2.,3.] and values(t['y'])==[10,20,30]


_s3_pie_aggregation_E=Path(os.environ.get('DATA_AGENT_S3_PIE_AGGREGATION_EVIDENCE','tmp/s3-chart-pie-aggregation-20261014-r2/evidence-promoted'));_s3_pie_aggregation_E.mkdir(parents=True,exist_ok=True)


_s3_pie_aggregation_E=Path(os.environ.get('DATA_AGENT_S3_PIE_AGGREGATION_EVIDENCE','tmp/s3-chart-pie-aggregation-20261014-r2/evidence-promoted'));_s3_pie_aggregation_E.mkdir(parents=True,exist_ok=True)


def _s3_pie_aggregation_save(n,d):(_s3_pie_aggregation_E/n).write_bytes(json.dumps(d,ensure_ascii=False,indent=2,default=str).encode())


_s3_pie_aggregation_CASES=['pie_sum','pie_mean','pie_median'];_s3_pie_aggregation_CONTROLS=[c+'_control' for c in _s3_pie_aggregation_CASES]+['pie_frequency_control','pie_count_control','pie_labels_count_control','pie_metric_count_control']


_s3_pie_aggregation_CASES=['pie_sum','pie_mean','pie_median'];_s3_pie_aggregation_CONTROLS=[c+'_control' for c in _s3_pie_aggregation_CASES]+['pie_frequency_control','pie_count_control','pie_labels_count_control','pie_metric_count_control']


def _s3_pie_aggregation_frame(case):
 f=pd.DataFrame({'segment':['X','Y','X','Y'],'amount':[1,2,10,20]})
 if case=='pie_labels_count_control':f['cohort']=['C1','C2','C1','C2']
 if case=='pie_metric_count_control':f.loc[1,'amount']=float('nan')
 return f


def _s3_pie_aggregation_args(case,name):
 p={'chart_type':'pie','data':name,'title':'Explicit aggregate without measure','x_col':'segment','aggregation':case.removesuffix('_control').split('_')[-1]}
 if case=='pie_frequency_control':p['aggregation']=''
 elif case in {'pie_count_control','pie_labels_count_control'}:
  p['aggregation']='count'
  if case=='pie_labels_count_control':p.pop('x_col');p['label_columns']='segment,cohort'
 elif case=='pie_metric_count_control':p.update(aggregation='count',y_col='amount')
 elif case.endswith('_control'):p['y_col']='amount'
 return p


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',_s3_pie_aggregation_CASES+_s3_pie_aggregation_CONTROLS)
def test_cross_interface_s3_chart_pie_aggregation(engine,monkeypatch,route,case):
 from data_agent.tools import visualization as v
 loop,_=engine;f=_s3_pie_aggregation_frame(case);loop.context.workspace.add('remaining_input',f);captured=[];p=_s3_pie_aggregation_args(case,'remaining_input')
 def stop(fig,title,metadata):captured.append({'figure':fig.to_plotly_json(),'metadata':metadata});return 'intercepted before write'
 monkeypatch.setattr(v,'_save_chart',stop);r=v.create_chart(**p) if route=='direct' else registry.execute('create_chart',p).summary
 _s3_pie_aggregation_save(case+'_'+route+'.json',{'input':p,'rows':f.to_dict('records'),'captured':captured,'result':str(r),'provider_calls':0,'actual_chart_writes':0})
 if case.endswith('_control'):
  assert len(captured)==1;_s3_pie_aggregation_assert_plot(case,captured[0]['figure']);return
 assert not captured;error=json.loads(str(r));assert error['error_type']=='chart_validation' and error['error_code']=='missing_explicit_chart_measure'


@pytest.mark.parametrize('case', ['pie_sum', 'pie_sum_control', 'pie_mean_control', 'pie_frequency_control', 'pie_count_control', 'pie_labels_count_control', 'pie_metric_count_control'])
def test_normal_user_chain_s3_chart_pie_aggregation(engine,monkeypatch,case):
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
 monkeypatch.setattr(go.Figure,'to_image',no_png);content='加载上传文件，将其命名为experiment；严格按明确选列、分组及聚合绘图，不得忽略参数，也不得把非法计数当作有效计数。';p=_s3_pie_aggregation_args(case,'experiment');raw=_s3_pie_aggregation_frame(case).to_csv(index=False).encode()
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
  if md['status']=='exported':(_s3_pie_aggregation_E/('normal_'+case+'.md')).write_bytes((root/'reports'/md['artifact_path'].split('/')[-1]).read_bytes())
 _s3_pie_aggregation_save('normal_'+case+'.json',{'case':case,'input':p,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'metadata':metadata,'html':[str(z) for z in html],'state':state,'session_dir':str(root),'md':md,'provider_calls':0,'visual':'unassessed'})
 assert len(ends)==1 and ends[0]['status']=='completed',events
 if case.endswith('_control'):
  assert len(html)==1 and answer['requirement_outcomes'][0]['status']=='answered',events;_s3_pie_aggregation_assert_plot(case,metadata[0]['figure']);return
 assert not html and answer['requirement_outcomes'][0]['status']=='failed';assert not any(z['tool_name']=='create_chart' for z in state['tool_receipts'])


def _s3_pie_aggregation_assert_plot(case,figure):
 t=figure['data'][0]
 if case=='pie_labels_count_control':assert [json.loads(x) for x in t['labels']]==[['X','C1'],['Y','C2']]
 else:assert list(t['labels'])==['X','Y']
 expected=[2,1] if case=='pie_metric_count_control' else [2,2] if case in {'pie_frequency_control','pie_count_control','pie_labels_count_control'} else [11.,22.] if '_sum' in case else [5.5,11.]
 assert t['values']==expected


def _s3_business_evidence(cfg):
 root=Path(os.environ.get('DATA_AGENT_S3_BUSINESS_TABLE_EVIDENCE',str(cfg.sessions_resolved/'table_evidence')))
 root.mkdir(parents=True,exist_ok=True)
 return root


def _s3_business_frame(case):
 f=pd.DataFrame({'group':['A','B','C','D'],'amount':[1,2,3,999]})
 if case=='comparison_fields':f=pd.concat([f.assign(day='2026-09-01'),f.assign(amount=lambda x:x.amount*2,day='2026-09-03')],ignore_index=True)
 return f


def _s3_business_parameters(case):return {'name':'experiment','sort_by':'amount','n':4,'ascending':False,'columns':'group,amount'} if case=='fourth_group' else {'name':'experiment','date_col':'day','metrics':'amount','dimensions':'group','period_a':'2026-09-01~2026-09-02','period_b':'2026-09-03~2026-09-06'}


def _s3_business_assert_actual(case,data):
 if case=='fourth_group':assert data['records']==[{'group':'D','amount':999},{'group':'C','amount':3},{'group':'B','amount':2},{'group':'A','amount':1}]
 else:
  rows={r['dimension']:r['amount'] for r in data['comparisons']};assert set(rows)==set('ABCD');assert rows['D']['exact_aggregates']=={'a':999.,'b':1998.,'diff':999.};assert rows['D']['change_pct']==100.;assert data['period_a']['day_count']==2 and data['period_b']['day_count']==4


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['fourth_group','comparison_fields'])
def test_s3_business_tables_cross_interfaces(engine,case,route):
 from data_agent.tools.eda import top_n,compare_periods
 loop,cfg=engine;E=_s3_business_evidence(cfg);f=_s3_business_frame(case);loop.context.workspace.add('experiment',f);name='top_n' if case=='fourth_group' else 'compare_periods';args=_s3_business_parameters(case);result=registry.execute(name,args) if route=='registry' else (top_n(**args) if case=='fourth_group' else compare_periods(**args));data=result.data if isinstance(result,ToolResult) else json.loads(result)
 with (E/(case+'_'+route+'.json')).open('x',encoding='utf-8') as out:json.dump({'case':case,'input':args,'rows':f.to_dict('records'),'result':data,'provider_calls':0},out,ensure_ascii=False,indent=2,default=str)
 _s3_business_assert_actual(case,data)


@pytest.mark.parametrize('case',['fourth_group','comparison_fields'])
def test_s3_business_tables_normal_agentloop(engine,case,monkeypatch):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 _,cfg=engine;E=_s3_business_evidence(cfg);monkeypatch.setattr(cfg,'mcp_enabled',False);tool='top_n' if case=='fourth_group' else 'compare_periods';args=_s3_business_parameters(case)
 if case=='fourth_group':
  content='分析上传数据，将其命名为experiment；完整交付四个渠道的金额对照，保留渠道与金额的对应关系，并按金额降序保留原值。';params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':4,'topn_columns':['group','amount']};specs=[{'kind':'table','scope':{'datasets':['experiment'],'metrics':['group','amount'],'parameters':dict(params,topn_output=out)}} for out in ['records','observation']]
 else:
  content='分析上传数据，将其命名为experiment；比较2026-09-01至2026-09-02与2026-09-03至2026-09-06的各渠道amount合计、差值和日均，完整保留各期日期、分组、分母和观测范围，不推断因果。';params={'comparison_date_col':'day','comparison_dimensions':['group'],'comparison_formulas':{},'period_a':args['period_a'],'period_b':args['period_b']};specs=[{'kind':'table','scope':{'datasets':['experiment'],'metrics':['amount'],'parameters':dict(params,comparison_output=out)}} for out in ['comparison','observation']]
 model=_NativeProductModel(content,'experiment',tool,args,specs);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='original_group_'+case;raw=_s3_business_frame(case).to_csv(index=False).encode()
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;response=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']);state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));receipt=next(z for z in state['tool_receipts'] if z['tool_name']==tool);ends=[v for k,v in events if k=='turn_end']
 with use_agent_context(manager.get(sid).context):md=export_assistant_reply(sid,answer['body'],'md')
 mdpath=root/'reports'/md['artifact_path'].split('/')[-1]
 with (E/('normal_'+case+'.md')).open('xb') as out:out.write(mdpath.read_bytes())
 with (E/('normal_'+case+'.json')).open('x',encoding='utf-8') as out:json.dump({'case':case,'input':args,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'state':state,'receipt':receipt,'session_dir':str(root),'md':md,'provider_calls':0},out,ensure_ascii=False,indent=2,default=str)
 assert len(ends)==1 and ends[0]['status']=='completed';assert answer['body']==msg['content']==ends[0]['reply_content'];assert answer['requirement_outcomes'][0]['status']=='answered'
 claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in answer['source_snapshot']['requirements'][0]['claim_ids']];values={c['basis_refs'][0]['result_path'][0]:c['value'] for c in claims}
 assert '\n| ' in answer['body'] and '\n| ---' in answer['body'],answer['body']
 assert 'exact_aggregates' not in answer['body'] and 'effective_rows' not in answer['body'],answer['body']
 if case=='fourth_group':assert values['records'][0]=={'group':'D','amount':999} and len(values['records'])==4
 else:
  rows={r['dimension']:r['amount'] for r in values['comparisons']};assert rows['D']['exact_aggregates']=={'a':999.,'b':1998.,'diff':999.};assert all('2026-09-01' in c['scope']['time_scope'] and '2026-09-06' in c['scope']['time_scope'] for c in claims)


@pytest.mark.parametrize("tool,case",[("compare_periods",c) for c in ["regular","missing","nonfinite","unknown","zero","invalid_date","new_group","ratio","ratio_missing"]]+[("top_n",c) for c in ["descending","ascending","columns","oversized","save","operation_only"]])
def test_s3_business_tables_existing_real_app_boundaries(engine,tool,case,monkeypatch):
    import data_agent.tools.report as report
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    _,cfg=engine;original=report.export_assistant_reply;captured=[];E=_s3_business_evidence(cfg)
    def export(sid,body,fmt,*args,**kwargs):
        result=original(sid,body,fmt,*args,**kwargs);root=cfg.sessions_resolved/sid;saved=load_session(sid);answer=read_answer(sid,saved["messages"][-1]["answer_ref"]);state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));md=root/'reports'/result['artifact_path'].split('/')[-1]
        with (E/(tool+'_'+case+'.json')).open('x',encoding='utf-8') as f:json.dump({'tool':tool,'case':case,'body':body,'answer':answer,'state':state,'saved':saved,'session_dir':str(root),'md':result,'provider_calls':0},f,ensure_ascii=False,indent=2,default=str)
        with (E/(tool+'_'+case+'.md')).open('xb') as f:f.write(md.read_bytes())
        assert answer['body']==body and body in md.read_text(encoding='utf-8');captured.append(answer)
        return result
    monkeypatch.setattr(report,'export_assistant_reply',export)
    if tool=='compare_periods':_test_normal_app_period_comparison_real_sums_unknown_scope_sse_save_refresh_export(engine,case)
    else:_test_normal_app_topn_original_precision_exact_range_and_real_effect_sse_save_refresh_export(engine,case,monkeypatch)
    assert len(captured)==1;a=captured[0]
    if case=='operation_only':assert '操作完成' in a['body']
    else:
        assert '\n| ' in a['body'] and '\n| ---' in a['body']
        assert 'exact_aggregates' not in a['body'] and 'effective_rows' not in a['body']
    if tool=='top_n' and case in {'descending','save','oversized'}:assert '0.423456789012345' in a['body']
    if tool=='compare_periods' and case in {'unknown','new_group','zero','ratio_missing'}:assert '未知' in a['body']
    if tool=='compare_periods' and case.startswith('ratio'):assert '合计 ÷' in a['body']


def _s3_html_evidence(cfg):
 root=Path(os.environ.get('DATA_AGENT_S3_HTML_TEXT_EVIDENCE',str(cfg.sessions_resolved/'html_text_evidence')))
 root.mkdir(parents=True,exist_ok=True)
 return root


def _s3_html_frame(case):
 f=pd.DataFrame({'group':['A','B','C','D onerror=ops'],'amount':[1,2,3,999]})
 if case=='comparison_fields':f=pd.concat([f.assign(day='2026-09-01'),f.assign(amount=lambda x:x.amount*2,day='2026-09-03')],ignore_index=True)
 return f


def _s3_html_parameters(case):return {'name':'experiment','sort_by':'amount','n':4,'ascending':False,'columns':'group,amount'} if case=='fourth_group' else {'name':'experiment','date_col':'day','metrics':'amount','dimensions':'group','period_a':'2026-09-01~2026-09-02','period_b':'2026-09-03~2026-09-06'}


def _s3_html_assert_actual(case,data):
 if case=='fourth_group':assert data['records']==[{'group':'D onerror=ops','amount':999},{'group':'C','amount':3},{'group':'B','amount':2},{'group':'A','amount':1}]
 else:
  rows={r['dimension']:r['amount'] for r in data['comparisons']};assert set(rows)=={'A','B','C','D onerror=ops'};assert rows['D onerror=ops']['exact_aggregates']=={'a':999.,'b':1998.,'diff':999.};assert rows['D onerror=ops']['change_pct']==100.;assert data['period_a']['day_count']==2 and data['period_b']['day_count']==4


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('case',['fourth_group','comparison_fields'])
def test_s3_html_literal_cross_interfaces(engine,case,route):
 from data_agent.tools.eda import top_n,compare_periods
 loop,cfg=engine;E=_s3_html_evidence(cfg);f=_s3_html_frame(case);loop.context.workspace.add('experiment',f);name='top_n' if case=='fourth_group' else 'compare_periods';args=_s3_html_parameters(case);result=registry.execute(name,args) if route=='registry' else (top_n(**args) if case=='fourth_group' else compare_periods(**args));data=result.data if isinstance(result,ToolResult) else json.loads(result)
 with (E/(case+'_'+route+'.json')).open('x',encoding='utf-8') as out:json.dump({'case':case,'input':args,'rows':f.to_dict('records'),'result':data,'provider_calls':0},out,ensure_ascii=False,indent=2,default=str)
 _s3_html_assert_actual(case,data)


@pytest.mark.parametrize('case',['fourth_group','comparison_fields'])
def test_s3_html_literal_normal_agentloop(engine,case,monkeypatch):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 _,cfg=engine;E=_s3_html_evidence(cfg);monkeypatch.setattr(cfg,'mcp_enabled',False);tool='top_n' if case=='fourth_group' else 'compare_periods';args=_s3_html_parameters(case)
 if case=='fourth_group':
  content='分析上传数据，将其命名为experiment；完整交付四个渠道的金额对照，保留渠道与金额的对应关系，并按金额降序保留原值。';params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':4,'topn_columns':['group','amount']};specs=[{'kind':'table','scope':{'datasets':['experiment'],'metrics':['group','amount'],'parameters':dict(params,topn_output=out)}} for out in ['records','observation']]
 else:
  content='分析上传数据，将其命名为experiment；比较2026-09-01至2026-09-02与2026-09-03至2026-09-06的各渠道amount合计、差值和日均，完整保留各期日期、分组、分母和观测范围，不推断因果。';params={'comparison_date_col':'day','comparison_dimensions':['group'],'comparison_formulas':{},'period_a':args['period_a'],'period_b':args['period_b']};specs=[{'kind':'table','scope':{'datasets':['experiment'],'metrics':['amount'],'parameters':dict(params,comparison_output=out)}} for out in ['comparison','observation']]
 model=_NativeProductModel(content,'experiment',tool,args,specs);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='original_group_'+case;raw=_s3_html_frame(case).to_csv(index=False).encode()
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;response=h.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json();api_html=h.get('/api/sessions/'+sid+'/export?format=html').get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']);state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));receipt=next(z for z in state['tool_receipts'] if z['tool_name']==tool);ends=[v for k,v in events if k=='turn_end']
 with use_agent_context(manager.get(sid).context):
  md=export_assistant_reply(sid,answer['body'],'md')
  html_result=export_assistant_reply(sid,answer['body'],'html')
 html_path=root/'reports'/html_result['artifact_path'].split('/')[-1]
 api_path=cfg.sessions_resolved.parent/api_html['artifact_path']
 assert 'D onerror=ops' in api_path.read_text(encoding='utf-8')
 with (E/('normal_'+case+'_api.html')).open('xb') as out:out.write(api_path.read_bytes())
 with (E/('normal_'+case+'.html')).open('xb') as out:out.write(html_path.read_bytes())
 mdpath=root/'reports'/md['artifact_path'].split('/')[-1]
 with (E/('normal_'+case+'.md')).open('xb') as out:out.write(mdpath.read_bytes())
 with (E/('normal_'+case+'.json')).open('x',encoding='utf-8') as out:json.dump({'case':case,'input':args,'raw_hex':raw.hex(),'ticket':ticket,'calls':model.calls,'events':events,'refresh':refresh,'saved':saved,'answer':answer,'state':state,'receipt':receipt,'session_dir':str(root),'md':md,'html_export':html_result,'html_path':str(html_path),'api_html':api_html,'api_html_path':str(api_path),'provider_calls':0},out,ensure_ascii=False,indent=2,default=str)
 assert len(ends)==1 and ends[0]['status']=='completed';assert answer['body']==msg['content']==ends[0]['reply_content'];assert answer['requirement_outcomes'][0]['status']=='answered'
 claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in answer['source_snapshot']['requirements'][0]['claim_ids']];values={c['basis_refs'][0]['result_path'][0]:c['value'] for c in claims}
 if case=='fourth_group':
  assert 'D onerror=ops' in html_path.read_text(encoding='utf-8'), 'HTML export removed literal group text while MD and canonical claims retain it'
 if case=='fourth_group':assert values['records'][0]=={'group':'D onerror=ops','amount':999} and len(values['records'])==4
 else:
  rows={r['dimension']:r['amount'] for r in values['comparisons']};assert rows['D onerror=ops']['exact_aggregates']=={'a':999.,'b':1998.,'diff':999.};assert all('2026-09-01' in c['scope']['time_scope'] and '2026-09-06' in c['scope']['time_scope'] for c in claims)

