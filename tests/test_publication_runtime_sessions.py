from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: sessions. Shared fixtures have one owner."""
from copy import deepcopy
from data_agent.agent import compact
from data_agent.agent.publication.contracts import encode
from pathlib import Path
from tests.test_trusted_publication_semantics import execute
import hashlib
import io
import json
import os
import pandas as pd
import pytest
from tests.support.publication_runtime import _NativeProductModel, draft, request
from tests.test_publication_runtime_records import _askq_events
from tests.test_trusted_publication_runtime import _s3_distribution_id_save

class _S3OriginalScopeProxy:
 active=None
 def chat(self,*a,**kw):return self.active.chat(*a,**kw)
 def stream_chat_structured(self,*a,**kw):return self.active.stream_chat_structured(*a,**kw)


class _S3OriginalScopeFollowup:
 def __init__(self,text,answer):self.text=text;self.answer=answer
 def chat(self,messages,system='',**kw):
  from data_agent.llm.client import Response
  from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
  if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return Response(text=json.dumps({'intent_type':'result_followup','requested_outputs':[{'kind':'presentation','exact_span':self.text,'source_answer_id':self.answer}]},ensure_ascii=False))
  v=ScriptedClient._current_host_snapshot(messages,system);return Response(text=json.dumps({'schema':'answer_bindings.v2','snapshot_digest':v['snapshot_digest'],'sections':[{'requirement_ids':[r['id']],'parts':[{'kind':'claim','ref':c} for c in r['claim_ids']]} for r in v['requirements'] if not r['withdrawn']]},ensure_ascii=False))
 def stream_chat_structured(self,*a,**kw):
  from data_agent.llm.client import StreamTextDelta,StreamComplete
  r=self.chat(*a,**kw);yield StreamTextDelta(r.text);yield StreamComplete(r)


def test_s3_original_e02_receipt_scope_preserved_across_five_plans_and_exact_export(engine,monkeypatch):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer,collect_products
 from data_agent.agent.publication.facts import load_receipt_result
 from data_agent.agent.context import use_agent_context
 from data_agent.tools.report import export_assistant_reply
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False);proxy=_S3OriginalScopeProxy();manager=AgentManager(client_factory=lambda **kw:proxy,auxiliary_client_factory=lambda:proxy);app=create_app();app.config['agent_manager']=manager;sid='original_receipt_scope';turns=[];first=None
 with app.test_client() as h:
  for i in range(1,6):
   name='q'+str(i);text='分析上传数据，将其命名为'+name+'；按amount降序交付全部四组记录，保留原值。';args={'name':name,'sort_by':'amount','ascending':False,'n':4,'columns':'group,amount'};params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':4,'topn_columns':['group','amount'],'topn_output':'records'};model=_NativeProductModel(text,name,'top_n',args,[{'kind':'table','scope':{'datasets':[name],'metrics':['group','amount'],'parameters':params}}]);raw=('group,amount\nA,1\nB,2\nC,3\nD,'+str(999*i)+'\n').encode();ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),name+'.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;proxy.active=model;resp=h.post('/api/chat',json={'session_id':sid,'message':text,'uploads':[ticket]});events=[(x.split('\n',1)[0][7:],json.loads(x.split('\ndata: ',1)[1])) for x in resp.get_data(as_text=True).split('\n\n') if x.startswith('event:')];msg=load_session(sid)['messages'][-1];answer=read_answer(sid,msg['answer_ref']);turns.append({'name':name,'raw_hex':raw.hex(),'ticket':ticket,'events':events,'answer':answer,'calls':model.calls})
   assert len([d for k,d in events if k=='turn_end'])==1 and answer['requirement_outcomes'][-1]['status']=='answered',answer
   if i==1:first=answer['answer_id']
  text='请只重新交付原答案'+first+'的q1四组排行，不重新计算，也不引用其他来源。';proxy.active=_S3OriginalScopeFollowup(text,first);resp=h.post('/api/chat',json={'session_id':sid,'message':text});events=[(x.split('\n',1)[0][7:],json.loads(x.split('\ndata: ',1)[1])) for x in resp.get_data(as_text=True).split('\n\n') if x.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 root=cfg.sessions_resolved/sid;saved=load_session(sid);last=read_answer(sid,saved['messages'][-1]['answer_ref']);state=json.loads((root/'analysis_state.json').read_text(encoding='utf-8'));receipts=state['tool_receipts'];first_receipt=receipts[0];ctx=manager.get(sid).context
 with use_agent_context(ctx):
  direct=load_receipt_result(session_id=sid,receipt_id=first_receipt['id']);filtered=collect_products(ctx.analysis_state,sid,receipt_ids={first_receipt['id']});md=export_assistant_reply(sid,last['body'],'md')
 with app.test_client() as h:
  api_content=h.post('/api/sessions/'+sid+'/export-reply',json={'content':last['body'],'format':'md'});api_id=h.post('/api/sessions/'+sid+'/export-reply',json={'reply_id':saved['messages'][-1]['reply_id'],'format':'md'})
 import os
 O=Path(os.environ.get('DATA_AGENT_S3_ORIGINAL_SCOPE_EVIDENCE',str(cfg.sessions_resolved/'scope_evidence')));O.mkdir(parents=True,exist_ok=True)
 with (O/'before-export-assert.json').open('x',encoding='utf-8') as f:json.dump({'answer':last,'state':state,'direct':md,'api_content':{'status':api_content.status_code,'body':api_content.get_json()},'api_id':{'status':api_id.status_code,'body':api_id.get_json()},'session_dir':str(root),'turns':turns,'filtered_claims':filtered[0],'first_receipt':first_receipt,'provider_calls':0},f,ensure_ascii=False,indent=2,default=str)
 assert 'artifact_path' in md and api_content.status_code==200, 'exact accepted body rejected by direct and API content export'
 mdpath=root/'reports'/md['artifact_path'].split('/')[-1]
 with (O/'actual.md').open('xb') as f:f.write(mdpath.read_bytes())
 with (O/'actual.json').open('x',encoding='utf-8') as f:json.dump({'turns':turns,'followup':{'text':text,'events':events,'refresh':refresh,'answer':last},'state':state,'first_receipt':first_receipt,'direct_result':direct[2],'filtered_claims':filtered[0],'session_dir':str(root),'md':md,'provider_calls':0},f,ensure_ascii=False,indent=2,default=str)
 assert len({r['plan_id'] for r in receipts if r.get('plan_id')})==5
 assert all(r['arguments'].get('name')!='q1' for r in receipts[-4:])
 assert all(c['basis_refs'][0]['receipt_id']==first_receipt['id'] for c in filtered[0]) and filtered[0]
 admitted={x['ref'] for x in last['render_trace'] if x['kind']=='claim' and x['disposition']=='accepted'};claims=[c for c in last['source_snapshot']['claims'] if c['id'] in admitted];assert claims and all(c['scope']['dataset']=='q1' for c in claims)
 assert '| D | 999 |' in last['body'] and '1998' not in last['body'] and all(c['value']!=4995 for c in claims)
 assert last['requirement_outcomes'][-1]['status']=='partial' and 'interpretation' in last['requirement_outcomes'][-1]['reason']
 assert last['body'] in mdpath.read_text(encoding='utf-8')
 idpath=cfg.sessions_resolved.parent/api_id.get_json()['artifact_path']
 assert last['body'] in idpath.read_text(encoding='utf-8')


def _s3_budget_evidence(cfg):
 p=Path(os.environ.get('DATA_AGENT_S3_ORIGINAL_BUDGET_EVIDENCE',str(cfg.sessions_resolved/'budget_evidence')));p.mkdir(parents=True,exist_ok=True);return p


def _s3_budget_output(cfg,name,value):
 with (_s3_budget_evidence(cfg)/(name+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,default=str)


class _S3OriginalBudgetModel(_NativeProductModel):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.requests=[]
 def chat(self,messages,system='',tools=None,**kw):
  from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
  if system!='你是一个JSON输出器，只返回JSON，不要其他内容。':self.observe(messages,system,tools)
  response=super().chat(messages,system=system,tools=tools,**kw)
  if system=='你是一个JSON输出器，只返回JSON，不要其他内容。' and getattr(self,'explain',False):
   data=json.loads(response.text);data['requested_outputs'][0]['purposes']=['interpretation'];response.text=encode(data)
  return response

 def observe(self,messages,system,tools):
  from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
  from data_agent.llm.request_policy import resolve_request_budget
  from data_agent.config import get_config
  from data_agent.llm.client import _convert_tools
  c=get_config();v=ScriptedClient._current_host_snapshot(messages,system);pol=resolve_request_budget(c.model_id,c,c.max_tokens)
  self.requests.append({'view':v,'tools_closed':tools is None,'budget':pol.estimate([{'role':'system','content':system}]+messages,_convert_tools(tools) if tools else None)})


@pytest.mark.parametrize('mode',['soft','hard'])
def test_s3_original_e05_normal_large(engine,monkeypatch,mode):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 _,cfg=engine
 monkeypatch.setattr(cfg,'mcp_enabled',False);monkeypatch.setattr(cfg,'model_context_tokens',1000000);monkeypatch.setattr(cfg,'model_max_input_tokens',884000 if mode=='soft' else 120000);monkeypatch.setattr(cfg,'model_max_output_tokens',16000);monkeypatch.setattr(cfg,'max_tokens',16000)
 name='experiment';n=3000;text='分析上传数据，将其命名为experiment；按amount降序交付全部3000条amount和label记录，保持完整尾部和原值。'+('并解释排行含义。' if mode=='hard' else '不添加解释。')
 args={'name':name,'sort_by':'amount','ascending':False,'n':n,'columns':'amount,label'};params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':n,'topn_columns':['amount','label'],'topn_output':'records'}
 model=_S3OriginalBudgetModel(text,name,'top_n',args,[{'kind':'table','scope':{'datasets':[name],'metrics':['amount','label'],'parameters':params}}]);model.explain=mode=='hard';manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='original_e05_'+mode
 raw=('amount,label\n'+''.join(str(i)+','+'字段'*30+str(i)+'\n' for i in range(n))).encode()
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;resp=h.post('/api/chat',json={'session_id':sid,'message':text,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in resp.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None
 _s3_budget_output(cfg,'normal_'+mode,{'requests':model.requests,'calls':model.calls,'events':events,'saved':saved,'answer':answer,'ticket':ticket,'raw_sha256':hashlib.sha256(raw).hexdigest(),'session_dir':str(cfg.sessions_resolved/sid),'provider_calls':0,'refresh':refresh})
 assert answer is not None,events
 assert model.calls==['describe_dataset','record_analysis_plan','top_n']
 assert all(x['budget']['tokens']<=x['budget']['input_allowance'] for x in model.requests)
 final=model.requests[-1]['view'];assert bool(final.get('model_view_issue'))==(mode=='hard'),[(len(x['view'].get('claims',[])),x['budget']['tokens'],x['view'].get('model_view_issue')) for x in model.requests]
 claims=[c for c in answer['source_snapshot']['claims'] if c['id'] in answer['source_snapshot']['requirements'][0]['claim_ids']];rows=next(c['value'] for c in claims if isinstance(c['value'],list));assert len(rows)==n and rows[0]['amount']==2999 and rows[-1]['amount']==0
 assert '| 2999 |' in answer['body'] and '| 0 |' in answer['body']
 if mode=='soft':assert final['model_view_budget']['expanded_past_soft_target']
 else:assert answer['requirement_outcomes'][0]['status']=='partial' and '预算' in answer['requirement_outcomes'][0]['reason']


@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('fault',['none','hash','tail'])
def test_s3_original_e05_reference_cross_interface(engine,route,fault):
 import pandas as pd
 from data_agent.agent.publication.runtime import snapshot_for_turn,model_publication_context
 from data_agent.tools.registry import registry
 from data_agent.tools.file_ops import read_file
 loop,cfg=engine;loop.context.workspace.add('orders',pd.DataFrame({'amount':range(3000),'label':['row-'+str(i) for i in range(3000)]}));request(loop,'报告全部条数',{'kind':'measurement','scope':{'datasets':['orders'],'quantity':'rows'}});rid,_=execute(loop,'top_n',{'name':'orders','n':3000});host=snapshot_for_turn(loop);before=host.as_dict();v=model_publication_context(host,loop.context.analysis_state,budget=1000000)
 assert v['deferred_details']
 d=next(x for x in v['deferred_details'] if x['receipt_id']==rid);fp=cfg.sessions_resolved/loop.session_id/d['result_ref'];raw=fp.read_bytes();digest=hashlib.sha256(raw).hexdigest();args={'path':d['result_ref'],'expected_sha256':d['file_sha256'],'offset':0}
 if fault=='hash':args['expected_sha256']='0'*64
 if fault=='tail':fp.write_bytes(raw+b'changed')
 pages=[];offsets=[]
 for _ in range(1000):
  r=registry.execute('read_file',args) if route=='registry' else read_file(**args);s=r.summary if hasattr(r,'summary') else r
  if s.startswith('Error:') or (hasattr(r,'data') and isinstance(r.data,dict) and r.data.get('error')):break
  page=json.loads(s);pages.append(page);offsets.append(page['offset'])
  if page['next_offset'] is None:break
  args['offset']=page['next_offset']
 else:raise AssertionError('unbounded read')
 _s3_budget_output(cfg,'cross_'+route+'_'+fault,{'view':v,'host':before,'reference':d,'physical_sha256':digest,'raw_hex':raw.hex(),'pages':pages,'error':s if fault!='none' else None,'provider_calls':0})
 if fault!='none':assert not pages and 'file_changed' in s
 else:
  restored=''.join(p['content'] for p in pages);assert restored==raw.decode().replace('\r\n','\n');detail=json.loads(restored);assert len(detail['records'])==3000 and detail['records'][-1]['amount']==0;assert all(p['sha256']==digest for p in pages)
 assert host.as_dict()==before


class _S3OriginalReferenceModel(_S3OriginalBudgetModel):
 def __init__(self,*a,fault=False,**kw):super().__init__(*a,**kw);self.read_step=0;self.pages=[];self.reference=None;self.fault=fault
 def chat(self,messages,system='',tools=None,**kw):
  from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
  from data_agent.llm.client import Response,ToolCall
  if self.step>=3 and system!='你是一个JSON输出器，只返回JSON，不要其他内容。' and self.read_step<2:
   self.observe(messages,system,tools)
   v=ScriptedClient._current_host_snapshot(messages,system)
   if self.read_step==0:
    self.reference=v['deferred_details'][-1];args={'path':self.reference['result_ref'],'expected_sha256':self.reference['file_sha256'],'offset':0}
   else:
    tool=next(m for m in reversed(messages) if m.get('role')=='tool');page=json.loads(tool['content']);self.pages.append(page);args={'path':self.reference['result_ref'],'expected_sha256':('0'*64 if self.fault else self.reference['file_sha256']),'offset':max(0,page['total_chars']-2000)}
   self.read_step+=1;self.calls.append('read_file');return Response(tool_calls=[ToolCall('e05_read_'+str(self.read_step),'read_file',args)])
  if self.read_step==2 and not getattr(self,'read_done',False):
   self.read_done=True;self.pages.append(json.JSONDecoder().raw_decode(next(m['content'] for m in reversed(messages) if m.get('role')=='tool'))[0])
  return super().chat(messages,system=system,tools=tools,**kw)


@pytest.mark.parametrize('fault',[False,True])
def test_s3_original_e05_normal_deferred_read(engine,monkeypatch,fault):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False);monkeypatch.setattr(cfg,'model_context_tokens',1000000);monkeypatch.setattr(cfg,'model_max_input_tokens',884000);monkeypatch.setattr(cfg,'model_max_output_tokens',16000);monkeypatch.setattr(cfg,'max_tokens',16000)
 text='分析上传数据，将其命名为experiment；只报告按amount降序排行的返回记录条数，n=3000，不展示排行明细，不解释。';params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':3000,'topn_columns':['amount','label'],'topn_output':'n'};model=_S3OriginalReferenceModel(text,'experiment','top_n',{'name':'experiment','n':3000,'sort_by':'amount','ascending':False,'columns':'amount,label'},[{'kind':'measurement','scope':{'datasets':['experiment'],'metrics':['amount','label'],'quantity':'count','parameters':params}}],fault=fault);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='original_e05_reference_'+str(fault);raw=('amount,label\n'+''.join(str(i)+',row-'+str(i)+'\n' for i in range(3000))).encode()
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;resp=h.post('/api/chat',json={'session_id':sid,'message':text,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in resp.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
 saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None
 _s3_budget_output(cfg,'normal_reference_'+str(fault),{'requests':model.requests,'calls':model.calls,'pages':model.pages,'reference':model.reference,'events':events,'saved':saved,'answer':answer,'ticket':ticket,'raw_sha256':hashlib.sha256(raw).hexdigest(),'session_dir':str(cfg.sessions_resolved/sid),'provider_calls':0})
 assert answer is not None,events
 assert model.calls==['describe_dataset','record_analysis_plan','top_n','read_file','read_file'] and len(model.pages)==2,events
 assert '3000' in answer['body'] and 'row-0' not in answer['body']
 if fault:assert 'file_changed' in encode(model.pages[-1])
 else:assert 'row-0' in model.pages[-1]['content'] and model.pages[-1]['sha256']==model.reference['file_sha256']


@pytest.mark.parametrize('change',['new_receipt','tamper','missing'])
def test_s3_original_e09_cached_publication_refreshes_exact_evidence(engine,change):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
 from data_agent.session.history import load_canonical_history
 loop,cfg=engine;request(loop,'报告当前真实行数',{'kind':'measurement','scope':{'datasets':['orders'],'quantity':'rows'}});rid,_=execute(loop,'describe_dataset',{'name':'orders'});first=snapshot_for_turn(loop);before=first.as_dict();body,error=publish(loop,draft(first));assert error is None;old_service=loop._publication_service
 receipt=next(r for r in loop.context.analysis_state.tool_receipts if r['id']==rid);path=cfg.sessions_resolved/loop.session_id/receipt['detail_ref']['path'];physical=path.read_bytes()
 if change=='new_receipt':execute(loop,'describe_dataset',{'name':'orders'})
 elif change=='tamper':path.write_bytes(physical+b'changed')
 else:path.unlink()
 second=snapshot_for_turn(loop);assert second.digest!=first.digest and first.as_dict()==before
 rejected,reason=publish(loop,draft(first));assert rejected is None and reason
 second=snapshot_for_turn(loop)  # Format-recovery history is itself canonical input.
 body,error=publish(loop,draft(second));assert error is None;answer=loop._accepted_answer;assert loop._publication_service is not old_service
 assert answer['source_snapshot']==second.as_dict() and answer['snapshot_digest']==second.digest
 assert commit(loop,{'role':'assistant'},body) is None
 saved=load_canonical_history(loop.session_id)
 _s3_budget_output(cfg,'cache_'+change,{'before':before,'first_digest':first.digest,'after':second.as_dict(),'answer':answer,'saved':saved.messages,'old_draft_rejection':reason,'source_path':str(path),'source_preimage_hex':physical.hex(),'provider_calls':0})
 if change=='new_receipt':assert answer['requirement_outcomes'][0]['status']=='answered' and len(second.as_dict()['claims'])>len(before['claims'])
 else:assert not second.as_dict()['claims'] and answer['requirement_outcomes'][0]['status'] in {'not_computed','evidence_insufficient'} and '已完成' not in body


@pytest.mark.parametrize('change',['tamper','missing'])
def test_s3_original_e09_normal_app_late_evidence_change_cannot_commit_old_package(engine,monkeypatch,change):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.agent.publication import runtime
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False)
 text='分析上传数据，将其命名为experiment；按amount降序交付全部四组原值。';params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':4,'topn_columns':['group','amount'],'topn_output':'records'};model=_S3OriginalBudgetModel(text,'experiment','top_n',{'name':'experiment','n':4,'sort_by':'amount','ascending':False,'columns':'group,amount'},[{'kind':'table','scope':{'datasets':['experiment'],'metrics':['group','amount'],'parameters':params}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='original_e09_'+change;seen=[];original=runtime.publish
 def late(loop,raw):
  if loop.session_id==sid and not seen:
   seen.append({'raw':raw,'issued_snapshot':loop._publication_runtime[1].as_dict(),'issued_digest':loop._publication_runtime[1].digest});receipt=next(r for r in loop.context.analysis_state.tool_receipts if r['tool_name']=='top_n');path=cfg.sessions_resolved/sid/receipt['detail_ref']['path'];seen[0]['path']=str(path);seen[0]['preimage_hex']=path.read_bytes().hex()
   if change=='tamper':path.write_bytes(path.read_bytes()+b'changed')
   else:path.unlink()
  return original(loop,raw)
 monkeypatch.setattr(runtime,'publish',late)
 raw=b'group,amount\nA,1\nB,2\nC,3\nD,999\n'
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;resp=h.post('/api/chat',json={'session_id':sid,'message':text,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in resp.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);last=saved['messages'][-1];answer=read_answer(sid,last['answer_ref']) if last.get('answer_ref') else None
 _s3_budget_output(cfg,'normal_cache_'+change,{'fault':seen,'calls':model.calls,'requests':model.requests,'events':events,'saved':saved,'refresh':refresh,'answer':answer,'provider_calls':0})
 assert answer and len(seen)==1 and model.calls==['describe_dataset','record_analysis_plan','top_n'],events
 assert answer['snapshot_digest']!=seen[0]['issued_digest']
 assert not any(c.get('target',{}).get('tool')=='top_n' for c in answer['source_snapshot']['claims'])
 assert answer['requirement_outcomes'][0]['status'] in {'not_computed','evidence_insufficient'} and '| D | 999 |' not in answer['body']
 assert answer['body']==last['content']==[v for k,v in events if k=='turn_end'][0]['reply_content']


def _s3_compact_integrity_evidence(cfg):
 import os
 p=Path(os.environ.get('DATA_AGENT_S3_COMPACT_INTEGRITY_EVIDENCE',str(cfg.sessions_resolved/'compact_integrity_evidence')));p.mkdir(parents=True,exist_ok=True);return p


def _s3_compact_integrity_output(cfg,name,data):
 with (_s3_compact_integrity_evidence(cfg)/(name+'.json')).open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,default=str)


@pytest.mark.parametrize('mode',['large','micro','wrapper'])
def test_s3_original_e07_existing_unverified_original_not_claimed_or_deleted(engine,monkeypatch,mode):
 from data_agent.tools.registry import ToolResult
 from types import SimpleNamespace
 import data_agent.agent.loop as lm
 loop,cfg=engine;content='original\n'+'x'*20000+'\nD=999';path=compact._content_addressed_path(compact._session_tool_outputs_dir(loop.session_id),'same',content);path.write_bytes(b'preexisting different content');before=path.read_bytes()
 if mode=='large':result=compact.persist_large_output(loop.session_id,'same',content)
 elif mode=='micro':
  msgs=[{'role':'tool','tool_call_id':'same','content':content}]+[{'role':'tool','tool_call_id':'recent'+str(i),'content':'recent'} for i in range(compact.KEEP_RECENT)];compact.micro_compact(loop.session_id,msgs);result=msgs[0]['content']
 else:
  monkeypatch.setattr(lm,'persist_detail',lambda *a,**kw:(_ for _ in ()).throw(OSError('injected detail failure')));result=loop._compact_tool_output(ToolResult(summary=content),SimpleNamespace(id='same',name='top_n'))
 _s3_compact_integrity_output(cfg,mode,{'result':result,'original':content,'path':str(path),'preexisting_hex':before.hex(),'exists_after':path.exists(),'bytes_after_hex':path.read_bytes().hex() if path.exists() else None,'provider_calls':0})
 assert result==content, 'unverified existing path must not replace original tool content'
 assert path.exists() and path.read_bytes()==before, 'preexisting file must be preserved'


def test_s3_original_e07_normal_app_failed_summary_persistence_with_existing_bad_copy_keeps_original(engine,monkeypatch):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 import data_agent.agent.loop as lm
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False);monkeypatch.setattr(cfg,'model_context_tokens',1000000);monkeypatch.setattr(cfg,'model_max_input_tokens',884000);monkeypatch.setattr(cfg,'model_max_output_tokens',16000);monkeypatch.setattr(cfg,'max_tokens',16000)
 records=600;text='分析上传数据，将其命名为experiment；按amount降序交付全部600条原值。';params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':records,'topn_columns':['amount','label'],'topn_output':'records'};model=_NativeProductModel(text,'experiment','top_n',{'name':'experiment','n':records,'sort_by':'amount','ascending':False,'columns':'amount,label'},[{'kind':'table','scope':{'datasets':['experiment'],'metrics':['amount','label'],'parameters':params}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='compact_integrity';seen=[];real_store=compact._persist_tool_output
 def failed_original(session,key,content):
  if session==sid and len(content)>compact.PERSIST_THRESHOLD:
   path=compact._content_addressed_path(compact._session_tool_outputs_dir(session),key,content);path.write_bytes(b'preexisting different content');seen.append({'path':str(path),'original':content,'before_hex':path.read_bytes().hex()});value=real_store(session,key,content);seen[-1]['result']=value if value is not None else content;seen[-1]['after_hex']=path.read_bytes().hex() if path.exists() else None;return value
  return real_store(session,key,content)
 monkeypatch.setattr(compact,'_persist_tool_output',failed_original)
 raw=('amount,label\n'+''.join(str(i)+',row-'+str(i)+'\n' for i in range(records))).encode()
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;resp=h.post('/api/chat',json={'session_id':sid,'message':text,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in resp.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
 saved=load_session(sid);last=saved['messages'][-1];answer=read_answer(sid,last['answer_ref']) if last.get('answer_ref') else None
 _s3_compact_integrity_output(cfg,'normal',{'seen':seen,'events':events,'saved':saved,'answer':answer,'calls':model.calls,'raw_hex':raw.hex(),'ticket':ticket,'provider_calls':0})
 assert answer and seen and seen[0]['result']==seen[0]['original'], 'normal fallback advertised an invalid original copy'
 assert seen[0]['before_hex']==seen[0]['after_hex'] and '| 599 |' in answer['body'] and '| 0 |' in answer['body']


def _s3_compact_original_record(cfg,name,value):
 with (_s3_compact_integrity_evidence(cfg)/(name+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)


@pytest.mark.parametrize('size',[10000,20000])
def test_s3_original_e06_medium_large_tail_and_second_micro_compaction(engine,size):
 from data_agent.agent.compact import persist_large_output,micro_compact
 _,cfg=engine;sid='original_compact_'+str(size);body='head\n'+'x'*size+'\nTAIL_VALUE_D=999';preview=persist_large_output(sid,'same-id',body);messages=[{'role':'tool','tool_call_id':'same-id','content':body}]+[{'role':'tool','tool_call_id':'recent'+str(i),'content':'recent'+str(i)} for i in range(8)];recent=[dict(m) for m in messages[1:]];micro_compact(sid,messages);root=cfg.sessions_resolved/sid/'tool_outputs';before={p.name:p.read_bytes() for p in root.iterdir()};assert len(before)==1 and next(iter(before.values())).decode().replace('\r\n','\n')==body and messages[1:]==recent;first=messages[0]['content'];assert first.startswith('[Compacted:');micro_compact(sid,messages);after={p.name:p.read_bytes() for p in root.iterdir()};assert after==before and messages[0]['content']==first
 _s3_compact_original_record(cfg,'tail_'+str(size),{'size':size,'original_sha256':hashlib.sha256(body.encode()).hexdigest(),'root':str(root),'files':{n:hashlib.sha256(v).hexdigest() for n,v in before.items()},'tail':'TAIL_VALUE_D=999','first_summary':first,'second_summary':messages[0]['content'],'large_preview':preview,'original_retained':True,'provider_calls':0})


def test_s3_original_e07_same_tool_id_different_content_preserves_two_originals(engine):
 from data_agent.agent.compact import persist_large_output
 _,cfg=engine;sid='original_same_id';one='x'*20000+'TAIL_ONE=999';two='x'*20000+'TAIL_TWO=1998';a=persist_large_output(sid,'same-id',one);b=persist_large_output(sid,'same-id',two);root=cfg.sessions_resolved/sid/'tool_outputs';files={p.name:p.read_text(encoding='utf-8') for p in root.iterdir()};assert len(files)==2 and set(files.values())=={one,two} and a!=b
 _s3_compact_original_record(cfg,'same_id',{'root':str(root),'files':{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()},'tails':['TAIL_ONE=999','TAIL_TWO=1998'],'provider_calls':0})


@pytest.mark.parametrize('mode',['large','micro'])
def test_s3_original_e07_failed_write_never_claims_saved_or_replaces_original(engine,monkeypatch,mode):
 from data_agent.agent.compact import persist_large_output,micro_compact
 _,cfg=engine;sid='original_failure_'+mode;body='x'*20000+'TAIL_VALUE=999';root=cfg.sessions_resolved/sid/'tool_outputs';root.mkdir(parents=True);real=Path.open
 def fail(p,*args,**kwargs):
  if p.parent==root and args and args[0]=='x':raise OSError('controlled owned result write failure')
  return real(p,*args,**kwargs)
 monkeypatch.setattr(Path,'open',fail)
 if mode=='large':
  assert persist_large_output(sid,'id',body)==body
 else:
  msgs=[{'role':'tool','tool_call_id':'old','content':body}]+[{'role':'tool','tool_call_id':str(i),'content':'recent'} for i in range(8)];micro_compact(sid,msgs);assert msgs[0]['content']==body
 assert not list(root.iterdir());_s3_compact_original_record(cfg,'failure_'+mode,{'root':str(root),'original_sha256':hashlib.sha256(body.encode()).hexdigest(),'files':[],'saved_claim':False,'original_retained':True,'provider_calls':0})


@pytest.mark.parametrize('mode',['large','micro'])
@pytest.mark.parametrize('copy',['valid','invalid_utf8'])
def test_s3_original_e07_existing_copy_validated_without_mutation(engine,mode,copy):
 from data_agent.agent import compact
 _,cfg=engine;sid='original_copy_'+mode+'_'+copy;content='x'*20000+'TAIL=999';root=compact._session_tool_outputs_dir(sid);path=compact._content_addressed_path(root,'same',content);before=content.encode() if copy=='valid' else b'\xff\xfe';path.write_bytes(before);mtime=path.stat().st_mtime_ns
 if mode=='large':result=compact.persist_large_output(sid,'same',content)
 else:
  msgs=[{'role':'tool','tool_call_id':'same','content':content}]+[{'role':'tool','tool_call_id':str(i),'content':'recent'} for i in range(8)];compact.micro_compact(sid,msgs);result=msgs[0]['content']
 assert path.read_bytes()==before and path.stat().st_mtime_ns==mtime
 assert (result!=content)==(copy=='valid')
 _s3_compact_integrity_output(cfg,'copy_'+mode+'_'+copy,{'original':content,'before_hex':before.hex(),'after_hex':path.read_bytes().hex(),'result':result,'path':str(path),'mtime_unchanged':True,'provider_calls':0})


@pytest.mark.parametrize('behavior',['answer','tool_again','transport','savefail'])
def test_s3_original_e10_normal_app_tool_budget_preserves_independent_fact_and_missing_goal(engine,monkeypatch,behavior):
 from data_agent.agent.loop import AgentLoop
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False);original=AgentLoop._complete_analysis_turn;sid='original_e10_tool_budget_'+behavior
 def prepare(loop,*a,**kw):
  result=original(loop,*a,**kw)
  if loop.session_id==sid:loop.context.turn_state.budget.max_tool_calls=2
  return result
 monkeypatch.setattr(AgentLoop,'_complete_analysis_turn',prepare)
 class FinalizationModel(_S3OriginalBudgetModel):
  def chat(self,messages,system='',tools=None,**kw):
   if self.step>=4 and system!='你是一个JSON输出器，只返回JSON，不要其他内容。' and behavior in {'tool_again','transport'}:
    self.observe(messages,system,tools)
    if behavior=='transport':raise ConnectionError('controlled terminal transport failure')
    from data_agent.llm.client import Response,ToolCall
    return Response(tool_calls=[ToolCall('closed_attempt','top_n',self.args)])
   return super().chat(messages,system=system,tools=tools,**kw)
 if behavior=='savefail':
  import data_agent.session.history as store
  monkeypatch.setattr(store,'commit_accepted_answer',lambda *a,**kw:(_ for _ in ()).throw(OSError('controlled final save failure')))
 text='分析上传数据，将其命名为experiment；报告原表行数和按amount降序的全部四组记录，保留无法计算的具体缺口。';params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':4,'topn_columns':['group','amount'],'topn_output':'records'};model=FinalizationModel(text,'experiment','top_n',{'name':'experiment','n':4,'sort_by':'amount','ascending':False,'columns':'group,amount'},[{'kind':'measurement','scope':{'datasets':['experiment'],'quantity':'rows'}},{'kind':'table','scope':{'datasets':['experiment'],'metrics':['group','amount'],'parameters':params}}],preparatory_calls=[('describe_dataset',{'name':'experiment'})]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;raw=b'group,amount\nA,1\nB,2\nC,3\nD,999\n'
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;response=h.post('/api/chat',json={'session_id':sid,'message':text,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=h.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);msg=saved['messages'][-1];answer=read_answer(sid,msg['answer_ref']) if msg.get('answer_ref') else None;state=manager.get(sid).context.analysis_state;turn=manager.get(sid).context.turn_state
 _s3_budget_output(cfg,'normal_tool_budget_'+behavior,{'events':events,'saved':saved,'refresh':refresh,'answer':answer,'receipts':state.tool_receipts,'calls':model.calls,'requests':model.requests,'executed_nonmeta_calls':turn.tool_calls,'max_tool_calls':turn.budget.max_tool_calls,'provider_calls':0})
 assert len(model.requests)==5 and model.requests[-1]['tools_closed']
 ends=[v for k,v in events if k=='turn_end'];assert len(ends)==1
 if behavior in {'transport','savefail'}:
  assert not answer and ends[0]['status']=='failed'
  assert turn.tool_calls==2 and not any(r['tool_name']=='top_n' for r in state.tool_receipts)
  return
 assert answer and answer['requirement_outcomes'][0]['status']=='partial',events
 assert ends[0]['status']=='completed' and ends[0]['reply_content']==answer['body']==msg['content']
 assert turn.tool_calls==2 and not any(r['tool_name']=='top_n' for r in state.tool_receipts)
 assert any('budget_exceeded' in (m.get('content') or '') for m in saved['messages'] if m.get('role')=='tool')
 assert '4' in answer['body'] and '| D | 999 |' not in answer['body']
 assert len([v for k,v in events if k=='turn_end'])==1


@pytest.mark.parametrize('route',['sync','stream'])
@pytest.mark.parametrize('cause',['tool_calls','elapsed_time','fallback_calls','fallback_resolution','execution_guard'])
def test_s3_original_e10_cross_executor_budget_reason_and_closure(engine,route,cause):
 from data_agent.agent.execution_control import BudgetExceeded
 from data_agent.llm.client import ToolCall,Response
 loop,cfg=engine;loop._reset_turn_tracking();tc=ToolCall('blocked','describe_dataset',{'name':'orders'})
 class State:
  def ensure_can_call(self,*a,**kw):raise BudgetExceeded('language-independent guard',code=cause)
 loop.context.turn_state=State()
 if route=='sync':result=loop._execute_tools_sequential([tc],'');events=[]
 else:events=list(loop._process_tool_calls(Response(tool_calls=[tc]),1));result=None
 closes=cause in {'tool_calls','elapsed_time','fallback_calls'}
 assert bool(loop._turn_budget_exhaustion)==closes and bool(loop._turn_finalization_mode)==closes
 if closes:
  assert result is None and loop._tools_for_current_round() is None
  assert not any(e['type']=='error' for e in events)
 else:assert loop._tools_for_current_round()
 _s3_budget_output(cfg,'executor_'+route+'_'+cause,{'events':events,'messages':loop.messages,'budget_closed':loop._turn_budget_exhaustion,'result':getattr(result,'content',None),'tool_receipts':loop.context.analysis_state.tool_receipts,'provider_calls':0})


@pytest.mark.parametrize('route',['direct','registry'])
def test_distribution_business_table_actual_direct_and_registry(engine,route):
 from data_agent.tools.registry import registry
 from data_agent.tools.eda import distribution_analysis
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish
 from data_agent.agent.publication.contracts import encode
 loop,cfg=engine;loop.context.workspace.add('orders',pd.DataFrame({'amount':[1.,2.,3.,4.]}));scope={'datasets':['orders'],'metrics':['amount']};request(loop,'交付amount完整分布统计',{'kind':'table','scope':scope});args={'name':'orders','columns':'amount'}
 binding=loop._capture_tool_execution_binding('distribution_analysis',args);plan=loop.context.analysis_state.analysis_plan;step=plan['method_plan'][0];binding.update(plan_id=plan['id'],plan_sha256=plan['plan_sha256'],step_id=step['step_id'],requirement_ids=step['requirement_ids'],required_delivery_ids=[d['id'] for d in step['required_deliveries']])
 result=registry.execute('distribution_analysis',args) if route=='registry' else distribution_analysis(**args);text=result.summary if hasattr(result,'summary') else result;data=result.data if hasattr(result,'data') and result.data else json.loads(text);loop._record_turn_tool_result('distribution_analysis',text,args,'display_'+route,data,execution_binding=binding);host=snapshot_for_turn(loop);body,error=publish(loop,encode({'schema':'answer_bindings.v2','snapshot_digest':host.digest,'sections':[]}));a=loop._accepted_answer;table=next(c for c in a['source_snapshot']['claims'] if c['basis_refs'][0]['result_path']==['amount']);_s3_distribution_id_save("distribution_"+route,{'tool_result':data,'answer':a,'body':body,'source_table':table,'raw_structure_visible':'"quantile_interpolation"' in body and '"normality_test"' in body,'provider_calls':0,'display_implemented':True})
 assert error is None and table['value']['mean']==2.5 and [table['value']['quantiles'][k] for k in ['min','25%','50%','75%','max']]==[1.,1.75,2.5,3.25,4.]
 assert '"quantile_interpolation"' not in body and '"normality_test"' not in body
 assert '总体标准差' in body and '1.75' in body and '0.9718770585603881' in body and '未拒绝正态性' in body


def test_normal_agentloop_opaque_call_id_and_summary_failure_cannot_escape(engine,monkeypatch):
 import io
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.llm.client import ToolCall
 import data_agent.agent.loop as lm
 _,cfg=engine;monkeypatch.setattr(cfg,'mcp_enabled',False);monkeypatch.setattr(cfg,'model_context_tokens',1000000);monkeypatch.setattr(cfg,'model_max_input_tokens',884000);monkeypatch.setattr(cfg,'model_max_output_tokens',16000);monkeypatch.setattr(cfg,'max_tokens',16000);sid='opaque_id';attempts=[];failures=[];real=Path.open
 def guard(p,*a,**kw):
  if a and a[0] in {'x','w','wb','xb'} and p.drive.lower()=='d:' and p.name.startswith('unowned'):
   attempts.append(str(p.resolve()));raise OSError('safely intercepted before unowned write')
  if a and a[0]=='x' and p.suffix=='.txt' and p.parent==cfg.sessions_resolved/sid/'tool_outputs':
   failures.append(str(p));raise OSError('controlled full summary failure')
  return real(p,*a,**kw)
 monkeypatch.setattr(Path,'open',guard)
 class Model(_NativeProductModel):
  def chat(self,*a,**kw):
   r=super().chat(*a,**kw)
   if r.has_tool_calls:r.tool_calls=[ToolCall('D:unowned',c.name,c.arguments) if c.name=='top_n' else c for c in r.tool_calls]
   return r
 n=600;text='分析上传数据，将其命名为experiment；按amount降序交付全部600条原值。';params={'topn_sort_by':'amount','topn_ascending':False,'topn_n':n,'topn_columns':['amount','label'],'topn_output':'records'};model=Model(text,'experiment','top_n',{'name':'experiment','sort_by':'amount','ascending':False,'n':n,'columns':'amount,label'},[{'kind':'table','scope':{'datasets':['experiment'],'metrics':['amount','label'],'parameters':params}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;raw=('amount,label\n'+''.join(str(i)+',row-'+str(i)+'\n' for i in range(n))).encode()
 with app.test_client() as h:
  ticket=h.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket;r=h.post('/api/chat',json={'session_id':sid,'message':text,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in r.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
 saved=load_session(sid);a=read_answer(sid,saved['messages'][-1]['answer_ref']);root=cfg.sessions_resolved/sid;_s3_distribution_id_save('opaque_normal',{'attempts':attempts,'summary_failures':failures,'events':events,'saved':saved,'answer':a,'tool_files':[str(p) for p in (root/'tool_outputs').iterdir()],'session_dir':str(root),'unowned_writes':0,'provider_calls':0})
 assert not attempts, 'unsafe writes were blocked by test interceptor, not by product'
 assert '| 599 |' in a['body'] and '| 0 |' in a['body']

 assert failures,'The fault must reach the current unique original persistence path'


@pytest.mark.parametrize("conclusion,p_value,expected",[("not_rejected",0.9718770585603881,"未拒绝正态性"),("rejected",0.000000123456789012345,"拒绝正态性"),("unknown",None,"未知")])
def test_distribution_business_table_precision_unknown_and_literal_cells(conclusion,p_value,expected):
 from data_agent.agent.publication.renderer import _business_table
 from data_agent.tools.report import _markdown_to_html
 value={"count":4,"mean":0.423456789012345,"std":1.118,"skewness":0.,"kurtosis":-1.36,
        "quantiles":{"min":None,"25%":1.75,"50%":2.5,"75%":3.25,"max":4.},
        "quantile_interpolation":"linear","observation":{"source_rows":5,"count":4,"missing_count":0,"excluded_nonfinite":1},
        "normality_test":{"conclusion":conclusion,"p_value":p_value,"reason":"未知原因|<script>bad()</script>" if p_value is None else ""}}
 claim={"label":"amount|<img src=x onerror=ops>","target":{"tool":"distribution_analysis","business_product":{"kind":"table","parameters":{},"metrics":["amount"]}},"value":value}
 body=_business_table(claim,());html=_markdown_to_html(body)
 assert "0.423456789012345" in body and expected in body
 assert "<table>" in html and "<script>" not in html and "<img " not in html
 assert "amount" in html and "onerror=ops" in html
 if p_value is None:assert "未知原因" in body and "未知" in body
 else:assert str(p_value) in body


@pytest.mark.parametrize("restart", [False, True])
def test_s3_normal_auto_window_answer_then_equivalent_followup_is_not_suspended(engine, monkeypatch, restart):
    import os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    from data_agent.llm.client import Response
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
    _, cfg = engine
    first_text = "加载上传数据并将其命名为experiment，比较amount的变化；由我选择比较范围。"
    followup = "再次比较experiment的amount，沿用同一比较范围。"
    params = {"comparison_date_col":"day", "comparison_dimensions":[], "comparison_formulas":{}, "period_a":"2026-10-01~2026-10-07", "period_b":"2026-10-08~2026-10-14", "comparison_output":"comparison"}
    specs = [{"kind":"table", "scope":{"datasets":["experiment"], "metrics":["amount"], "parameters":params}}]
    class Model(_NativeProductModel):
        second = False
        goal_id = ""
        def chat(self, messages, system="", tools=None, **kw):
            if system == "你是一个JSON输出器，只返回JSON，不要其他内容。" and self.second:
                return Response(text=encode({"intent_type":"directed_analysis", "requested_outputs":[{"kind":"result", "exact_span":followup, "op":"reuse", "target_id":self.goal_id}]}))
            if system != "你是一个JSON输出器，只返回JSON，不要其他内容。":
                view = ScriptedClient._current_host_snapshot(messages, system)
                if view.get("execution_targets"):
                    self.goal_id = next(r["id"] for r in view["execution_targets"] if r["semantic_kind"] == "result")
                if self.second:
                    return Response(text=encode({"schema":"answer_bindings.v2", "snapshot_digest":view["snapshot_digest"], "sections":[{"requirement_ids":[r["id"]], "parts":[{"kind":"claim", "ref":cid} for cid in r["claim_ids"]]} for r in view["requirements"] if not r["withdrawn"]]}))
            return super().chat(messages, system=system, tools=tools, **kw)
    model = Model(first_text, "experiment", "compare_periods", {"name":"experiment", "date_col":"day", "metrics":"amount", "period_a":params["period_a"], "period_b":params["period_b"]}, specs)
    factory = lambda: AgentManager(client_factory=lambda **kw:model, auxiliary_client_factory=lambda:model)
    manager = factory(); app = create_app(); app.config["agent_manager"] = manager
    sid = "auto_window_" + str(restart)
    raw = ("day,amount\n" + "".join(f"2026-10-{i:02d},{10 if i<=7 else 20}\n" for i in range(1,15))).encode()
    events = lambda response: [(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
    with app.test_client() as http:
        ticket = http.post("/api/upload", data={"file":(io.BytesIO(raw),"experiment.csv")}, content_type="multipart/form-data").get_json(); model.ticket=ticket
        first = events(http.post("/api/chat",json={"session_id":sid,"message":first_text,"uploads":[ticket]}))
        detail = http.get("/api/sessions/"+sid).get_json(); active = detail.get("active_confirmation")
        assert active and active["confirmation_type"] == "time_window", {"events":first,"detail":detail}
        resumed = events(http.post("/api/chat/resume",json={"session_id":sid,"confirmation_id":active["confirmation_id"],"expected_version":active["version"],"idempotency_key":"window_once","user_response":"last_7_vs_previous_7"}))
        saved_first = load_session(sid); accepted_first = read_answer(sid,saved_first["messages"][-1]["answer_ref"])
        assert accepted_first["requirement_outcomes"][0]["status"] == "answered", resumed
        if restart:
            manager = factory(); app.config["agent_manager"] = manager
        model.second = True
        second = events(http.post("/api/chat",json={"session_id":sid,"message":followup}))
        refreshed = http.get("/api/sessions/"+sid).get_json()
        trust = http.get("/api/sessions/"+sid+"/trust").get_json()
    saved = load_session(sid); loop = manager.get(sid)
    last = next((m for m in reversed(saved["messages"]) if m.get("answer_ref")),None)
    answer = read_answer(sid,last["answer_ref"]) if last else None
    _s3_assert_workbench_uses_original_accepted_parts(trust, answer)
    out = Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(cfg.sessions_resolved/"evidence")));out.mkdir(parents=True,exist_ok=True)
    (out/("normal_auto_window_"+str(restart)+".json")).write_text(json.dumps({"raw_hex":raw.hex(),"ticket":ticket,"first":first,"active":active,"resumed":resumed,"second":second,"saved":saved,"refreshed":refreshed,"trust":trust,"answer":answer,"first_answer":accepted_first,"state":loop.context.analysis_state.to_dict(),"calls":model.calls,"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    assert not [e for e in second if e[0] in {"suspended","error"}], second
    assert len([e for e in second if e[0]=="turn_end"]) == 1
    assert [e[1]["status"] for e in second if e[0]=="turn_end"] == ["completed"]
    assert refreshed["active_confirmation"] is None
    assert answer["body"] == last["content"] and all(r["status"]=="answered" for r in answer["requirement_outcomes"])
    with use_agent_context(loop.context):
        ambiguous=export_assistant_reply(sid,answer["body"],"md")
        exported=export_assistant_reply(sid,answer["body"],"md",reply_id=last["reply_id"])
    assert ambiguous["error_type"] == "ambiguous_reply"
    assert exported["status"] == "exported"
    (out/("normal_auto_window_"+str(restart)+".md")).write_bytes((cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes())


def test_s3_normal_workbench_eight_facts_and_pending_gap_keep_one_accepted_answer(engine):
    import os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    from data_agent.llm.client import Response
    from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
    _,cfg=engine
    requested="报告记录数及amount的唯一值数、最小值、最大值、合计、均值、中位数、样本标准差"
    missing="判断这些观测能否证明促销增量"
    content="加载上传数据并将其命名为experiment；"+requested+"；"+missing+"。"
    expected={"rows":3,"unique_values":3,"min":10,"max":30,"sum":60,"mean":20,"50%":20,"std":10}
    specs=[{"kind":"measurement","scope":{"datasets":["experiment"],"quantity":q,**({"metrics":["amount"]} if q!="rows" else {})}} for q in expected]
    class Model(_NativeProductModel):
        def chat(self,messages,system="",tools=None,**kw):
            response=super().chat(messages,system=system,tools=tools,**kw)
            if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
                parsed=json.loads(response.text)
                parsed["requested_outputs"]=[{"kind":"result","exact_span":requested,"business_scope":{"datasets":["experiment"]}},{"kind":"gap","exact_span":missing}]
                response.text=encode(parsed)
            elif response.text and self.step>3:
                view=ScriptedClient._current_host_snapshot(messages,system)
                claims=[dict(zip(view["claim_fields"],row)) for row in view["claims"]]
                selected={c["id"] for c in claims if c["delivery_kind"]=="measurement" and c["quantity"] in expected and c["declared_delivery_ids"]}
                assert len(selected)==8
                response.text=encode({"schema":"answer_bindings.v2","snapshot_digest":view["snapshot_digest"],"sections":[{"requirement_ids":[r["id"]],"parts":[{"kind":"claim","ref":cid} for cid in r["claim_ids"] if cid in selected]} for r in view["requirements"] if not r["withdrawn"]]})
            return response
    model=Model(content,"experiment","describe_dataset",{"name":"experiment"},specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config["agent_manager"]=manager
    sid="workbench_eight";raw=b"amount\n10\n20\n30\n"
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"experiment.csv")},content_type="multipart/form-data").get_json();model.ticket=ticket
        response=http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]})
        events=[(b.split("\n",1)[0][7:],json.loads(b.split("\ndata: ",1)[1])) for b in response.get_data(as_text=True).split("\n\n") if b.startswith("event:")]
        refreshed=http.get("/api/sessions/"+sid).get_json();view=http.get("/api/sessions/"+sid+"/trust").get_json()
    saved=load_session(sid);last=saved["messages"][-1];answer=read_answer(sid,last["answer_ref"]);loop=manager.get(sid)
    _s3_assert_workbench_uses_original_accepted_parts(view, answer)
    out=Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(cfg.sessions_resolved/"evidence")));out.mkdir(parents=True,exist_ok=True)
    with use_agent_context(loop.context):
        exports={fmt:export_assistant_reply(sid,answer["body"],fmt,reply_id=last["reply_id"]) for fmt in ["md","html"]}
    (out/"normal_workbench_eight.json").write_text(json.dumps({"raw_hex":raw.hex(),"ticket":ticket,"events":events,"view":view,"saved":saved,"refreshed":refreshed,"answer":answer,"state":loop.context.analysis_state.to_dict(),"exports":exports,"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    wb=view["workbench"];assert wb["verified_total"]==len(wb["verified_conclusions"])==8
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    values={c["target"]["statistic"]:c["value"] for c in answer["source_snapshot"]["claims"] if c["id"] in accepted}
    assert values==expected
    assert len(wb["pending_findings"])==1
    pending=wb["pending_findings"][0];assert pending["claim"]==missing and pending["status_label"]=="证据不足"
    assert pending["basis"] and not pending["basis"].startswith("ans_") and pending["gap"] and pending["next_step"]
    assert pending["id"] not in {c["id"] for c in wb["verified_conclusions"]}
    ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]=="completed"
    assert answer["body"]==last["content"]==ends[0]["reply_content"]
    assert next(m for m in reversed(refreshed["messages"]) if m.get("reply_id")==last["reply_id"])["content"]==answer["body"]
    for fmt,result in exports.items():
        assert result["status"]=="exported"
        (out/("normal_workbench_eight."+fmt)).write_bytes((cfg.sessions_resolved/sid/"reports"/result["artifact_path"].split("/")[-1]).read_bytes())


@pytest.mark.parametrize("restart",[False,True])
def test_s3_normal_single_card_filters_reused_method_and_restores_one_batch_answer(engine,restart):
    import os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    from data_agent.llm.client import Response,ToolCall
    _,cfg=engine
    content="加载上传数据并将其命名为experiment，我将回答成本口径和窗口；计算amount的分期合计，不要求计算净收益。"
    cost={"question":"净收益的成本是否包含券成本？","options":[{"label":"包含","value":"include"},{"label":"不包含","value":"exclude"}]}
    method={"question":"是否使用留存方法继续分析？","options":[{"label":"按此方法继续","value":"yes"}],"confirmation_type":"method_confirmation"}
    window={"question":"比较窗口采用近7天还是近30天？","options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}],"confirmation_type":"time_window"}
    params={"comparison_date_col":"day","comparison_dimensions":[],"comparison_formulas":{},"period_a":"2026-10-01~2026-10-07","period_b":"2026-10-08~2026-10-14","comparison_output":"comparison"}
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"metrics":["amount"],"parameters":params}}]
    class Model(_NativeProductModel):
        cost_asked=False;batch_asked=False
        def chat(self,messages,system="",tools=None,**kw):
            if system!="你是一个JSON输出器，只返回JSON，不要其他内容。":
                if not self.cost_asked:
                    self.cost_asked=True;self.calls.append("ask_cost");return Response(tool_calls=[ToolCall("cost_question","ask_user_question",dict(cost,confirmation_type="metric_scope",blocking_reason="成本口径由用户决定。"))])
                if not self.batch_asked:
                    self.batch_asked=True;self.calls.append("ask_batch");return Response(tool_calls=[ToolCall("batch_question","ask_user_question",{"questions":json.dumps([cost,method,window],ensure_ascii=False),"confirmation_type":"metric_scope","blocking_reason":"只有比较窗口仍缺失。"})])
            return super().chat(messages,system=system,tools=tools,**kw)
    model=Model(content,"experiment","compare_periods",{"name":"experiment","date_col":"day","metrics":"amount","period_a":params["period_a"],"period_b":params["period_b"]},specs)
    factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    manager=factory();app=create_app();app.config["agent_manager"]=manager;sid="mixed_card_"+str(restart)
    raw=("day,amount\n"+"".join(f"2026-10-{i:02d},{10 if i<=7 else 20}\n" for i in range(1,15))).encode()
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"experiment.csv")},content_type="multipart/form-data").get_json();model.ticket=ticket
        first=_askq_events(http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]}));active=http.get("/api/sessions/"+sid).get_json()["active_confirmation"]
        assert active["question"]==cost["question"]
        second=_askq_events(http.post("/api/chat/resume",json={"session_id":sid,"confirmation_id":active["confirmation_id"],"expected_version":active["version"],"idempotency_key":"cost_once","user_response":"include"}))
        detail=http.get("/api/sessions/"+sid).get_json();batch=detail["active_confirmation"];visible=json.loads(batch["context"])
        assert len(visible)==1 and visible[0]["question"]==window["question"]
        payload={"session_id":sid,"confirmation_id":batch["confirmation_id"],"expected_version":batch["version"],"idempotency_key":"window_once","user_response":json.dumps([{"question_id":visible[0]["question_id"],"question":window["question"],"answer":"window7","is_free_input":False}],ensure_ascii=False)}
        if restart:manager=factory();app.config["agent_manager"]=manager
        final=_askq_events(http.post("/api/chat/resume",json=payload));calls=list(model.calls)
        replay=_askq_events(http.post("/api/chat/resume",json=payload));refreshed=http.get("/api/sessions/"+sid).get_json();view=http.get("/api/sessions/"+sid+"/trust").get_json()
    saved=load_session(sid);loop=manager.get(sid);last=next(m for m in reversed(saved["messages"]) if m.get("answer_ref"));answer=read_answer(sid,last["answer_ref"])
    record=loop._confirmation_runtime().get(sid,batch["confirmation_id"]);bound=json.loads(record.response)
    assert [r["status"] for r in bound]==["reused","advisory","resolved"]
    assert [bound[0]["answer"],bound[-1]["answer"]]==["include","window7"]
    assert model.calls==calls and model.calls.count("compare_periods")==1
    assert refreshed["active_confirmation"] is None and all(r["status"]=="answered" for r in answer["requirement_outcomes"])
    for events,status in [(first,"suspended"),(second,"suspended"),(final,"completed"),(replay,"completed")]:
        ends=[d for e,d in events if e=="turn_end"];assert len(ends)==1 and ends[0]["status"]==status
    assert answer["body"]==last["content"]==next(d["reply_content"] for e,d in final if e=="turn_end")
    _s3_assert_workbench_uses_original_accepted_parts(view, answer)
    out=Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(cfg.sessions_resolved/"evidence")));out.mkdir(parents=True,exist_ok=True)
    with use_agent_context(loop.context):exported=export_assistant_reply(sid,answer["body"],"md",reply_id=last["reply_id"])
    assert exported["status"]=="exported"
    (out/("normal_mixed_card_"+str(restart)+".md")).write_bytes((cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes())
    (out/("normal_mixed_card_"+str(restart)+".json")).write_text(json.dumps({"raw_hex":raw.hex(),"ticket":ticket,"first":first,"second":second,"final":final,"replay":replay,"visible":visible,"record":record.to_dict(),"answer":answer,"saved":saved,"refreshed":refreshed,"view":view,"state":loop.context.analysis_state.to_dict(),"calls":calls,"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")


def _s3_assert_workbench_uses_original_accepted_parts(view, answer):
    original = {t["ref"]: t["rendered_text"] for t in answer["render_trace"]
                if t["kind"] == "claim" and t["disposition"] == "accepted"}
    assert {c["id"]: c["summary"] for c in view["workbench"]["verified_conclusions"]} == original


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("prior_answer", [False, True])
def test_s3_normal_related_upload_revalidates_question_before_new_answer(engine, restart, prior_answer):
    """Public model proposals plus real upload/chat/resume and persisted artifacts."""
    import os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    from data_agent.llm.client import Response
    _, cfg = engine
    first_text = "加载上传数据并将其命名为experiment，比较amount的变化；由我选择比较范围。"
    replacement = "上传附件是experiment的新版，请替换原目标并比较新版amount的变化；由我重新选择比较范围。"
    def parameters(start):
        return {"comparison_date_col":"day", "comparison_dimensions":[], "comparison_formulas":{},
                "period_a":f"2026-10-{start:02d}~2026-10-{start+6:02d}",
                "period_b":f"2026-10-{start+7:02d}~2026-10-{start+13:02d}", "comparison_output":"comparison"}
    def specs(params):
        return [{"kind":"table", "scope":{"datasets":["experiment"],"metrics":["amount"],"parameters":params}}]
    class Model(_NativeProductModel):
        replacing = False
        def chat(self, messages, system="", **kw):
            if self.replacing and system == "你是一个JSON输出器，只返回JSON，不要其他内容。":
                declared, _ = json.JSONDecoder().raw_decode(messages[-1]["content"].partition("canonical_requirements: ")[2])
                prior = next(r for r in reversed(declared) if r["lifecycle_status"]=="active" and r["semantic_kind"]=="result")
                return Response(text=encode({"intent_type":"directed_analysis", "requested_outputs":[
                    {"kind":"result", "exact_span":replacement,"op":"replace","target_id":prior["id"],"business_scope":{"datasets":["experiment"]}}],
                    "upload_bindings":[{"upload_id":self.ticket["upload_id"],"dataset":"experiment","relation":"replace","exact_span":replacement,"object_span":"experiment"}]}))
            return super().chat(messages, system=system, **kw)
    params=parameters(1)
    model=Model(first_text,"experiment","compare_periods",{"name":"experiment","date_col":"day","metrics":"amount","period_a":params["period_a"],"period_b":params["period_b"]},specs(params))
    factory=lambda:AgentManager(client_factory=lambda **kw:model, auxiliary_client_factory=lambda:model)
    manager=factory();app=create_app();app.config["agent_manager"]=manager
    sid=f"related_upload_{restart}_{prior_answer}"
    raw=("day,amount\n"+"".join(f"2026-10-{i:02d},{10 if i<=7 else 20}\n" for i in range(1,15))).encode()
    newer=("day,amount\n"+"".join(f"2026-10-{i:02d},{30 if i<=21 else 50}\n" for i in range(15,29))).encode()
    def resume_payload(active,key):
        return {"session_id":sid,"confirmation_id":active["confirmation_id"],"expected_version":active["version"],"idempotency_key":key,"user_response":"last_7_vs_previous_7"}
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"experiment.csv")},content_type="multipart/form-data").get_json();model.ticket=ticket
        first=_askq_events(http.post("/api/chat",json={"session_id":sid,"message":first_text,"uploads":[ticket]}))
        old=http.get("/api/sessions/"+sid).get_json()["active_confirmation"]
        assert old and old["confirmation_type"]=="time_window",first
        first_resume=[];old_answer=None;old_saved=None
        if prior_answer:
            first_resume=_askq_events(http.post("/api/chat/resume",json=resume_payload(old,"old_once")))
            old_saved=load_session(sid)["messages"][-1];old_answer=read_answer(sid,old_saved["answer_ref"])
            assert all(o["status"]=="answered" for o in old_answer["requirement_outcomes"]),first_resume
        if restart:manager=factory();app.config["agent_manager"]=manager
        params=parameters(15);model.replacing=True;model.content=replacement;model.step=0
        model.specs=specs(params);model.args=dict(model.args,period_a=params["period_a"],period_b=params["period_b"])
        new_ticket=http.post("/api/upload",data={"file":(io.BytesIO(newer),"experiment_v2.csv")},content_type="multipart/form-data").get_json();model.ticket=new_ticket
        changed=_askq_events(http.post("/api/chat",json={"session_id":sid,"message":replacement,"uploads":[new_ticket]}))
        current=http.get("/api/sessions/"+sid).get_json()["active_confirmation"]
        assert current and current["confirmation_id"]!=old["confirmation_id"],changed
        loop=manager.get(sid);service=loop._confirmation_runtime();old_record=service.get(sid,old["confirmation_id"])
        assert old_record.status.value==("resolved" if prior_answer else "expired")
        assert old_record.response==("last_7_vs_previous_7" if prior_answer else None)
        new_record=service.get(sid,current["confirmation_id"])
        assert new_record.data_version!=old_record.data_version
        assert new_record.resolution_params["host_binding"]["status"]=="host_bound"
        calls_before=list(model.calls)
        stale=_askq_events(http.post("/api/chat/resume",json=resume_payload(old,"old_stale")))
        assert [d["status"] for e,d in stale if e=="turn_end"]==["failed"],stale
        assert model.calls==calls_before
        if restart:manager=factory();app.config["agent_manager"]=manager
        final=_askq_events(http.post("/api/chat/resume",json=resume_payload(current,"new_once")))
        calls=list(model.calls)
        replay=_askq_events(http.post("/api/chat/resume",json=resume_payload(current,"new_once")))
        refreshed=http.get("/api/sessions/"+sid).get_json();view=http.get("/api/sessions/"+sid+"/trust").get_json()
    saved=load_session(sid);last=next(m for m in reversed(saved["messages"]) if m.get("answer_ref"));answer=read_answer(sid,last["answer_ref"]);loop=manager.get(sid)
    for events,status in [(first,"suspended"),(changed,"suspended"),(final,"completed"),(replay,"completed")]:
        assert [d["status"] for e,d in events if e=="turn_end"]==[status],events
    assert model.calls==calls and model.calls.count("compare_periods")==1+int(prior_answer)
    assert answer["body"]==last["content"]==next(d["reply_content"] for e,d in final if e=="turn_end")
    assert {o["requirement_id"]:o["status"] for o in answer["requirement_outcomes"]}=={r["id"]:("withdrawn" if r["withdrawn"] else "answered") for r in answer["source_snapshot"]["requirements"]},answer
    assert refreshed["active_confirmation"] is None
    published=[m for m in refreshed["messages"] if m.get("answer_ref")==last["answer_ref"]]
    assert len(published)==1 and published[0]["content"]==answer["body"] and published[0]["reply_id"]==last["reply_id"]
    _s3_assert_workbench_uses_original_accepted_parts(view,answer)
    if old_answer:assert read_answer(sid,old_saved["answer_ref"])==old_answer
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    comparisons=[c["value"] for c in answer["source_snapshot"]["claims"] if c["id"] in accepted]
    assert len(comparisons)==1 and comparisons[0]["amount"]["exact_aggregates"]=={"period_a":210.0,"period_b":350.0,"diff":140.0},comparisons
    with use_agent_context(loop.context):
        identity=loop.context.workspace._publication_data_identity("experiment")
        exported=export_assistant_reply(sid,answer["body"],"md",reply_id=last["reply_id"])
    assert identity["source_origins"][0]["file_sha256"]==new_ticket["sha256"]=="sha256:"+hashlib.sha256(newer).hexdigest()
    assert exported["status"]=="exported"
    out=Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(cfg.sessions_resolved/"evidence")));out.mkdir(parents=True,exist_ok=True)
    stem=f"normal_related_upload_{restart}_{prior_answer}"
    (out/(stem+".json")).write_text(json.dumps({"raw_hex":raw.hex(),"new_hex":newer.hex(),"ticket":ticket,"new_ticket":new_ticket,"first":first,"old":old,"first_resume":first_resume,"old_answer":old_answer,"changed":changed,"current":current,"old_record":old_record.to_dict(),"new_record":new_record.to_dict(),"stale":stale,"final":final,"replay":replay,"answer":answer,"saved":saved,"refreshed":refreshed,"view":view,"identity":identity,"state":loop.context.analysis_state.to_dict(),"calls":calls,"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    (out/(stem+".md")).write_bytes((cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes())


@pytest.mark.parametrize("multi",[False,True])
@pytest.mark.parametrize("ambient",["none","other_session"])
def test_s3_normal_cli_original_values_in_owned_context_plan_save_refresh_export(tmp_path,monkeypatch,multi,ambient):
    import os
    from pathlib import Path
    from contextlib import nullcontext
    import data_agent.session.task_manager as tasks
    import data_agent.tools.interaction as ui
    from data_agent.tools import discover_tools
    from data_agent.config import get_config
    from data_agent.agent.loop import AgentLoop
    from data_agent.agent.context import use_agent_context,get_current_context
    from data_agent.llm.client import Response,ToolCall
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.tools.report import export_assistant_reply
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    discover_tools();cfg=get_config()
    from data_agent.tools.task_tools import task_manager as workflow_manager
    assert workflow_manager is tasks.task_manager, "test fixture must use the original single task owner"
    monkeypatch.setattr(cfg,"sessions_dir",tmp_path/"sessions");monkeypatch.setattr(cfg,"workspace_dir",tmp_path/"workspace")
    monkeypatch.setattr(cfg,"mcp_enabled",False);monkeypatch.setattr(cfg,"skill_auto_discover",False)
    monkeypatch.setattr(tasks.task_manager,"_dir",tmp_path/"tasks");monkeypatch.setattr(tasks.task_manager,"_next_id_val",0)
    raw=b"amount,orders\n10,1\n20,2\n30,3\n";source=cfg.workspace_resolved/"inbox"/"experiment.csv";source.parent.mkdir(parents=True);source.write_bytes(raw)
    content="载入experiment.csv为experiment，按我随后选择的字段计算合计。"
    chosen=["amount","orders"] if multi else ["amount"]
    specs=[{"kind":"measurement","scope":{"datasets":["experiment"],"metrics":[column],"quantity":"sum"}} for column in chosen]
    class Model(_NativeProductModel):
        loaded=False;asked=False
        def chat(self,messages,system="",**kw):
            if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
                return Response(text=encode({"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":content,"business_scope":{"datasets":["experiment"]}}]}))
            if not self.loaded:
                self.loaded=True;self.calls.append("load_data");return Response(tool_calls=[ToolCall("cli_load","load_data",{"source":"experiment.csv","name":"experiment"})])
            if not self.asked:
                self.asked=True;self.calls.append("ask_user_question");return Response(tool_calls=[ToolCall("cli_fields","ask_user_question",{"question":"需要哪几个字段的合计？","options":[{"label":"销售金额","value":"amount"},{"label":"订单数","value":"orders"}],"multi_select":multi,"confirmation_type":"metric_scope","blocking_reason":"所选字段决定本次合计的对象。"})])
            if self.step==0:
                self.step=1;self.calls.append("quick_profile")
                return Response(tool_calls=[ToolCall("cli_schema","quick_profile",{"name":"experiment"})])
            return super().chat(messages,system=system,**kw)
    model=Model(content,"experiment","describe_dataset",{"name":"experiment"},specs)
    sid="normal_cli_"+str(multi)+"_"+ambient
    loop=AgentLoop(client=model,auxiliary_llm_client=model,session_id=sid)
    other=AgentLoop(client=None,session_id="unrelated_ambient") if ambient=="other_session" else None
    monkeypatch.setattr(ui,"_robust_input",lambda *a,**kw:"1,2" if multi else "1")
    with use_agent_context(other.context) if other else nullcontext():
        original_context=get_current_context();reply=loop.run_turn(content)
        assert get_current_context() is original_context
    saved=load_session(sid);last=next((m for m in reversed(saved["messages"]) if m.get("answer_ref")),None)
    assert last is not None,{"reply":reply,"calls":model.calls}
    answer=read_answer(sid,last["answer_ref"])
    records=loop._confirmation_runtime()._store(sid).load_records();assert len(records)==1
    record=next(iter(records.values()));assert record.response==(["amount","orders"] if multi else "amount") and record.status.value=="resolved"
    assert record.resolution_params["host_binding"]["session_id"]==sid
    assert reply==last["content"]==answer["body"] and all(o["status"]=="answered" for o in answer["requirement_outcomes"])
    assert model.calls==["load_data","ask_user_question","quick_profile","record_analysis_plan","describe_dataset"]
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    assert sorted(c["value"] for c in answer["source_snapshot"]["claims"] if c["id"] in accepted)==([6,60] if multi else [60])
    app=create_app();app.config["agent_manager"]=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    with app.test_client() as http:
        refreshed=http.get("/api/sessions/"+sid).get_json();view=http.get("/api/sessions/"+sid+"/trust").get_json()
    published=[m for m in refreshed["messages"] if m.get("answer_ref")==last["answer_ref"]];assert len(published)==1 and published[0]["content"]==answer["body"]
    assert refreshed["active_confirmation"] is None
    _s3_assert_workbench_uses_original_accepted_parts(view,answer)
    with use_agent_context(loop.context):
        identity=loop.context.workspace._publication_data_identity("experiment")
        exported=export_assistant_reply(sid,answer["body"],"md",reply_id=last["reply_id"])
    assert identity["source_origins"][0]["file_sha256"]=="sha256:"+hashlib.sha256(raw).hexdigest()
    assert exported["status"]=="exported"
    md=(cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes();assert answer["body"] in md.decode("utf-8").replace("\r\n","\n")
    out=Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(tmp_path/"evidence")));out.mkdir(parents=True,exist_ok=True);stem="normal_cli_"+str(multi)+"_"+ambient
    (out/(stem+".json")).write_text(json.dumps({"raw_hex":raw.hex(),"answer":answer,"saved":saved,"refreshed":refreshed,"view":view,"identity":identity,"record":record.to_dict(),"state":loop.context.analysis_state.to_dict(),"calls":model.calls,"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    (out/(stem+".md")).write_bytes(md)


@pytest.mark.parametrize("restart",[False,True])
def test_s3_normal_unbound_old_question_new_request_current_source_once_save_refresh_export(engine,restart):
    import os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    from data_agent.llm.client import Response,ToolCall
    _,cfg=engine
    left_goal="分别独立分析left的amount净收益";right_goal="分别独立分析right的amount净收益"
    first_text="文件甲将其命名为left，文件乙将其命名为right；"+left_goal+"；"+right_goal+"；两表不合并，共同的券成本口径由我先回答。"
    second_text="改为只比较right的amount变化，不再处理前两项净收益；比较范围由我选择。"
    params={"comparison_date_col":"day","comparison_dimensions":[],"comparison_formulas":{},"period_a":"2026-10-01~2026-10-07","period_b":"2026-10-08~2026-10-14","comparison_output":"comparison"}
    specs=[{"kind":"table","scope":{"datasets":["right"],"metrics":["amount"],"parameters":params}}]
    class Model(_NativeProductModel):
        phase=1;cost_asked=False;window_asked=False
        def chat(self,messages,system="",**kw):
            if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
                if self.phase==1:
                    return Response(text=encode({"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":left_goal,"business_scope":{"datasets":["left"]}},{"kind":"result","exact_span":right_goal,"business_scope":{"datasets":["right"]}}],"upload_bindings":[{"upload_id":t["upload_id"],"dataset":name,"relation":"new","exact_span":"将其命名为"+name} for t,name in zip(self.tickets,["left","right"])]}))
                declared,_=json.JSONDecoder().raw_decode(messages[-1]["content"].partition("canonical_requirements: ")[2]);active=[r for r in declared if r["lifecycle_status"]=="active"]
                left=next(r for r in active if r["business_scope"]["datasets"]==["left"]);right=next(r for r in active if r["business_scope"]["datasets"]==["right"])
                return Response(text=encode({"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":"只比较right的amount变化","op":"replace","target_id":left["id"],"business_scope":{"datasets":["right"]}},{"kind":"result","exact_span":"不再处理前两项净收益","op":"withdraw","target_id":right["id"]}]}))
            if self.phase==1 and not self.cost_asked:
                self.cost_asked=True;self.calls.append("ask_cost")
                return Response(tool_calls=[ToolCall("old_cost","ask_user_question",{"question":"净收益定义是否扣除券成本？","options":[{"label":"扣除","value":"include"},{"label":"不扣除","value":"exclude"}],"confirmation_type":"metric_scope","blocking_reason":"原业务定义未明确，回答只用于本次请求。"})])
            if self.phase==2 and not self.window_asked:
                self.window_asked=True;self.calls.append("ask_window")
                return Response(tool_calls=[ToolCall("current_window","ask_user_question",{"question":"right的amount按哪两个统计窗口比较？","options":[{"label":"10月1日至7日 对 10月8日至14日","value":"window7"},{"label":"暂不确定","value":"unknown"}],"confirmation_type":"time_window","blocking_reason":"当前比较窗口未确定。"})])
            return super().chat(messages,system=system,**kw)
    model=Model(first_text,"right","compare_periods",{"name":"right","date_col":"day","metrics":"amount","period_a":params["period_a"],"period_b":params["period_b"]},specs)
    factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    manager=factory();app=create_app();app.config["agent_manager"]=manager;sid="unbound_new_request_"+str(restart)
    raws={name:("day,amount,coupon_cost\n"+"".join(f"2026-10-{i:02d},{(10 if i<=7 else 20) if name=='left' else (30 if i<=7 else 50)},2\n" for i in range(1,15))).encode() for name in ["left","right"]}
    with app.test_client() as http:
        tickets=[http.post("/api/upload",data={"file":(io.BytesIO(raws[name]),name+".csv")},content_type="multipart/form-data").get_json() for name in ["left","right"]];model.tickets=tickets
        first=_askq_events(http.post("/api/chat",json={"session_id":sid,"message":first_text,"uploads":tickets}));old=http.get("/api/sessions/"+sid).get_json()["active_confirmation"]
        assert old and old["question"]=="净收益定义是否扣除券成本？"
        original=manager.get(sid)._confirmation_runtime().get(sid,old["confirmation_id"]);assert original.resolution_params["host_binding"]["status"]=="request_only"
        if restart:manager=factory();app.config["agent_manager"]=manager
        model.phase=2;model.content=second_text
        second=_askq_events(http.post("/api/chat",json={"session_id":sid,"message":second_text}));current=http.get("/api/sessions/"+sid).get_json()["active_confirmation"]
        assert current and current["confirmation_id"]!=old["confirmation_id"] and current["question"]=="right的amount按哪两个统计窗口比较？",second
        service=manager.get(sid)._confirmation_runtime();expired=service.get(sid,old["confirmation_id"])
        assert expired.status.value=="expired" and expired.response is None and expired.resolution_params==original.resolution_params
        fresh=service.get(sid,current["confirmation_id"]);assert fresh.resolution_params["host_binding"]["status"]=="host_bound" and set(fresh.resolution_params["host_binding"]["objects"])=={"right"}
        before=list(model.calls)
        stale=_askq_events(http.post("/api/chat/resume",json={"session_id":sid,"confirmation_id":old["confirmation_id"],"expected_version":old["version"],"idempotency_key":"old_unbound_stale","user_response":"include"}));assert model.calls==before
        if restart:manager=factory();app.config["agent_manager"]=manager
        payload={"session_id":sid,"confirmation_id":current["confirmation_id"],"expected_version":current["version"],"idempotency_key":"current_bound_once","user_response":"window7"}
        final=_askq_events(http.post("/api/chat/resume",json=payload));calls=list(model.calls);replay=_askq_events(http.post("/api/chat/resume",json=payload))
        refreshed=http.get("/api/sessions/"+sid).get_json();view=http.get("/api/sessions/"+sid+"/trust").get_json()
    saved=load_session(sid);last=next((m for m in reversed(saved["messages"]) if m.get("answer_ref")),None);assert last is not None,final
    answer=read_answer(sid,last["answer_ref"]);loop=manager.get(sid)
    for events,status in [(first,"suspended"),(second,"suspended"),(stale,"failed"),(final,"completed"),(replay,"completed")]:assert [d["status"] for e,d in events if e=="turn_end"]==[status],events
    assert model.calls==calls==["ask_cost","ask_window","describe_dataset","record_analysis_plan","compare_periods"]
    assert answer["body"]==last["content"]==next(d["reply_content"] for e,d in final if e=="turn_end")
    assert {o["requirement_id"]:o["status"] for o in answer["requirement_outcomes"]}=={r["id"]:("withdrawn" if r["withdrawn"] else "answered") for r in answer["source_snapshot"]["requirements"]}
    assert len(answer["source_snapshot"]["requirements"])==3 and sum(r["withdrawn"] for r in answer["source_snapshot"]["requirements"])==2
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"};values=[c["value"] for c in answer["source_snapshot"]["claims"] if c["id"] in accepted]
    assert len(values)==1 and values[0]["amount"]["exact_aggregates"]=={"period_a":210.0,"period_b":350.0,"diff":140.0}
    assert len([m for m in refreshed["messages"] if m.get("answer_ref")==last["answer_ref"]])==1 and refreshed["active_confirmation"] is None
    _s3_assert_workbench_uses_original_accepted_parts(view,answer)
    with use_agent_context(loop.context):
        identity=loop.context.workspace._publication_data_identity("right");exported=export_assistant_reply(sid,answer["body"],"md",reply_id=last["reply_id"])
    assert identity["source_origins"][0]["file_sha256"]==tickets[1]["sha256"]=="sha256:"+hashlib.sha256(raws["right"]).hexdigest()
    assert tickets[0]["sha256"]!=tickets[1]["sha256"] and exported["status"]=="exported"
    md=(cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes();assert answer["body"] in md.decode("utf-8").replace("\r\n","\n")
    out=Path(os.environ.get("DATA_AGENT_S3_ASK_EVIDENCE",str(cfg.sessions_resolved/"evidence")));out.mkdir(parents=True,exist_ok=True);stem="normal_unbound_new_request_"+str(restart)
    (out/(stem+".json")).write_text(json.dumps({"raw_hex":{n:r.hex() for n,r in raws.items()},"tickets":tickets,"first_text":first_text,"second_text":second_text,"first":first,"old":old,"original":original.to_dict(),"second":second,"current":current,"expired":expired.to_dict(),"fresh":fresh.to_dict(),"stale":stale,"final":final,"replay":replay,"answer":answer,"saved":saved,"refreshed":refreshed,"view":view,"identity":identity,"state":loop.context.analysis_state.to_dict(),"calls":calls,"provider_calls":0},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    (out/(stem+".md")).write_bytes(md)


@pytest.mark.parametrize("injected", [False, True])
def test_s3_q12_normal_fixed_rows_model_dependency_claim_does_not_suspend(engine,injected):
    import os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.llm.client import Response,ToolCall
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    content="加载附件将其命名为experiment，仅计算全表记录数，不筛选时间，不计算窗口指标。"
    scope={"datasets":["experiment"],"quantity":"rows"}
    specs=[{"kind":"measurement","scope":scope}]
    child={"question":"所有操作都必须先选近7天或近30天窗口？", "confirmation_type":"time_window",
           "options":[{"label":"近7天","value":"window7"},{"label":"近30天","value":"window30"}],
           "dataset_ref":"another_session/private","affected_operations":["*"],"blocked_surfaces":["*"]}
    class Model(_NativeProductModel):
        asked=False
        def chat(self,messages,system="",**kw):
            if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
                return Response(text=encode({"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":content,"business_scope":scope}],"upload_bindings":[{"upload_id":self.ticket["upload_id"],"dataset":"experiment","relation":"new","exact_span":"将其命名为experiment"}]}))
            if self.step==0:
                self.step=1;self.calls.append("quick_profile")
                return Response(tool_calls=[ToolCall("q12_profile","quick_profile",{"name":"experiment"})])
            if injected and self.step==2 and not self.asked:
                self.asked=True;self.calls.append("ask_user_question")
                return Response(tool_calls=[ToolCall("q12_claimed_dependency","ask_user_question",{"questions":json.dumps([child],ensure_ascii=False),"confirmation_type":"metric_scope"})])
            return super().chat(messages,system=system,**kw)
    model=Model(content,"experiment","describe_dataset",{"name":"experiment"},specs)
    manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    app=create_app();app.config["agent_manager"]=manager;sid="q12_rows_"+str(injected)
    raw=b"day,amount\n2026-10-01,10\n2026-10-08,20\n2026-10-14,30\n"
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"experiment.csv")},content_type="multipart/form-data").get_json();model.ticket=ticket
        events=_askq_events(http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]}))
        refreshed=http.get("/api/sessions/"+sid).get_json();view=http.get("/api/sessions/"+sid+"/trust").get_json()
    saved=load_session(sid);last=next((m for m in reversed(saved["messages"]) if m.get("answer_ref")),None);answer=read_answer(sid,last["answer_ref"]) if last else None
    loop=manager.get(sid);records=loop._confirmation_runtime()._store(sid).load_records()
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"]);stem="q12_normal_rows_"+str(injected)
    captured={"raw_hex":raw.hex(),"ticket":ticket,"input":child if injected else None,"events":events,"saved":saved,"refreshed":refreshed,"view":view,"answer":answer,"records":{k:r.to_dict() for k,r in records.items()},"state":loop.context.analysis_state.to_dict(),"calls":model.calls,"provider_calls":0}
    (out/(stem+".json")).write_text(json.dumps(captured,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    assert [d["status"] for e,d in events if e=="turn_end"]==["completed"],"A model-claimed window dependency must not block the user's explicit full-table count."
    assert answer is not None and all(r["status"]=="answered" for r in answer["requirement_outcomes"])
    assert refreshed["active_confirmation"] is None
    accepted={t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    assert [c["value"] for c in answer["source_snapshot"]["claims"] if c["id"] in accepted]==[3]
    assert model.calls==["quick_profile","record_analysis_plan"]+(["ask_user_question"] if injected else [])+["describe_dataset"]
    _s3_assert_workbench_uses_original_accepted_parts(view,answer)
    with use_agent_context(loop.context):exported=export_assistant_reply(sid,answer["body"],"md",reply_id=last["reply_id"])
    assert exported["status"]=="exported"
    md=(cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes();assert answer["body"] in md.decode("utf-8").replace("\r\n","\n")
    (out/(stem+".md")).write_bytes(md)


@pytest.mark.parametrize("restart",[False,True])
@pytest.mark.parametrize("mode",["zero_version","old_version","future_version","conflict_same_key","conflict_new_key","write_before_applying","write_after_resolved","legacy_collision"])
def test_s3_r07_normal_http_conflict_old_version_and_recovery_fault(engine,monkeypatch,restart,mode):
    import os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.llm.client import Response
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.agent.confirmation.actions import ResolutionActionRegistry
    _,cfg=engine
    content="加载上传数据并将其命名为experiment，比较amount的变化；由我选择比较范围。"
    params={"comparison_date_col":"day","comparison_dimensions":[],"comparison_formulas":{},"period_a":"2026-10-01~2026-10-07","period_b":"2026-10-08~2026-10-14","comparison_output":"comparison"}
    specs=[{"kind":"table","scope":{"datasets":["experiment"],"metrics":["amount"],"parameters":params}}]
    model=_NativeProductModel(content,"experiment","compare_periods",{"name":"experiment","date_col":"day","metrics":"amount","period_a":params["period_a"],"period_b":params["period_b"]},specs)
    factory=lambda:AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model)
    manager=factory();app=create_app();app.config["agent_manager"]=manager
    sid=f"r07_http_{mode}_{restart}";raw=("day,amount\n"+"".join(f"2026-10-{i:02d},{10 if i<=7 else 20}\n" for i in range(1,15))).encode()
    out=Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"]);stem=f"r07_normal_{mode}_{restart}";capture={"mode":mode,"restart":restart,"raw_hex":raw.hex(),"provider_calls":0}
    action_calls=[];apply=ResolutionActionRegistry.apply
    def observed_apply(self,name,context,answer,resolution_id):
        if context.session_id==sid:action_calls.append({"action":name,"answer":answer,"resolution_id":resolution_id})
        return apply(self,name,context,answer,resolution_id)
    monkeypatch.setattr(ResolutionActionRegistry,"apply",observed_apply)
    def save():
        capture.update(saved=load_session(sid),calls=list(model.calls),action_calls=list(action_calls))
        (out/(stem+".json")).write_text(json.dumps(capture,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    def payload(active,key="answer_once",response="last_7_vs_previous_7"):
        return {"session_id":sid,"confirmation_id":active["confirmation_id"],"expected_version":active["version"],"idempotency_key":key,"user_response":response}
    with app.test_client() as http:
        ticket=http.post("/api/upload",data={"file":(io.BytesIO(raw),"experiment.csv")},content_type="multipart/form-data").get_json();model.ticket=ticket;capture["ticket"]=ticket
        first=_askq_events(http.post("/api/chat",json={"session_id":sid,"message":content,"uploads":[ticket]}));capture["first"]=first
        active=http.get("/api/sessions/"+sid).get_json()["active_confirmation"];assert active,first
        loop=manager.get(sid);record=loop._confirmation_runtime().get(sid,active["confirmation_id"]);capture["original_record"]=record.to_dict()
        assert record.source=="question_need_detector", "this positive control must use the actual automatic producer"
        events_path=cfg.sessions_resolved/sid/"confirmations/events.jsonl"
        before=events_path.read_bytes();calls_before=list(model.calls)
        if restart:manager=factory();app.config["agent_manager"]=manager
        if mode.startswith("conflict") or mode=="legacy_collision":
            completed=_askq_events(http.post("/api/chat/resume",json=payload(active)));capture["completed"]=completed
            original_saved=load_session(sid);accepted=next(m for m in reversed(original_saved["messages"]) if m.get("answer_ref"));original_answer=read_answer(sid,accepted["answer_ref"])
            before=events_path.read_bytes();calls_before=list(model.calls);action_before=list(action_calls)
            bad=payload(active,"answer_once" if mode=="conflict_same_key" else "different_key","last_30_vs_previous_30")
        elif mode.endswith("version"):
            bad=payload(active,"stale_answer")
            bad["expected_version"]={"zero_version":0,"old_version":active["version"]-1,"future_version":active["version"]+1}[mode]
            action_before=list(action_calls)
        else:
            append=ConfirmationStore.append;fired=[]
            target="applying" if mode=="write_before_applying" else "resolved"
            def injected(store,event):
                if store.session_id==sid and event.event_type==target and not fired:
                    fired.append(event.event_id)
                    if mode=="write_after_resolved":append(store,event)
                    raise OSError("original confirmation event write failure "+mode)
                return append(store,event)
            monkeypatch.setattr(ConfirmationStore,"append",injected);bad=payload(active);action_before=list(action_calls)
        rejected=_askq_events(http.post("/api/chat/resume",json=bad));capture["rejected"]=rejected
        if mode.startswith("write_"):monkeypatch.setattr(ConfirmationStore,"append",append)
        capture["record_after_rejected"]=manager.get(sid)._confirmation_runtime().get(sid,active["confirmation_id"]).to_dict();capture["before_events_hex"]=before.hex();capture["after_rejected_events_hex"]=events_path.read_bytes().hex();save()
        assert [d["status"] for e,d in rejected if e=="turn_end"]==["failed"], "A stale/conflicting/faulted response cannot report completed."
        assert model.calls==calls_before
        if not mode.startswith("write_"):
            assert action_calls==action_before and events_path.read_bytes()==before
        if mode.startswith("conflict") or mode=="legacy_collision":
            conflict_history=load_session(sid)["messages"]
            assert conflict_history[:len(original_saved["messages"])]==original_saved["messages"]
            assert len(conflict_history)==len(original_saved["messages"])+1
            assert "执行失败" in conflict_history[-1]["content"] and not conflict_history[-1].get("answer_ref")
            assert read_answer(sid,accepted["answer_ref"])==original_answer
            assert conflict_history[-1]["reply_id"]!=accepted["reply_id"], "A failed execution notice must not share the original AcceptedAnswer reply identity."
        if mode=="legacy_collision":
            from data_agent.session.history import save_session,load_canonical_history
            legacy=deepcopy(load_session(sid)["messages"]);legacy[-1]["reply_id"]=accepted["reply_id"]
            save_session(legacy,session_id=sid)
            manager.get(sid).messages=deepcopy(legacy)
            frozen=load_canonical_history(sid)
            capture["historical_before"]={"messages":frozen.messages,"sha256":frozen.sha256}
            history_files={p.name:p.read_bytes().hex() for p in (cfg.sessions_resolved/sid).glob("conversation.*")}
            capture["historical_files_before"]=history_files
            capture["original_answer_bytes"]=(cfg.sessions_resolved/sid/accepted["answer_ref"]["path"]).read_bytes().hex()
            capture["historical_events_before"]=events_path.read_bytes().hex()
            projected=http.get("/api/sessions/"+sid).get_json();capture["historical_projection"]=projected;save()
            assert load_canonical_history(sid).sha256==frozen.sha256
            assert projected["messages"][-1]["reply_id"]!=accepted["reply_id"] and projected["messages"][-1]["reply_id"].startswith("legacy_")
        if restart:manager=factory();app.config["agent_manager"]=manager
        resumed=_askq_events(http.post("/api/chat/resume",json=payload(active)));capture["resumed"]=resumed;save()
        if mode=="write_before_applying":
            assert [d["status"] for e,d in resumed if e=="turn_end"]==["failed"]
            assert not action_calls and model.calls==calls_before
            assert not manager.get(sid).context.analysis_state.accepted_answers
            assert manager.get(sid)._confirmation_runtime().get(sid,active["confirmation_id"]).status.value=="response_received"
            capture["recovery_scope"]="fail-closed orphan preserved; automatic completion is not assessed";save();return
        assert [d["status"] for e,d in resumed if e=="turn_end"]==["completed"],resumed
        calls=list(model.calls);actions=list(action_calls);history=load_session(sid)
        replay=_askq_events(http.post("/api/chat/resume",json=payload(active)));capture["replay"]=replay
        refreshed=http.get("/api/sessions/"+sid).get_json();view=http.get("/api/sessions/"+sid+"/trust").get_json()
    saved=load_session(sid);last=next(m for m in reversed(saved["messages"]) if m.get("answer_ref"));answer=read_answer(sid,last["answer_ref"]);loop=manager.get(sid)
    assert [d["status"] for e,d in replay if e=="turn_end"]==["completed"]
    assert model.calls==calls and action_calls==actions and len(actions)==1 and model.calls.count("compare_periods")==1
    assert saved["messages"]==history["messages"] and len(loop.context.analysis_state.accepted_answers)==1
    assert refreshed["active_confirmation"] is None
    assert answer["body"]==last["content"] and all(o["status"]=="answered" for o in answer["requirement_outcomes"])
    _s3_assert_workbench_uses_original_accepted_parts(view,answer)
    for sequence in (resumed,replay):
        terminal=next(d for e,d in sequence if e=="turn_end")
        assert terminal["reply_id"]==last["reply_id"] and terminal["reply_content"]==answer["body"]
    with use_agent_context(loop.context):
        identity=loop.context.workspace._publication_data_identity("experiment")
        exported=export_assistant_reply(sid,answer["body"],"md",reply_id=last["reply_id"])
    capture["exported"]=exported;save()
    assert exported.get("status")=="exported",exported
    md=(cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes();assert answer["body"] in md.decode("utf-8").replace("\r\n","\n")
    capture.update(answer=answer,refreshed=refreshed,view=view,state=loop.context.analysis_state.to_dict(),identity=identity,record=loop._confirmation_runtime().get(sid,active["confirmation_id"]).to_dict(),after_events_hex=events_path.read_bytes().hex());save();(out/(stem+".md")).write_bytes(md)
    if mode=="legacy_collision":
        current=load_canonical_history(sid)
        capture["historical_after"]={"messages":current.messages,"sha256":current.sha256}
        capture["historical_files_after"]={p.name:p.read_bytes().hex() for p in (cfg.sessions_resolved/sid).glob("conversation.*")}
        save()
        assert capture["historical_after"]==capture["historical_before"]
        assert capture["historical_files_after"]==capture["historical_files_before"]
        assert saved["messages"][-1]["reply_id"]==last["reply_id"]
        assert refreshed["messages"][-1]["reply_id"]==capture["historical_projection"]["messages"][-1]["reply_id"]
        assert events_path.read_bytes().hex()==capture["historical_events_before"]
        assert (cfg.sessions_resolved/sid/last["answer_ref"]["path"]).read_bytes().hex()==capture["original_answer_bytes"]


@pytest.mark.parametrize("case", ["material", "unrelated_rows", "unrelated_profit", "missing_original"])
def test_s3_q12_real_cleaning_producer_normal_original_answer(engine, monkeypatch, case):
    import io, os
    from pathlib import Path
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.llm.client import Response, ToolCall
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.tools.report import export_assistant_reply
    import data_agent.tools.data_io as producer
    _, cfg = engine
    record = producer._record_trust_workflow
    produced = []
    def actual_producer(**kwargs):
        kwargs["needs_confirm"] = [*kwargs["needs_confirm"], {"column":"amount", "action":"ambiguous_numeric",
            "requires_confirmation":True, "reason":"The amount scale needs a business choice."}]
        result = record(**kwargs)
        state = kwargs["state"]
        produced.append(deepcopy(state.cleaning_logs[-1]))
        if case == "missing_original":
            state.cleaning_logs[-1]["artifact_path"] = str(cfg.sessions_resolved / kwargs["session_id"] / "tool_outputs" / "unavailable-original.json")
            state.save()
        return result
    monkeypatch.setattr(producer, "_record_trust_workflow", actual_producer)
    metric = "profit" if case == "unrelated_profit" else "amount"
    params = {"comparison_date_col":"day", "comparison_dimensions":[], "comparison_formulas":{},
        "period_a":"2026-10-01~2026-10-07", "period_b":"2026-10-08~2026-10-14", "comparison_output":"comparison"}
    scope = {"datasets":["experiment"], "quantity":"rows"} if case == "unrelated_rows" else {
        "datasets":["experiment"], "metrics":[metric], "parameters":params}
    specs = [{"kind":"measurement" if case == "unrelated_rows" else "table", "scope":scope}]
    content = ("加载附件将其命名为experiment，仅计算全表记录数。" if case == "unrelated_rows" else
        "加载附件将其命名为experiment，比较"+metric+"在2026-10-01至2026-10-07与2026-10-08至2026-10-14的真实合计与差值。")
    tool = "describe_dataset" if case == "unrelated_rows" else "compare_periods"
    args = {"name":"experiment"} if case == "unrelated_rows" else {"name":"experiment", "date_col":"day", "metrics":metric,
        "period_a":params["period_a"], "period_b":params["period_b"]}
    class Model(_NativeProductModel):
        def chat(self, messages, system="", **kw):
            if system == "你是一个JSON输出器，只返回JSON，不要其他内容。":
                return Response(text=encode({"intent_type":"directed_analysis", "requested_outputs":[{
                    "kind":"result", "exact_span":content, "business_scope":scope}], "upload_bindings":[{
                    "upload_id":self.ticket["upload_id"], "dataset":"experiment", "relation":"new", "exact_span":"将其命名为experiment"}]}))
            if self.step == 0:
                self.step = 1
                self.calls.append("quick_profile")
                return Response(tool_calls=[ToolCall("producer_profile", "quick_profile", {"name":"experiment"})])
            return super().chat(messages, system=system, **kw)
    model = Model(content, "experiment", tool, args, specs)
    manager = AgentManager(client_factory=lambda **kw:model, auxiliary_client_factory=lambda:model)
    app = create_app(); app.config["agent_manager"] = manager
    sid = "q12_actual_producer_"+case
    raw = ("day,amount,profit\n"+"".join(f"2026-10-{i:02d},{10 if i<=7 else 20},{i}\n" for i in range(1,15))).encode()
    with app.test_client() as http:
        ticket = http.post("/api/upload", data={"file":(io.BytesIO(raw), "experiment.csv")}, content_type="multipart/form-data").get_json()
        model.ticket = ticket
        first = _askq_events(http.post("/api/chat", json={"session_id":sid, "message":content, "uploads":[ticket]}))
        active = http.get("/api/sessions/"+sid).get_json()["active_confirmation"]
        if case == "material":
            assert [d["status"] for e,d in first if e=="turn_end"] == ["suspended"], first
            assert active and "amount" in active["question"], active
            final = _askq_events(http.post("/api/chat/resume", json={"session_id":sid, "confirmation_id":active["confirmation_id"],
                "expected_version":active["version"], "idempotency_key":"amount_original_once", "user_response":"amount按元，保持当前数值"}))
        else:
            assert active is None, first
            final = first
        refreshed = http.get("/api/sessions/"+sid).get_json()
    saved = load_session(sid)
    last = next((m for m in reversed(saved["messages"]) if m.get("answer_ref")), None)
    answer = read_answer(sid, last["answer_ref"]) if last else None
    out = Path(os.environ["DATA_AGENT_S3_ASK_EVIDENCE"])
    (out/("q12_actual_producer_"+case+".json")).write_text(json.dumps({"case":case,"raw_sha256":hashlib.sha256(raw).hexdigest(),
        "produced":produced,"first":first,"final":final,"refreshed":refreshed,"saved":saved,"answer":answer,"calls":model.calls,"provider_calls":0},
        ensure_ascii=False,indent=2,default=str), encoding="utf-8")
    assert [d["status"] for e,d in final if e=="turn_end"] == ["completed"], final
    assert produced and all(r.get("source_binding") for r in produced)
    assert answer and answer["body"] == last["content"] == next(d["reply_content"] for e,d in final if e=="turn_end")
    assert len([m for m in refreshed["messages"] if m.get("answer_ref")==last["answer_ref"]]) == 1
    accepted = {t["ref"] for t in answer["render_trace"] if t["kind"]=="claim" and t["disposition"]=="accepted"}
    claims = [c for c in answer["source_snapshot"]["claims"] if c["id"] in accepted]
    if case == "missing_original":
        assert not claims and answer["requirement_outcomes"][0]["status"] == "evidence_insufficient", answer
    else:
        assert all(r["status"] == "answered" for r in answer["requirement_outcomes"]), answer
        if case == "unrelated_rows": assert [c["value"] for c in claims] == [14]
        else:
            assert len(claims) == 1
            assert claims[0]["value"][metric]["exact_aggregates"] == {
                "period_a":28.0 if metric=="profit" else 70.0, "period_b":77.0 if metric=="profit" else 140.0, "diff":49.0 if metric=="profit" else 70.0}
    loop = manager.get(sid)
    with use_agent_context(loop.context):
        exported = export_assistant_reply(sid, answer["body"], "md", reply_id=last["reply_id"])
    assert exported["status"] == "exported"
    md = (cfg.sessions_resolved/sid/"reports"/exported["artifact_path"].split("/")[-1]).read_bytes()
    assert answer["body"] in md.decode("utf-8").replace("\r\n","\n")
    (out/("q12_actual_producer_"+case+".md")).write_bytes(md)


@pytest.mark.parametrize("restart",[False,True])
def test_s3_normal_q12_mixed_mapping_r09_concurrent_card_resume_actual_answer(engine,restart):
    import io,hashlib,os
    from pathlib import Path
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context
    from threading import Barrier
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.session.history import load_session
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.agent.context import use_agent_context
    from data_agent.agent.loop import UserConfirmationRequired,SuspendedForConfirmation
    from data_agent.tools.report import export_assistant_reply
    _,cfg=engine
    content="分析上传数据，将其命名为comparison，计算前后两个窗口amount的差值，由我确认窗口。"
    args={"name":"comparison","date_col":"day","metrics":"amount","period_a":"2026-09-01~2026-09-06","period_b":"2026-09-07~2026-09-12"}
    question={"question":"前后窗口是否采用所列六天范围？","confirmation_type":"time_window","options":[{"label":"前期9月1—6日，后期9月7—12日","value":"split6"},{"label":"另行指定窗口","value":"custom"}]}
    mapping={"exact_span":"amount的差值","dataset":"comparison","column":"amount"}
    ask={"questions":encode([question]),"measurement_mapping":encode(mapping)}
    scope={"datasets":["comparison"],"metrics":["amount"],"quantity":"difference"}
    script=_NativeProductModel(content,"comparison","compare_periods",args,[{"kind":"measurement","scope":scope}],preparatory_calls=[("ask_user_question",ask)])
    manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app=create_app();app.config["agent_manager"]=manager
    raw=pd.DataFrame({"day":pd.date_range("2026-09-01",periods=12),"amount":[10]*6+[20]*6}).to_csv(index=False).encode();sid="s3_normal_q12_r09_"+str(restart)
    def events(response):return [(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
    with app.test_client() as http:
        ticket=http.post('/api/upload',data={"file":(io.BytesIO(raw),'comparison.csv')},content_type='multipart/form-data').get_json();script.ticket=ticket
        assert ticket['sha256']=='sha256:'+hashlib.sha256(raw).hexdigest()
        first=events(http.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]}));loop=manager.get(sid);service=loop._confirmation_runtime();active=service.checkpoint(sid)
        out=Path(os.environ['DATA_AGENT_S3_ASK_EVIDENCE']);(out/('normal_q12_r09_first_'+str(restart)+'.json')).write_text(json.dumps({'first':first,'active':active.to_dict() if active else None,'provider_calls':0},ensure_ascii=False,indent=2),encoding='utf-8')
        assert len([d for e,d in first if e=='turn_end' and d['status']=='suspended'])==1 and active is not None
        assert len(json.loads(active.resolution_params['context']))==1 and 'measurement_mapping' not in active.resolution_params
        barrier=Barrier(2)
        def arrive(index):
            with use_agent_context(loop.context):
                barrier.wait(timeout=10)
                return loop._suspend_for_confirmation_request(UserConfirmationRequired(question=question['question'],options=[],context=ask['questions'],measurement_mapping=ask['measurement_mapping']),turn_id='arrival_'+str(index))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(copy_context().run,arrive,index) for index in range(2)];same=[f.result(timeout=20) for f in futures]
        assert all(isinstance(r,SuspendedForConfirmation) and r.confirmation_id==active.confirmation_id for r in same)
        assert len(service._store(sid).load_records())==1
        visible=json.loads(same[0].context);answer_text=encode([{'question_id':visible[0]['question_id'],'question':question['question'],'answer':'split6','is_free_input':False}])
        if restart:
            manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app.config['agent_manager']=manager
        final=events(http.post('/api/chat/resume',json={'session_id':sid,'confirmation_id':active.confirmation_id,'user_response':answer_text,'expected_version':active.version,'idempotency_key':'q12_r09_once'}));refreshed=http.get('/api/sessions/'+sid).get_json()
    ends=[d for e,d in final if e=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed',final
    body=''.join(d['text'] for e,d in final if e=='text_delta');saved=load_session(sid);owner=next(m for m in reversed(saved['messages']) if m.get('answer_ref'));answer=read_answer(sid,owner['answer_ref'])
    assert body==ends[0]['reply_content']==answer['body']==owner['content']
    assert next(m for m in refreshed['messages'] if m.get('answer_ref')==owner['answer_ref'])['content']==body
    accepted={t['ref'] for t in answer['render_trace'] if t['kind']=='claim' and t['disposition']=='accepted'}
    claimed=[c for c in answer['source_snapshot']['claims'] if c['id'] in accepted]
    assert answer['requirement_outcomes'][0]['status']=='answered' and len(claimed)==1
    assert claimed[0]['label']=='amount：差值' and claimed[0]['value']==60
    assert script.calls==['describe_dataset','record_analysis_plan','ask_user_question','compare_periods']
    exported=export_assistant_reply(sid,body,'md',reply_id=owner['reply_id']);assert exported['status']=='exported';md=(cfg.sessions_resolved/sid/'reports'/exported['artifact_path'].split('/')[-1]).read_text(encoding='utf-8');assert body in md
    (out/('normal_q12_r09_'+str(restart)+'.json')).write_text(json.dumps({'raw_hex':raw.hex(),'ticket':ticket,'first':first,'final':final,'answer':answer,'saved':saved,'refreshed':refreshed,'calls':script.calls,'record':service.get(sid,active.confirmation_id).to_dict(),'provider_calls':0},ensure_ascii=False,indent=2),encoding='utf-8');(out/('normal_q12_r09_'+str(restart)+'.md')).write_text(md,encoding='utf-8')

