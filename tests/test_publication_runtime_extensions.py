from tests.test_trusted_publication_semantics import engine
"""Publication contract tests: extensions. Shared fixtures have one owner."""
from copy import deepcopy
from data_agent.agent.publication.contracts import encode
from data_agent.mcp.bridge import MCPToolBridge
from data_agent.mcp.client import MCPClientManager
from data_agent.mcp.client import MCPConnection
from data_agent.mcp.config import MCPConfig
from data_agent.mcp.config import MCPServerConfig
from data_agent.mcp.config import load_mcp_config
from data_agent.mcp.config import save_mcp_config
from data_agent.mcp.models import MCPToolDef
from data_agent.session.history import load_session
from data_agent.session.history import save_session
from data_agent.tools.registry import ToolRegistry
from data_agent.tools.registry import registry
from pathlib import Path
from tests.test_trusted_publication_native_families import _operation_spec
from tests.test_trusted_publication_semantics import execute
from types import SimpleNamespace
import asyncio
import builtins
import hashlib
import io
import json
import pytest
from tests.support.publication_runtime import _NativeProductModel, draft, request

_SKILLS_CATALOG_OUT=Path('tmp/s3-skills-catalog-20261013-r1')


_SKILLS_CATALOG_CASE_OUT=_SKILLS_CATALOG_OUT


def _setup_skills_catalog(engine,tmp_path,monkeypatch,empty):
 import data_agent.agent.loop as module
 import data_agent.config_resolver as resolver
 from data_agent.skills.loader import SkillLoader
 root=tmp_path/'skills_fixture';root.mkdir()
 if not empty:
  for name,enabled in [('catalog_on',True),('catalog_off',False)]:
   f=root/name/'SKILL.md';f.parent.mkdir();f.write_text('---\nname: '+name+'\ndescription: Catalogue fixture\nenabled: '+str(enabled).lower()+'\n---\nFixture reference only.',encoding='utf-8')
 owner=SkillLoader(root);owner.discover();monkeypatch.setattr(engine[0],'_skill_loader',owner.for_session(engine[0].session_id));monkeypatch.setattr(module,'_skill_loader',owner);monkeypatch.setattr(resolver,'resolve_skills_dirs',lambda:[root]);return owner,root


def _capture_skills_catalog(name,value):
 _SKILLS_CATALOG_CASE_OUT.mkdir(parents=True,exist_ok=True)
 with (_SKILLS_CATALOG_CASE_OUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)


@pytest.mark.parametrize('empty',[False,True])
@pytest.mark.parametrize('route',['store','registry'])
def test_actual_skill_catalogue_can_be_empty_without_missing_data(engine,tmp_path,monkeypatch,empty,route):
 owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,empty);monkeypatch.setitem(globals(),'_SKILLS_CATALOG_CASE_OUT',_SKILLS_CATALOG_OUT/'evidence'/engine[1].sessions_resolved.parents[1].name)
 if route=='store':result={'skills':[{'name':s.name,'enabled':s.enabled} for s in owner.list_available()]}
 else:result=json.loads(registry.execute('list_skills',{}).summary)
 _capture_skills_catalog(route+'_'+str(empty)+'.json',{'root':str(root),'result':result,'provider_calls':0})
 assert len(result['skills'])==(0 if empty else 2)


@pytest.mark.parametrize('empty',[False,True])
def test_normal_standalone_skill_catalogue_delivers_actual_scope(engine,tmp_path,monkeypatch,empty):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 _,cfg=engine;owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,empty);monkeypatch.setitem(globals(),'_SKILLS_CATALOG_CASE_OUT',_SKILLS_CATALOG_OUT/'evidence'/engine[1].sessions_resolved.parents[1].name);sid='skills_catalog_'+str(empty)
 content='只列出当前全局安装的Skills名称、说明、启用状态及本会话加载状态；空目录也如实列出，不需要数据文件。'
 script=_NativeProductModel(content,'','list_skills',{},[{'kind':'table','scope':{'parameters':{'catalog_scope':'current_visible','catalog_output':'skills'}}}]);manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app=create_app();app.config['agent_manager']=manager
 with app.test_client() as http:
  response=http.post('/api/chat',json={'session_id':sid,'message':content});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refreshed=http.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);answer=read_answer(sid,saved['messages'][-1]['answer_ref']) if saved['messages'][-1].get('answer_ref') else None
 _capture_skills_catalog('normal_'+str(empty)+'.json',{'root':str(root),'events':events,'answer':answer,'saved':saved,'refreshed':refreshed,'calls':script.calls,'session_dir':str(cfg.sessions_resolved/sid),'files':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()},'provider_calls':0})
 assert answer is not None and answer['requirement_outcomes'][0]['status']=='answered'
 assert answer['source_snapshot']['data_identities']=={} and len(answer['source_snapshot']['claims'])==1
 assert answer['source_snapshot']['claims'][0]['value']==([] if empty else json.loads(next(d['web']['summary'] for e,d in events if e=='tool_result' and d['name']=='list_skills'))['skills'])
 assert '单位未知' not in answer['body'] and (not empty or '0项' in answer['body'])
 from data_agent.tools.report import export_assistant_reply
 export=export_assistant_reply(sid,answer['body'],'md');assert export['status']=='exported'
 md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8');(_SKILLS_CATALOG_CASE_OUT/('normal_'+str(empty)+'.md')).write_bytes(md.read_bytes())


def _skills_catalog_spec():
 return {'kind':'table','scope':{'parameters':{'catalog_scope':'current_visible','catalog_output':'skills'}}}


@pytest.mark.parametrize('fault',['result','missing_binding','session','permission','directories','file_sha','snapshot_sha','arguments','source','add_source','remove_source','loaded','configuration','cache'])
def test_skills_catalog_rejects_tampered_result_source_configuration_and_loading(engine,tmp_path,monkeypatch,fault):
 from data_agent.agent.publication.native import resolve_native_claims
 from tests.test_r3_comparison_host_claims import _tamper
 import data_agent.config_resolver as resolver
 loop,cfg=engine;owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,False);rid,result=execute(loop,'list_skills',{});receipt=loop.context.analysis_state.tool_receipts[-1]
 if fault=='result':result['skills'][0]['enabled']=not result['skills'][0]['enabled'];_tamper(loop,cfg,rid,result)
 elif fault=='missing_binding':receipt.pop('skills_binding')
 elif fault in {'session','permission','directories','file_sha','snapshot_sha'}:
  binding=receipt['skills_binding']
  if fault=='session':binding['session_id']='another_session'
  elif fault=='permission':binding['permission_scope']='another_permission'
  elif fault=='directories':binding['directories'][0]['path']=str(tmp_path/'another')
  elif fault=='file_sha':binding['files'][0]['sha256']='sha256:'+'0'*64
  else:binding['snapshot_sha256']='sha256:'+'0'*64
 elif fault=='arguments':receipt['arguments']={'name':'catalog_on'}
 elif fault=='source':(root/'catalog_on/SKILL.md').write_text('changed source',encoding='utf-8')
 elif fault=='add_source':p=root/'new/SKILL.md';p.parent.mkdir();p.write_text('new source',encoding='utf-8')
 elif fault=='remove_source':(root/'catalog_on/SKILL.md').unlink()
 elif fault=='loaded':loop._skill_loader.load('catalog_on')
 elif fault=='configuration':monkeypatch.setattr(resolver,'resolve_skills_dirs',lambda:[tmp_path/'another'])
 else:owner.get('catalog_on').description='stale cache override'
 with pytest.raises((ValueError,OSError)):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize('fault',['source','loaded','rebound_receipt'])
def test_skills_catalog_commit_rechecks_original_binding_after_render(engine,tmp_path,monkeypatch,fault):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
 from data_agent.tools.skill_tools import _skills_catalog_snapshot
 loop,cfg=engine;owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,False);request(loop,'列出当前Skills目录',_skills_catalog_spec());execute(loop,'list_skills',{});snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None and loop._accepted_answer['requirement_outcomes'][0]['status']=='answered'
 if fault=='loaded':loop._skill_loader.load('catalog_on')
 else:
  p=root/'catalog_on/SKILL.md';p.write_text(p.read_text(encoding='utf-8')+'\nChanged instructions.',encoding='utf-8')
  if fault=='rebound_receipt':owner.discover();loop.context.analysis_state.tool_receipts[-1]['skills_binding']=_skills_catalog_snapshot(loop.context)[1]
 assert commit(loop,{'role':'assistant'},body) and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize('change',['other_session_loading','unrelated_dataset'])
def test_skills_catalog_unrelated_state_does_not_invalidate_bound_catalogue(engine,tmp_path,monkeypatch,change):
 from data_agent.agent.publication.native import resolve_native_claims
 import pandas as pd
 loop,cfg=engine;owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,False);rid,result=execute(loop,'list_skills',{});other=owner.for_session('other_session')
 if change=='other_session_loading':other.load('catalog_on')
 else:loop.context.workspace.add('unrelated',pd.DataFrame({'x':[99]}))
 claims=resolve_native_claims(session_id=loop.session_id,receipt_id=rid);assert len(claims)==1 and claims[0]['value']==result['skills'] and claims[0]['basis_refs'][0]['data_identities']=={}


def test_skills_catalog_loaded_state_is_current_session_only(engine,tmp_path,monkeypatch):
 from data_agent.tools.skill_tools import list_skills
 loop,cfg=engine;owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,False);first=loop._skill_loader;other=owner.for_session('other');other.load('catalog_on')
 assert all(not r['loaded'] for r in json.loads(list_skills())['skills']);first.load('catalog_on');result=json.loads(list_skills())
 assert next(r for r in result['skills'] if r['name']=='catalog_on')['loaded'] and not next(r for r in result['skills'] if r['name']=='catalog_off')['loaded']


@pytest.mark.parametrize('kind',['measurement','forecast','chart','fit','series','scenario'])
def test_skills_catalog_cannot_borrow_dataset_or_method_authority(kind):
 from data_agent.agent.analysis_plan_contracts import delivery_schema
 from jsonschema import Draft7Validator
 value=_skills_catalog_spec();value['kind']=kind
 if kind=='measurement':value['scope']['quantity']='count'
 assert list(Draft7Validator(delivery_schema()).iter_errors(dict(value,requirement_id='rq',label='wrong kind')))


@pytest.mark.parametrize('fault',['datasets','metrics','quantity','no_scope','wrong_scope','wrong_output'])
def test_skills_catalog_scope_requires_exact_metadata_only_boundary(fault):
 from data_agent.agent.publication.deliveries import validate_business_scope
 scope=_skills_catalog_spec()['scope']
 if fault=='datasets':scope['datasets']=['orders']
 elif fault=='metrics':scope['metrics']=['amount']
 elif fault=='quantity':scope['quantity']='mean'
 elif fault=='no_scope':scope['parameters'].pop('catalog_scope')
 elif fault=='wrong_scope':scope['parameters']['catalog_scope']='all_system_files'
 else:scope['parameters']['catalog_output']='unknown_catalogue'
 with pytest.raises(ValueError):validate_business_scope(scope,required=True,metadata=True)


@pytest.mark.parametrize('fault',['read_denied','parse_failure','stale_cache'])
def test_skills_catalog_unreadable_or_unverified_source_is_not_empty_success(engine,tmp_path,monkeypatch,fault):
 from data_agent.tools.skill_tools import list_skills,_capture_skills_binding
 loop,cfg=engine;owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,False)
 if fault=='read_denied':
  original=Path.read_bytes
  def read(path):
   if path.name=='SKILL.md':raise PermissionError('injected actual read denial')
   return original(path)
  monkeypatch.setattr(Path,'read_bytes',read)
 elif fault=='parse_failure':monkeypatch.setattr(loop._skill_loader,'_parse_skill',lambda path:None)
 else:(root/'catalog_on/SKILL.md').write_text('new unsynchronized source',encoding='utf-8')
 assert _capture_skills_binding(loop.context) is None
 with pytest.raises((ValueError,OSError)):list_skills()


def test_normal_skills_catalog_load_then_list_and_other_session_isolation(engine,tmp_path,monkeypatch):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from tests.test_trusted_publication_native_families import _operation_spec
 from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
 _,cfg=engine;owner,root=_setup_skills_catalog(engine,tmp_path,monkeypatch,False);monkeypatch.setitem(globals(),'_SKILLS_CATALOG_CASE_OUT',_SKILLS_CATALOG_OUT/'evidence'/cfg.sessions_resolved.parents[1].name)
 class CurrentGoal(_NativeProductModel):
  def chat(self,messages,system='',tools=None,**kwargs):
   response=super().chat(messages,system=system,tools=tools,**kwargs)
   for call in response.tool_calls or []:
    if call.name=='record_analysis_plan':
     view=ScriptedClient._current_host_snapshot(messages,system);candidates=[r for r in view['execution_targets'] if r['semantic_kind']=='result' and not r.get('necessary_deliveries')]
     goal=candidates[-1] if candidates else view['execution_targets'][-1]
     for declaration in call.arguments['plan_json']['method_plan'][0]['required_deliveries']:declaration['requirement_id']=goal['id']
   return response
 class Switch:
  active=None
  def chat(self,*args,**kwargs):return self.active.chat(*args,**kwargs)
  def stream_chat_structured(self,*args,**kwargs):yield from self.active.stream_chat_structured(*args,**kwargs)
 client=Switch();manager=AgentManager(client_factory=lambda **kw:client,auxiliary_client_factory=lambda:client);app=create_app();app.config['agent_manager']=manager
 load='只加载catalog_on Skills。';listing='只列出当前全局Skills及本会话加载状态，不需要数据文件。'
 scenarios=[('load','skills_catalog_a',load,'load_skill',{'name':'catalog_on'},[_operation_spec('load_skill',{'name':'catalog_on'})]),('list_a','skills_catalog_a',listing,'list_skills',{},[_skills_catalog_spec()]),('list_b','skills_catalog_b',listing,'list_skills',{},[_skills_catalog_spec()])];records=[]
 with app.test_client() as http:
  for label,sid,content,tool,args,specs in scenarios:
   client.active=CurrentGoal(content,'',tool,args,specs);response=http.post('/api/chat',json={'session_id':sid,'message':content});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];saved=load_session(sid);answer=read_answer(sid,saved['messages'][-1]['answer_ref']);refreshed=http.get('/api/sessions/'+sid).get_json();ends=[d for e,d in events if e=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed' and ends[0]['reply_content']==answer['body']
   assert answer['requirement_outcomes'][-1]['status']=='answered'
   if tool=='list_skills':
    result=json.loads(next(d['web']['summary'] for e,d in events if e=='tool_result' and d['name']==tool));assert next(r for r in result['skills'] if r['name']=='catalog_on')['loaded']==(label=='list_a')
   export=export_assistant_reply(sid,answer['body'],'md');assert export['status']=='exported';md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8');(_SKILLS_CATALOG_CASE_OUT/('chain_'+label+'.md')).write_bytes(md.read_bytes());records.append({'label':label,'session_id':sid,'session_dir':str(cfg.sessions_resolved/sid),'events':events,'saved':saved,'refreshed':refreshed,'answer':answer,'md_path':str(md),'calls':client.active.calls})
 _capture_skills_catalog('normal_chain.json',{'root':str(root),'records':records,'provider_calls':0})
 assert records[0]['saved']['messages'][-1]['answer_ref']==records[1]['saved']['messages'][next(i for i,m in enumerate(records[1]['saved']['messages']) if m.get('answer_id')==records[0]['answer']['answer_id'])]['answer_ref']


_MCP_CONFIG_OUT=Path('tmp/s3-mcp-config-20261013-r2')


def _mcp_config_setup(engine,tmp_path,monkeypatch):
 import data_agent.agent.loop as module
 _,cfg=engine
 home=tmp_path/'home';home.mkdir()
 monkeypatch.setattr(Path,'home',lambda:home)
 monkeypatch.setattr(cfg,'mcp_enabled',False)
 monkeypatch.setattr(module,'_mcp_manager',None)
 path=cfg.global_mcp_config_path
 old=MCPConfig(servers=[MCPServerConfig(name='old',transport='stdio',command='offline-fixture',enabled=True,env={'EXAMPLE':'原值'},headers={'Example':'preserve'})])
 save_mcp_config(old,path)
 return cfg,path,path.read_bytes(),old


def _mcp_config_fault(monkeypatch,path,kind):
 original_open=builtins.open;original_write=Path.write_bytes;original_replace=Path.replace
 fired=[]
 def writer(p,mode='r',*a,**kw):
  if Path(p)==path and 'w' in mode and not fired:
   fired.append('direct')
   if kind!='before':
    with original_open(p,'wb') as f:f.write(b'servers: [broken')
   raise OSError('MCP caught write '+kind)
  return original_open(p,mode,*a,**kw)
 def write(p,value,*a,**kw):
  if p.parent==path.parent and p.name.startswith('.atomic-') and not fired and kind in {'before','partial'}:
   fired.append('temporary')
   if kind=='partial':original_write(p,value[:3],*a,**kw)
   raise OSError('MCP caught write '+kind)
  return original_write(p,value,*a,**kw)
 def replace(p,target,*a,**kw):
  if Path(target)==path and not fired and kind in {'replace','after_replace'}:
   fired.append('replace')
   if kind=='after_replace':original_replace(p,target,*a,**kw)
   raise OSError('MCP caught replacement '+kind)
  return original_replace(p,target,*a,**kw)
 monkeypatch.setattr(builtins,'open',writer);monkeypatch.setattr(Path,'write_bytes',write);monkeypatch.setattr(Path,'replace',replace)
 return fired


def _mcp_config_capture(cfg,name,value):
 folder=_MCP_CONFIG_OUT/'evidence'/cfg.sessions_resolved.parents[1].name;folder.mkdir(parents=True,exist_ok=True)
 with (folder/(name+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
 return folder


@pytest.mark.parametrize('route',['store','tool','registry','api'])
@pytest.mark.parametrize('kind',['before','partial','replace','after_replace'])
def test_mcp_caught_save_failure_preserves_old_bytes(engine,tmp_path,monkeypatch,route,kind):
 from data_agent.tools.mcp_tools import add_mcp_server
 from data_agent.web.app import create_app
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 app=create_app();error=None;result=None
 with monkeypatch.context() as m:
  fired=_mcp_config_fault(m,path,kind)
  try:
   if route=='store':save_mcp_config(MCPConfig(servers=[MCPServerConfig(name='new',transport='stdio',command='new-offline')]),path)
   elif route=='tool':result=add_mcp_server('new','stdio',command='new-offline')
   elif route=='registry':result=registry.execute('add_mcp_server',{'name':'new','transport':'stdio','command':'new-offline'}).summary
   else:
    with app.test_client() as http:
     response=http.post('/api/mcp/servers',json={'name':'new','transport':'stdio','command':'new-offline'});result=response.get_json();error=response.status_code
  except OSError as exc:error=str(exc)
 after=path.read_bytes()
 if hasattr(result,'to_web'):result=result.to_web()
 _mcp_config_capture(cfg,route+'_'+kind,{'old_hex':old_bytes.hex(),'after_hex':after.hex(),'error':error,'result':result,'fired':fired,'provider_calls':0})
 assert fired
 assert after==old_bytes
 assert load_mcp_config(path)==old
 assert not list(path.parent.glob('.atomic-*.tmp'))


@pytest.mark.parametrize('action',['add_mcp_server','disable_mcp_server','delete_mcp_server'])
def test_normal_standalone_mcp_management_effect_requires_bound_plan(engine,tmp_path,monkeypatch,action):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 args={'name':'new','transport':'stdio','command':'new-offline'} if action=='add_mcp_server' else {'name':'old'}
 content='只执行明确的全局MCP配置操作并交付真实效果，不连接服务器。完整参数：'+json.dumps({'tool':action,'arguments':args},ensure_ascii=False)
 model=_NativeProductModel(content,None,action,args,[_operation_spec(action,args)])
 manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='mcp_effect_'+action
 with app.test_client() as http:
  response=http.post('/api/chat',json={'session_id':sid,'message':content});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refreshed=http.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);refs=manager.get(sid).context.analysis_state.accepted_answers;answer=read_answer(sid,refs[-1]) if refs else None
 _mcp_config_capture(cfg,action,{'old_hex':old_bytes.hex(),'after_hex':path.read_bytes().hex(),'events':events,'saved':saved,'refreshed':refreshed,'answer':answer,'calls':model.calls,'provider_calls':0})
 assert answer and answer['requirement_outcomes'][0]['status']=='answered'
 assert not answer['source_snapshot']['claims'] and answer['source_snapshot']['effects']
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 with use_agent_context(manager.get(sid).context):export=export_assistant_reply(sid,answer['body'],'md')
 assert export['status']=='exported';md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8')
 folder=_MCP_CONFIG_OUT/'evidence'/cfg.sessions_resolved.parents[1].name;(folder/(action+'.md')).write_bytes(md.read_bytes())


@pytest.mark.parametrize('action',['add_mcp_server','enable_mcp_server','disable_mcp_server','delete_mcp_server'])
@pytest.mark.parametrize('route',['tool','registry','api'])
def test_mcp_config_actual_transition_preserves_other_servers_and_metadata(engine,tmp_path,monkeypatch,action,route):
 from data_agent.tools import mcp_tools
 from data_agent.mcp.config import MCPServerConfig,save_mcp_config,load_mcp_config
 from data_agent.web.app import create_app
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 old.servers.append(MCPServerConfig(name='other',transport='sse',url='http://127.0.0.1:9/offline',headers={'Example':'KEEP'}));save_mcp_config(old,path)
 args={'name':'old','transport':'stdio','command':'replacement','args':['--local'],'enabled':False} if action=='add_mcp_server' else {'name':'old'}
 if route=='tool':result=getattr(mcp_tools,action)(**args)
 elif route=='registry':result=registry.execute(action,args)
 else:
  app=create_app()
  with app.test_client() as http:
   if action=='add_mcp_server':response=http.post('/api/mcp/servers',json=args)
   elif action=='delete_mcp_server':response=http.delete('/api/mcp/servers/old')
   else:response=http.post('/api/mcp/servers/old/'+('enable' if action=='enable_mcp_server' else 'disable'))
   assert response.status_code==200;result=response.get_json()
 actual=load_mcp_config(path);servers={s.name:s for s in actual.servers}
 assert servers['other']==old.servers[1]
 if action=='delete_mcp_server':assert set(servers)=={'other'}
 elif action=='add_mcp_server':assert servers['old'].command=='replacement' and servers['old'].args==['--local'] and not servers['old'].enabled
 else:
  expected=old.servers[0].model_copy(update={'enabled':action=='enable_mcp_server'});assert servers['old']==expected
 if route!='api':assert result.data['state']['configuration']==actual.model_dump(exclude_none=True)
 assert not list(path.parent.glob('.atomic-*.tmp'))
 _mcp_config_capture(cfg,action+'_'+route+'_success',{'configuration':actual.model_dump(exclude_none=True),'provider_calls':0})


@pytest.mark.parametrize('kind',['before','partial','replace','after_replace','readback'])
@pytest.mark.parametrize('exists',[False,True])
def test_mcp_save_failure_preserves_existing_or_absent_target(engine,tmp_path,monkeypatch,kind,exists):
 import data_agent.mcp.config as module
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 if not exists:path.unlink()
 with monkeypatch.context() as m:
  if kind=='readback':
   def reject(*a,**kw):raise OSError('MCP readback failure after replacement')
   m.setattr(module,'mcp_config_state',reject)
  else:_mcp_config_fault(m,path,kind)
  with pytest.raises(OSError):module.save_mcp_config(MCPConfig(servers=[MCPServerConfig(name='new',transport='stdio',command='new')]),path)
 assert path.exists()==exists
 if exists:assert path.read_bytes()==old_bytes and load_mcp_config(path)==old
 assert not list(path.parent.glob('.atomic-*.tmp'))


@pytest.mark.parametrize('action',['enable_mcp_server','disable_mcp_server','delete_mcp_server'])
def test_mcp_config_missing_target_is_no_success_effect(engine,tmp_path,monkeypatch,action):
 from data_agent.agent.publication.native import resolve_operation_effect
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 loop=engine[0];request(loop,'仅操作缺失的MCP配置',_operation_spec(action,{'name':'missing'}));binding=loop._capture_tool_execution_binding(action,{'name':'missing'});result=registry.execute(action,{'name':'missing'})
 assert result.data['error_type']=='mcp_server_not_found' and path.read_bytes()==old_bytes
 assert not loop._record_turn_tool_result(action,result.summary,{'name':'missing'},'missing-call',result.data,execution_binding=binding)
 assert not loop.context.analysis_state.tool_receipts


@pytest.mark.parametrize('change',['file','parsed','result','before','permission','path','session','arguments'])
def test_mcp_config_effect_rejects_changed_source_result_and_binding(engine,tmp_path,monkeypatch,change):
 from data_agent.agent.publication.native import resolve_operation_effect
 from tests.test_r3_comparison_host_claims import _tamper
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch);loop=engine[0];args={'name':'new','transport':'stdio','command':'new-offline'}
 request(loop,'仅新增指定MCP配置',_operation_spec('add_mcp_server',args));rid,result=execute(loop,'add_mcp_server',args);receipt=loop.context.analysis_state.tool_receipts[-1]
 assert resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
 if change=='file':path.write_bytes(path.read_bytes()+b'\n# changed bytes\n')
 elif change=='parsed':
  actual=load_mcp_config(path);actual.servers[0].command='changed';save_mcp_config(actual,path)
 elif change=='result':
  result['state']['sha256']='sha256:'+'0'*64;_tamper(loop,cfg,rid,result)
 elif change=='before':receipt['operation_binding']['object_before']['sha256']='sha256:'+'0'*64
 elif change=='permission':receipt['operation_binding']['permission_scope']='OTHER'
 elif change=='path':receipt['operation_binding']['object_before']['path']=str(tmp_path/'OTHER')
 elif change=='session':receipt['operation_binding']['session_id']='other_session'
 else:receipt['arguments']['command']='other-command'
 with pytest.raises(ValueError):resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize('change',['file','configuration_root'])
def test_mcp_config_commit_rechecks_actual_file_after_render(engine,tmp_path,monkeypatch,change):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.publication.contracts import encode
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch);loop=engine[0];args={'name':'old'}
 request(loop,'仅禁用指定MCP配置',_operation_spec('disable_mcp_server',args));execute(loop,'disable_mcp_server',args);snapshot=snapshot_for_turn(loop)
 data=snapshot.as_dict();body,error=publish(loop,encode({'schema':'answer_bindings.v2','snapshot_digest':snapshot.digest,'sections':[{'requirement_ids':[r['id'] for r in data['requirements']],'parts':[{'kind':'effect','ref':e['id']} for e in data['effects']]}]}));assert error is None and '操作完成' in body
 if change=='file':path.write_bytes(path.read_bytes()+b'\n# actual edit\n')
 else:
  other=tmp_path/'other_home';other.mkdir();monkeypatch.setattr(Path,'home',lambda:other)
 assert commit(loop,{'role':'assistant'},body) and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize('case',['enable','replace','empty_delete','missing','undeclared','mismatched','failed_write'])
def test_mcp_normal_app_config_effect_refusal_failure_save_refresh_and_md(engine,tmp_path,monkeypatch,case):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 action={'enable':'enable_mcp_server','replace':'add_mcp_server','empty_delete':'delete_mcp_server','missing':'delete_mcp_server','undeclared':'disable_mcp_server','mismatched':'disable_mcp_server','failed_write':'disable_mcp_server'}[case]
 args={'name':'old','transport':'stdio','command':'replacement'} if case=='replace' else {'name':'missing' if case=='missing' else 'old'}
 actual=dict(args,name='other') if case=='mismatched' else args
 content='仅修改全局MCP配置并交付配置保存效果，不连接远端。完整参数：'+json.dumps({'tool':action,'arguments':args},ensure_ascii=False)
 model=_NativeProductModel(content,None,action,actual,[_operation_spec(action,args)])
 if case=='undeclared':model.step=1
 manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='mcp_config_'+case
 with monkeypatch.context() as m:
  fired=_mcp_config_fault(m,path,'after_replace') if case=='failed_write' else []
  with app.test_client() as http:
   response=http.post('/api/chat',json={'session_id':sid,'message':content});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refreshed=http.get('/api/sessions/'+sid).get_json();catalogue=http.get('/api/mcp/servers').get_json()
 loop=manager.get(sid);saved=load_session(sid);refs=loop.context.analysis_state.accepted_answers;assert len(refs)==1;answer=read_answer(sid,refs[0]);ends=[d for e,d in events if e=='turn_end'];assert len(ends)==1
 success=case in {'enable','replace','empty_delete'};blocked=case in {'undeclared','mismatched'}
 assert ends[0]['status']==('failed' if blocked else 'completed')
 assert (answer['requirement_outcomes'][0]['status']=='answered')==success
 assert not answer['source_snapshot']['data_identities'] and not answer['source_snapshot']['claims']
 effects=answer['source_snapshot']['effects'];assert bool(effects)==success
 if success:
  assert effects[0]['object']['identity']['sha256']=='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
  assert effects[0]['object']['identity']['configuration']=={'servers':catalogue}
  assert effects[0]['before']['object_before']['sha256']=='sha256:'+hashlib.sha256(old_bytes).hexdigest()
  assert effects[0]['permission_scope']=='configured_global_mcp' and '未核验连接' in answer['body']
  if case=='enable':assert effects[0]['details']['changed'] is False
  if case=='replace':assert catalogue[0]['command']=='replacement'
  if case=='empty_delete':assert catalogue==[]
 else:assert path.read_bytes()==old_bytes and '操作完成' not in answer['body']
 if blocked:assert 'operation_plan_required' in ends[0]['execution_notice'] and not any(r['tool_name']==action for r in loop.context.analysis_state.tool_receipts)
 else:assert saved['messages'][-1]['content']==answer['body']==ends[0]['reply_content']
 if case in {'failed_write','missing'}:
  assert answer['requirement_outcomes'][0]['status']=='failed'
  assert ('MCP caught replacement after_replace' if case=='failed_write' else 'MCP server not found') in answer['body']
  assert not any(r['tool_name']==action for r in loop.context.analysis_state.tool_receipts)
 if case=='failed_write':assert fired
 assert any(m.get('answer_ref')==refs[0] and m['content']==answer['body'] for m in refreshed['messages'])
 durable=json.loads((cfg.sessions_resolved/sid/'run_state.json').read_text(encoding='utf-8'));assert durable['turn_id']==ends[0]['turn_id'] and durable['status']==ends[0]['status']
 folder=_mcp_config_capture(cfg,'normal_'+case,{'answer':answer,'events':events,'saved':saved,'refreshed':refreshed,'durable':durable,'catalogue':catalogue,'old_hex':old_bytes.hex(),'after_hex':path.read_bytes().hex(),'provider_calls':0})
 if not blocked:
  with use_agent_context(loop.context):export=export_assistant_reply(sid,answer['body'],'md')
  assert export['status']=='exported';md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8');(folder/('normal_'+case+'.md')).write_bytes(md.read_bytes())


@pytest.mark.parametrize('case',['clear_after_success','wrong_arguments','unbound','save_failure'])
def test_mcp_typed_failure_stays_on_exact_existing_delivery_and_rolls_back_annotation(engine,tmp_path,monkeypatch,case):
 from data_agent.agent.publication.native import operation_spec
 from data_agent.agent.publication.runtime import snapshot_for_turn
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch);loop=engine[0];action='disable_mcp_server';args={'name':'old'}
 request(loop,'仅禁用明确MCP配置',_operation_spec(action,args));state=loop.context.analysis_state;step=state.analysis_plan['method_plan'][0];binding=loop._capture_tool_execution_binding(action,args)
 binding.update(plan_id=state.analysis_plan['id'],requirement_ids=step['requirement_ids'],required_delivery_ids=[d['id'] for d in step['required_deliveries']])
 before=deepcopy(state.answer_requirements);payload={'error':'EXACT_TYPED_FAILURE','error_type':'mcp_config_write_failed'}
 if case=='wrong_arguments':binding['operation_binding']['operation']=operation_spec(action,{'name':'other'})
 if case=='unbound':binding['required_delivery_ids']=[]
 if case=='save_failure':
  with monkeypatch.context() as m:
   m.setattr(state,'save',lambda:(_ for _ in ()).throw(OSError('annotation save rejected')))
   with pytest.raises(OSError):loop._record_turn_tool_result(action,encode(payload),args,'failure',payload,execution_binding=binding)
  assert state.answer_requirements==before;return
 assert not loop._record_turn_tool_result(action,encode(payload),args,'failure',payload,execution_binding=binding)
 failures=state.answer_requirements[0].get('source_binding',{}).get('operation_failures',{})
 if case!='clear_after_success':assert not failures;return
 assert list(failures)==binding['required_delivery_ids'] and not state.tool_receipts and path.read_bytes()==old_bytes
 result=registry.execute(action,args);rid=loop._record_turn_tool_result(action,result.summary,args,'success',result.data,execution_binding=binding);assert rid
 assert state.answer_requirements[0]['source_binding']['operation_failures']=={}
 snap=snapshot_for_turn(loop).as_dict();assert snap['effects'] and not snap['claims'] and snap['requirements'][0]['gap'] is None


_MCP_CATALOG_OUT=Path('tmp/s3-mcp-catalog-20261013-r1')


def _mcp_catalog_capture(cfg,n,v):
 p=_MCP_CATALOG_OUT/'evidence'/cfg.sessions_resolved.parents[1].name;p.mkdir(parents=True,exist_ok=True);(p/(n+'.json')).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')


@pytest.mark.parametrize('empty',[False,True])
@pytest.mark.parametrize('route',['tool','registry','api'])
def test_mcp_catalogue_actual_empty_and_nonempty(engine,tmp_path,monkeypatch,empty,route):
 from data_agent.tools.mcp_tools import list_mcp_servers
 from data_agent.web.app import create_app
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 if empty:path.write_text('servers: []\n',encoding='utf-8')
 if route=='tool':result=json.loads(list_mcp_servers());servers=result['servers']
 elif route=='registry':result=registry.execute('list_mcp_servers',{}).data;servers=result['servers']
 else:
  with create_app().test_client() as http:response=http.get('/api/mcp/servers');assert response.status_code==200;result=response.get_json();servers=result
 _mcp_catalog_capture(cfg,route+'_'+str(empty),{'result':result,'config_path':str(path),'config_hex':path.read_bytes().hex(),'provider_calls':0})
 assert [s['name'] for s in servers]==([] if empty else ['old'])


@pytest.mark.parametrize('empty',[False,True])
@pytest.mark.parametrize('runtime_state',['none','empty','connected','degraded','disconnected'])
def test_normal_standalone_mcp_catalogue_needs_no_dataset(engine,tmp_path,monkeypatch,empty,runtime_state):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 if empty:path.write_text('servers: []\n',encoding='utf-8')
 runtime_manager=_mcp_catalog_runtime(monkeypatch,runtime_state)
 import os
 runtime_source={'state':runtime_state,'process_id':os.getpid(),'manager_identity':id(runtime_manager) if runtime_manager else None,'session_identity':id(runtime_manager._connections['cached'].session) if runtime_manager and runtime_state not in {'none','empty','disconnected'} else None}
 content='只列出当前全局配置的MCP服务器和本进程已有连接状态；空配置也如实列出，不上传数据，不连接或调用远端。'
 model=_NativeProductModel(content,None,'list_mcp_servers',{},[{'kind':'table','scope':{'parameters':{'catalog_scope':'current_visible','catalog_output':key}}} for key in ['mcp_servers','mcp_health']]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager;sid='mcp_catalog_'+str(empty)+'_'+runtime_state
 with app.test_client() as http:
  response=http.post('/api/chat',json={'session_id':sid,'message':content});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refreshed=http.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);refs=manager.get(sid).context.analysis_state.accepted_answers;answer=read_answer(sid,refs[-1]) if refs else None
 _mcp_catalog_capture(cfg,'normal_'+str(empty)+'_'+runtime_state,{'runtime_source':runtime_source,'config_path':str(path),'session_dir':str(cfg.sessions_resolved/sid),'answer':answer,'events':events,'saved':saved,'refreshed':refreshed,'calls':model.calls,'config_hex':path.read_bytes().hex(),'provider_calls':0})
 assert answer and answer['requirement_outcomes'][0]['status']=='answered'
 assert not answer['source_snapshot']['data_identities']

 assert len(answer['source_snapshot']['claims'])==2
 health=next(c['value'] for c in answer['source_snapshot']['claims'] if c['basis_refs'][0]['result_path']==['health'])
 assert health['availability']==('unavailable' if runtime_state=='none' else 'available')
 if runtime_state=='none':assert health['connections'] is None and '连接状态未知' in answer['body']
 elif runtime_state=='empty':assert health['connections']=={}
 else:assert health['connections']['cached']['status']==runtime_state and '(+3)' in health['connections']['cached']['tools']
 assert '单位未知' not in answer['body'] and (not empty or '0项' in answer['body'])
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 with use_agent_context(manager.get(sid).context):export=export_assistant_reply(sid,answer['body'],'md')
 assert export['status']=='exported';md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8')
 folder=_MCP_CATALOG_OUT/'evidence'/cfg.sessions_resolved.parents[1].name;(folder/('normal_'+str(empty)+'_'+runtime_state+'.md')).write_bytes(md.read_bytes())


def _mcp_catalog_runtime(monkeypatch,state):
 import data_agent.agent.loop as module
 from data_agent.mcp.client import MCPClientManager,MCPConnection
 from data_agent.mcp.models import MCPToolDef
 if state=='none':monkeypatch.setattr(module,'_mcp_manager',None);return None
 config=MCPConfig(servers=[MCPServerConfig(name='cached',transport='stdio',command='previously-loaded-offline')]);manager=MCPClientManager(config)
 def forbidden(*a,**kw):raise AssertionError('MCP catalogue must not connect/probe/call remote')
 monkeypatch.setattr(manager,'start',forbidden);monkeypatch.setattr(manager,'call_tool',forbidden);monkeypatch.setattr(manager,'connect_server',forbidden)
 if state!='empty':
  conn=MCPConnection(config.servers[0]);conn.session=object() if state!='disconnected' else None;conn._failure_count=3 if state=='degraded' else 0
  conn.tools_cache=[MCPToolDef('cached','cached_tool_'+str(i),'Offline cached tool',{'type':'object'}) for i in range(8)];manager._connections['cached']=conn
 monkeypatch.setattr(module,'_mcp_manager',manager);return manager


def _mcp_catalog_specs():
 return [{'kind':'table','scope':{'parameters':{'catalog_scope':'current_visible','catalog_output':key}}} for key in ['mcp_servers','mcp_health']]


@pytest.mark.parametrize('change',['file_bytes','configuration','runtime_available','manager_config','connection','failure_count','tools_cache','session','permission','path','process','digest','arguments','servers_result','health_result'])
def test_mcp_catalogue_rejects_changed_configuration_runtime_result_and_binding(engine,tmp_path,monkeypatch,change):
 from data_agent.agent.publication.native import resolve_native_claims
 from tests.test_r3_comparison_host_claims import _tamper
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch);manager=_mcp_catalog_runtime(monkeypatch,'connected');loop=engine[0];rid,result=execute(loop,'list_mcp_servers',{});receipt=loop.context.analysis_state.tool_receipts[-1]
 assert len(resolve_native_claims(session_id=loop.session_id,receipt_id=rid))==2
 if change=='file_bytes':path.write_bytes(path.read_bytes()+b'\n# changed\n')
 elif change=='configuration':
  actual=load_mcp_config(path);actual.servers[0].enabled=False;save_mcp_config(actual,path)
 elif change=='runtime_available':_mcp_catalog_runtime(monkeypatch,'none')
 elif change=='manager_config':manager._config.servers[0].command='other-runtime'
 elif change=='connection':manager._connections['cached'].session=None
 elif change=='failure_count':manager._connections['cached']._failure_count=2
 elif change=='tools_cache':manager._connections['cached'].tools_cache[-1].description='OTHER'
 elif change=='session':receipt['mcp_binding']['session_id']='other_session'
 elif change=='permission':receipt['mcp_binding']['permission_scope']='OTHER'
 elif change=='path':receipt['mcp_binding']['configuration']['path']=str(tmp_path/'OTHER')
 elif change=='process':receipt['mcp_binding']['runtime']['process_id']+=1
 elif change=='digest':receipt['mcp_binding']['snapshot_sha256']='sha256:'+'0'*64
 elif change=='arguments':receipt['arguments']={'other':True}
 elif change=='servers_result':result['servers']=[];_tamper(loop,cfg,rid,result)
 else:result['health']['connections']['cached']['status']='disconnected';_tamper(loop,cfg,rid,result)
 with pytest.raises(ValueError):resolve_native_claims(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize('change',['file','runtime','rebound_receipt'])
def test_mcp_catalogue_final_commit_rechecks_original_configuration_and_cache_proof(engine,tmp_path,monkeypatch,change):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
 from data_agent.tools.mcp_tools import _mcp_catalog_snapshot
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch);manager=_mcp_catalog_runtime(monkeypatch,'connected');loop=engine[0];request(loop,'列出配置和当前进程MCP连接记录',_mcp_catalog_specs()[0]);execute(loop,'list_mcp_servers',{});snapshot=snapshot_for_turn(loop);body,error=publish(loop,draft(snapshot));assert error is None and loop._accepted_answer['requirement_outcomes'][0]['status']=='answered'
 if change in {'file','rebound_receipt'}:
  path.write_bytes(path.read_bytes()+b'\n# same config with new bytes\n')
  if change=='rebound_receipt':loop.context.analysis_state.tool_receipts[-1]['mcp_binding']=_mcp_catalog_snapshot(loop.context)[1]
 else:manager._connections['cached'].session=None
 assert commit(loop,{'role':'assistant'},body) and not loop.context.analysis_state.accepted_answers


@pytest.mark.parametrize('kind',['measurement','fit','forecast','chart','series','operation'])
def test_mcp_catalogue_cannot_borrow_data_or_method_authority(kind):
 from data_agent.agent.publication.deliveries import validate_business_scope
 value=_mcp_catalog_specs()[0]['scope']
 with pytest.raises(ValueError):validate_business_scope(value,required=True,measurement=kind=='measurement',operation=kind=='operation',metadata=kind=='table')


@pytest.mark.parametrize('change',['dataset','metric','quantity','scope','unknown_output'])
def test_mcp_catalogue_scope_is_metadata_only_and_explicit(change):
 from data_agent.agent.publication.deliveries import validate_business_scope
 scope=_mcp_catalog_specs()[0]['scope']
 if change=='dataset':scope['datasets']=['orders']
 elif change=='metric':scope['metrics']=['amount']
 elif change=='quantity':scope['quantity']='sum'
 elif change=='scope':scope['parameters']['catalog_scope']='other'
 else:scope['parameters']['catalog_output']='other_mcp'
 with pytest.raises(ValueError):validate_business_scope(scope,required=True,operation=False,metadata=True)


def test_mcp_catalogue_unrelated_data_or_skills_changes_do_not_invalidate_snapshot(engine,tmp_path,monkeypatch):
 import pandas as pd
 from data_agent.agent.publication.native import resolve_native_claims
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch);loop=engine[0];rid,result=execute(loop,'list_mcp_servers',{});before=resolve_native_claims(session_id=loop.session_id,receipt_id=rid)
 loop.context.workspace.add('unrelated',pd.DataFrame({'x':[1]}));assert resolve_native_claims(session_id=loop.session_id,receipt_id=rid)==before


@pytest.mark.parametrize('case',['missing','bad_yaml','not_file'])
def test_mcp_catalogue_never_calls_unreadable_configuration_empty_success(engine,tmp_path,monkeypatch,case):
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 if case=='missing':
  path.unlink();result=registry.execute('list_mcp_servers',{});assert result.data['servers']==[];return
 if case=='bad_yaml':path.write_text('servers: [broken',encoding='utf-8')
 else:path.unlink();path.mkdir()
 result=registry.execute('list_mcp_servers',{});assert result.data is None or 'servers' not in result.data
 assert 'error' in result.summary.lower()


_MCP_ERROR_OUT=Path('tmp/s3-mcp-error-20261013-r1')


def _mcp_error_capture(cfg,n,v):
 p=_MCP_ERROR_OUT/'evidence'/cfg.sessions_resolved.parents[1].name;p.mkdir(parents=True,exist_ok=True)
 with (p/(n+'.json')).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
 return p


def _mcp_error_setup(engine,tmp_path,monkeypatch,case):
 import data_agent.agent.loop as module
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 error=not case.startswith('success');texts={'error_text':['REMOTE_EXPLICIT_FAILURE 中文'],'error_multi':['first failure','second failure'],'error_empty':[],'error_nontext':[],'error_long':['REMOTE_LONG_FAILURE '+('详尽错误说明'*1000)],'success_empty':[],'success':['REMOTE_OK 中文','second line']}[case]
 calls=[]
 class Session:
  async def call_tool(self,tool,arguments):
   calls.append({'tool':tool,'arguments':arguments})
   return SimpleNamespace(isError=error,content=([SimpleNamespace(type='image',data='offline-not-decoded')] if case=='error_nontext' else [SimpleNamespace(text=t) for t in texts]))
 manager=MCPClientManager(MCPConfig());conn=MCPConnection(MCPServerConfig(name='offline_error',transport='stdio',command='never-execute'));conn.session=Session();conn.tools_cache=[MCPToolDef('offline_error','read_fixture','Offline text fixture',{'type':'object','properties':{'q':{'type':'string'}},'required':['q']})];manager._connections['offline_error']=conn
 monkeypatch.setattr(manager,'_run_async',lambda coro:asyncio.run(coro));monkeypatch.setattr(module,'_mcp_manager',manager)
 def forbidden(*a,**kw):raise AssertionError('Must not connect, start a server or call Provider')
 monkeypatch.setattr(manager,'start',forbidden);monkeypatch.setattr(manager,'connect_server',forbidden)
 return cfg,manager,conn,calls,error,texts


@pytest.mark.parametrize('case',['error_text','error_multi','error_empty','error_nontext','error_long','success','success_empty'])
@pytest.mark.parametrize('route',['async','manager','generic','bridge','registry'])
def test_mcp_explicit_error_with_text_never_becomes_success(engine,tmp_path,monkeypatch,case,route):
 from data_agent.tools.mcp_tools import call_mcp_tool
 cfg,manager,conn,calls,error,texts=_mcp_error_setup(engine,tmp_path,monkeypatch,case)
 args={'q':'exact input'};local=ToolRegistry();bridge=MCPToolBridge(manager,local);bridge.register_server('offline_error')
 if route=='async':result=asyncio.run(manager._call_tool_async(conn,'read_fixture',args))
 elif route=='manager':result=manager.call_tool('offline_error','read_fixture',args)
 elif route=='generic':result=call_mcp_tool('offline_error','read_fixture',json.dumps(args))
 elif route=='bridge':result=bridge._make_wrapper(conn.tools_cache[0])(**args)
 else:result=local.execute('offline_error__read_fixture',args).summary
 _mcp_error_capture(cfg,route+'_'+case,{'source_isError':error,'source_texts':texts,'calls':calls,'result':result,'provider_calls':0,'remote_mcp_calls':0})
 assert calls==[{'tool':'read_fixture','arguments':args}]
 if error:
  payload=json.loads(result);assert payload['error']=='\n'.join(texts) if texts else payload['error']=='Tool returned an error'
  assert payload.get('error_type')=='mcp_tool_error'
 else:assert result=='\n'.join(texts)


@pytest.mark.parametrize('route,case',[('generic','error_text'),('generic','error_long'),('generic','success'),('bridge','error_text')])
def test_normal_mcp_error_context_then_native_data_delivery(engine,tmp_path,monkeypatch,route,case):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 from data_agent.agent.context import use_agent_context
 cfg,manager,conn,calls,error,texts=_mcp_error_setup(engine,tmp_path,monkeypatch,case)
 if route=='bridge':
  monkeypatch.setattr(registry,'_tools',dict(registry._tools));bridge=MCPToolBridge(manager,registry);bridge.register_server('offline_error');tool='offline_error__read_fixture';args={'q':'exact input'}
 else:tool='call_mcp_tool';args={'server':'offline_error','tool':'read_fixture','arguments':json.dumps({'q':'exact input'})}
 content='加载上传数据并将其命名为experiment；先调用已指定的本地MCP只读示例工具取得上下文，再报告当前记录数；MCP失败不替代数据事实。'
 model=_NativeProductModel(content,'experiment','describe_dataset',{'name':'experiment'},[{'kind':'measurement','scope':{'datasets':['experiment'],'quantity':'rows'}}],[(tool,args)])
 agents=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=agents;sid='mcp_error_'+route+'_'+case;raw=b'amount\n10\n20\n30\n'
 with app.test_client() as http:
  ticket=http.post('/api/upload',data={'file':(io.BytesIO(raw),'experiment.csv')},content_type='multipart/form-data').get_json();model.ticket=ticket
  response=http.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refreshed=http.get('/api/sessions/'+sid).get_json()
 loop=agents.get(sid);saved=load_session(sid);answer=read_answer(sid,saved['messages'][-1]['answer_ref']);end=[d for e,d in events if e=='turn_end'];tool_output=next(d['web'] for e,d in events if e=='tool_result' and d['name']==tool)
 folder=_mcp_error_capture(cfg,'normal_'+route+'_'+case,{'model_calls':model.calls,'source_isError':error,'source_texts':texts,'calls':calls,'tool':tool,'tool_output':tool_output,'answer':answer,'events':events,'saved':saved,'refreshed':refreshed,'session_dir':str(cfg.sessions_resolved/sid),'upload':ticket,'upload_hex':raw.hex(),'provider_calls':0,'remote_mcp_calls':0})
 assert len(end)==1 and end[0]['status']=='completed' and end[0]['reply_content']==answer['body']==saved['messages'][-1]['content']
 assert answer['requirement_outcomes'][0]['status']=='answered' and calls==[{'tool':'read_fixture','arguments':{'q':'exact input'}}]
 assert all(c['basis_refs'][0]['tool_name']=='describe_dataset' for c in answer['source_snapshot']['claims'])
 if error:
  assert tool_output['data']['error_type']=='mcp_tool_error'
  assert tool_output['data']['error']=='\n'.join(texts)
  assert not any(r['tool_name']==tool for r in loop.context.analysis_state.tool_receipts)
 with use_agent_context(loop.context):export=export_assistant_reply(sid,answer['body'],'md')
 assert export['status']=='exported';md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1];assert answer['body'] in md.read_text(encoding='utf-8');(folder/('normal_'+route+'_'+case+'.md')).write_bytes(md.read_bytes())


@pytest.mark.parametrize('case',['unknown','disconnected','degraded','rpc_exception'])
def test_mcp_error_existing_connection_and_transport_failure_boundaries_unchanged(engine,tmp_path,monkeypatch,case):
 cfg,manager,conn,calls,error,texts=_mcp_error_setup(engine,tmp_path,monkeypatch,'success')
 name='unknown' if case=='unknown' else 'offline_error'
 if case=='disconnected':conn.session=None
 if case=='degraded':conn._failure_count=3
 if case=='rpc_exception':
  async def reject(*a,**kw):raise OSError('OFFLINE_RPC_FAILURE')
  monkeypatch.setattr(conn.session,'call_tool',reject)
 result=json.loads(manager.call_tool(name,'read_fixture',{'q':'exact input'}));assert result['error']
 assert not calls
 assert conn._failure_count==({'degraded':3,'rpc_exception':1}.get(case,0))


def test_mcp_error_protocol_failure_keeps_existing_rpc_counter_policy(engine,tmp_path,monkeypatch):
 cfg,manager,conn,calls,error,texts=_mcp_error_setup(engine,tmp_path,monkeypatch,'error_text');conn._failure_count=2
 result=json.loads(manager.call_tool('offline_error','read_fixture',{'q':'exact input'}));assert result['error_type']=='mcp_tool_error'
 assert conn._failure_count==0 and len(calls)==1


_CONV_EXPORT_OUT=Path('tmp/s3-conversation-export-20261013-r1')


_CONV_EXPORT_MESSAGES=[{'role':'user','content':'原始问题 ORIGINAL_USER'}, {'role':'assistant','content':'历史原文 ORIGINAL_ASSISTANT。这里只是保存的旧会话文本，不能升级为当前数据事实。'}]


def _conv_capture(n,v):
 from data_agent.config import get_config
 cfg=get_config();p=_CONV_EXPORT_OUT/'evidence'/cfg.sessions_resolved.parents[1].name;p.mkdir(parents=True,exist_ok=True)
 with (p/(n+'.json')).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)


@pytest.mark.parametrize('route',['tool','registry','api'])
@pytest.mark.parametrize('fmt',['markdown','txt','pdf'])
def test_conv_export_format_agreement(engine,tmp_path,monkeypatch,route,fmt):
 from data_agent.tools.report import export_conversation
 from data_agent.web.app import create_app
 cfg,*_=_mcp_config_setup(engine,tmp_path,monkeypatch);loop=engine[0];sid=loop.session_id;save_session(_CONV_EXPORT_MESSAGES,sid)
 if route=='tool':result=json.loads(export_conversation(format=fmt));status=None;mime=None
 elif route=='registry':response=registry.execute('export_conversation',{'format':fmt});result=response.data or json.loads(response.summary);status=None;mime=None
 else:
  with create_app().test_client() as http:response=http.get('/api/sessions/'+sid+'/export?format='+fmt);result=response.get_json(silent=True) or {'raw':response.get_data(as_text=True)};status=response.status_code;mime=response.mimetype
 files=[{'path':str(p),'sha256':__import__('hashlib').sha256(p.read_bytes()).hexdigest()} for p in (cfg.sessions_resolved/sid/'reports').glob('*')]
 _conv_capture(route+'_'+fmt,{'format':fmt,'route':route,'result':result,'status':status,'mime':mime,'files':files,'provider_calls':0})
 if fmt in {'markdown','pdf'}:assert result.get('status') in {'exported','degraded'};return
 assert result.get('error_type') in {'unsupported_export_format','invalid_tool_arguments'} and not files


@pytest.mark.parametrize('fmt',['markdown','html','html_chart','pdf','pdf_missing','pdf_failed','pdf_empty','storage_failed','blocked_undeclared','blocked_arguments'])
def test_conv_export_normal_standalone_actual_file(engine,tmp_path,monkeypatch,fmt):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.agent.publication.runtime import read_answer
 cfg,*_=_mcp_config_setup(engine,tmp_path,monkeypatch);sid='export_only_'+fmt
 case=fmt;fmt='pdf' if case.startswith('pdf') else 'html' if case=='html_chart' or case.startswith('blocked_') else 'markdown' if case=='storage_failed' else fmt
 if case in {'pdf_missing','pdf_failed','pdf_empty'}:_conv_pdf_fault(monkeypatch,case)
 if case=='storage_failed':
  from data_agent.tools import report
  monkeypatch.setattr(report,'_conversation_outputs',lambda *a,**kw:(_ for _ in ()).throw(OSError('injected export storage failure')))
 content='只把本会话已保存的用户与助手消息导出为'+fmt+'文件，不做新数据分析。';args={'title':'Exact conversation','format':fmt,'include_charts':case=='html_chart'}
 warmup='请说明会话导出的用途。'
 class ExportModel(_NativeProductModel):
  warming=True
  def chat(self,messages,system='',tools=None,**kw):
   if not self.warming:
    if case=='blocked_undeclared' and self.step==0 and system!='你是一个JSON输出器，只返回JSON，不要其他内容。':
     from data_agent.llm.client import Response,ToolCall
     self.step=2;self.calls.append('export_conversation');return Response(tool_calls=[ToolCall('export_without_plan','export_conversation',self.args)])
    return super().chat(messages,system=system,tools=tools,**kw)
   from data_agent.llm.client import Response
   from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
   if system=='你是一个JSON输出器，只返回JSON，不要其他内容。':return Response(text=json.dumps({'intent_type':'knowledge_qa','requested_outputs':[{'kind':'knowledge','exact_span':warmup}]},ensure_ascii=False))
   view=ScriptedClient._current_host_snapshot(messages,system)
   return Response(text=json.dumps({'schema':'answer_bindings.v2','snapshot_digest':view['snapshot_digest'],'sections':[{'requirement_ids':[r['id']],'parts':[{'kind':'text','purpose':'knowledge','text':'会话导出用于保存已经交流的公开消息，便于之后查看和分享；保存文本本身不验证数据结论。','claim_refs':[]}]} for r in view['requirements'] if not r['withdrawn']]},ensure_ascii=False))
 model=ExportModel(content,None,'export_conversation',args,[{'kind':'operation','scope':{'operation':{'action':'export_conversation','arguments':args}}}]);manager=AgentManager(client_factory=lambda **kw:model,auxiliary_client_factory=lambda:model);app=create_app();app.config['agent_manager']=manager
 if case=='blocked_arguments':model.args=dict(args,title='NOT_THE_DECLARED_TITLE')
 with app.test_client() as http:
  first=http.post('/api/chat',json={'session_id':sid,'message':warmup});first_raw=first.get_data(as_text=True);assert first.status_code==200 and 'turn_end' in first_raw;model.warming=False
  if case=='html_chart':
   from data_agent.session.history import session_charts_dir
   charts=session_charts_dir(sid);(charts/'example.json').write_text(json.dumps({'title':'Example','purpose':'exploratory','validation_status':'valid','figure':{'data':[{'type':'bar','x':[1],'y':[2]}]}}),encoding='utf-8');(charts/'example.html').write_text('<html><body>chart</body></html>',encoding='utf-8')
  response=http.post('/api/chat',json={'session_id':sid,'message':content});events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')];refresh=http.get('/api/sessions/'+sid).get_json()
  result=next((d['web']['data'] for e,d in events if e=='tool_result' and d['name']=='export_conversation'),{});main=result.get('artifact_path') or result.get('fallback_artifact_path');download=http.get('/api/files/'+main) if main else None;download_bytes=download.get_data() if download else b'';download_status=download.status_code if download else None
 saved=load_session(sid);refs=[m['answer_ref'] for m in saved['messages'] if m.get('answer_ref')];answer=read_answer(sid,refs[-1]) if refs else None;files=[{'path':str(p),'content':p.read_text(encoding='utf-8') if p.suffix!='.pdf' else None,'sha256':__import__('hashlib').sha256(p.read_bytes()).hexdigest()} for p in (cfg.sessions_resolved/sid/'reports').glob('*')]
 _conv_capture('normal_'+case,{'warmup_sse':first_raw,'response_status':response.status_code,'response_text':response.get_data(as_text=True),'answer':answer,'events':events,'saved':saved,'refreshed':refresh,'files':files,'download_hex':download_bytes.hex(),'download_status':download_status,'model_calls':model.calls,'session_dir':str(cfg.sessions_resolved/sid),'provider_calls':0})
 if case=='storage_failed':
  assert not files and result['error_type']=='conversation_export_failed' and answer['requirement_outcomes'][0]['status']=='failed' and 'injected export storage failure' in answer['body'];return
 if case.startswith('blocked_'):
  assert not files and any(e=='turn_end' and d['status']=='failed' and 'operation_plan_required' in d['execution_notice'] for e,d in events)
  assert not any(r['tool_name']=='export_conversation' for r in manager.get(sid).context.analysis_state.tool_receipts);return
 assert answer and answer['requirement_outcomes'][0]['status']==('partial' if case in {'pdf_missing','pdf_failed','pdf_empty'} else 'answered') and files and answer['source_snapshot']['effects']
 assert download_status==200 and __import__('hashlib').sha256(download_bytes).hexdigest()==result['outputs'][0]['sha256'][7:]
 if case=='pdf':
  from pypdf import PdfReader
  from io import BytesIO
  extracted=''.join(''.join(page.extract_text().split()) for page in PdfReader(BytesIO(download_bytes)).pages)
  assert '会话导出用于保存已经交流的公开消息' in extracted
 assert not answer['source_snapshot']['claims'] and not answer['source_snapshot']['data_identities']
 assert ('PDF未生成' in answer['body'])==(case in {'pdf_missing','pdf_failed','pdf_empty'})
 from data_agent.tools.report import export_assistant_reply
 exported=export_assistant_reply(sid,answer['body'],'md');assert exported['status']=='exported'
 md=cfg.sessions_resolved/sid/'reports'/exported['artifact_path'].split('/')[-1];folder=_CONV_EXPORT_OUT/'evidence'/cfg.sessions_resolved.parents[1].name;(folder/('normal_'+case+'.md')).write_bytes(md.read_bytes())
 assert answer['source_snapshot']['effects'][0]['receipt_id'] in md.read_text(encoding='utf-8')


def _conv_pdf_fault(monkeypatch,case):
 import sys,types
 if case=='pdf_missing':monkeypatch.setitem(sys.modules,'xhtml2pdf',None);return
 import xhtml2pdf
 def render(*args,**kw):
  if case=='pdf_failed':kw['dest'].write(b'PARTIAL_NO_PDF');raise OSError('injected PDF failure')
  return types.SimpleNamespace(err=0)
 monkeypatch.setattr(xhtml2pdf.pisa,'CreatePDF',render)


def _conv_unit_effect(engine,monkeypatch,include_charts=False):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
 from data_agent.agent.publication.native import resolve_operation_effect
 from data_agent.session.history import load_session
 loop,cfg=engine
 request(loop,'说明会话导出用途',kind='knowledge')
 snap=snapshot_for_turn(loop);r=snap.as_dict()['requirements'][0]
 body,error=publish(loop,encode({'schema':'answer_bindings.v2','snapshot_digest':snap.digest,'sections':[{'requirement_ids':[r['id']],'parts':[{'kind':'text','purpose':'knowledge','text':'公开会话用于保存已经交流的消息，不验证数据结论。','claim_refs':[]}]}]}));assert error is None and commit(loop,{'role':'assistant'},body) is None
 source_answer=cfg.sessions_resolved/loop.session_id/load_session(loop.session_id)['messages'][-1]['answer_ref']['path']
 if include_charts:
  from data_agent.session.history import session_charts_dir
  charts=session_charts_dir(loop.session_id);(charts/'example.json').write_text(json.dumps({'title':'Example','purpose':'exploratory','validation_status':'valid','figure':{'data':[{'type':'bar','x':[1],'y':[2]}]}}),encoding='utf-8');(charts/'example.html').write_text('<html><body>chart</body></html>',encoding='utf-8')
 args={'title':'Exact owned conversation','format':'markdown','include_charts':include_charts};spec={'kind':'operation','scope':{'operation':{'action':'export_conversation','arguments':args}}}
 request(loop,'只导出当前公开会话',spec);rid,result=execute(loop,'export_conversation',args);effect=resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)
 assert effect['object']['identity']['sha256']==result['outputs'][0]['sha256']
 return loop,cfg,rid,result,effect,source_answer


@pytest.mark.parametrize('change',['output','manifest','arguments','before_session','permission','before_source','result_source','result_parameters','result_status','result_path','result_outputs','history','answer_source','chart_source'])
def test_conv_export_original_scope_and_source_tamper_rejected(engine,monkeypatch,change):
 from data_agent.agent.publication.native import resolve_operation_effect
 from tests.test_r3_comparison_host_claims import _tamper
 from data_agent.session.history import load_canonical_history,save_session
 loop,cfg,rid,result,effect,source_answer=_conv_unit_effect(engine,monkeypatch,change=='chart_source');receipt=loop.context.analysis_state.tool_receipts[-1];sdir=cfg.sessions_resolved/loop.session_id
 if change=='output':(cfg.sessions_resolved.parent/result['artifact_path']).write_text('changed bytes',encoding='utf-8')
 elif change=='manifest':
  p=sdir/'artifacts.json';rows=json.loads(p.read_text(encoding='utf-8'));next(r for r in rows if r['path']==result['artifact_path'])['type']='report_pdf';p.write_text(json.dumps(rows),encoding='utf-8')
 elif change=='arguments':receipt['arguments']['title']='OTHER'
 elif change=='before_session':receipt['operation_binding']['session_id']='OTHER'
 elif change=='permission':receipt['operation_binding']['permission_scope']='OTHER'
 elif change=='before_source':receipt['operation_binding']['source_snapshot']['public_messages_sha256']='sha256:'+'0'*64
 elif change=='answer_source':source_answer.write_bytes(source_answer.read_bytes()+b' ')
 elif change=='chart_source':(sdir/'charts/example.html').write_text('changed chart source',encoding='utf-8')
 elif change=='history':
  messages=list(load_canonical_history(loop.session_id).messages);messages[0]['content']='changed original';save_session(messages,loop.session_id,extra_meta={'publication_schema':'answer_bindings.v2'},merge_protect=False)
 else:
  if change=='result_source':result['source_binding']['session_id']='OTHER'
  elif change=='result_parameters':result['parameters']['title']='OTHER'
  elif change=='result_status':result['status']='degraded'
  elif change=='result_path':result['artifact_path']='sessions/other/reports/forged.md'
  else:result['outputs'][0]['sha256']='sha256:'+'0'*64
  _tamper(loop,cfg,rid,result)
 with pytest.raises((ValueError,OSError,KeyError)):resolve_operation_effect(session_id=loop.session_id,receipt_id=rid)


@pytest.mark.parametrize('change',['output','answer_source','before_rebind'])
def test_conv_export_final_commit_rechecks_original_source_and_output(engine,monkeypatch,change):
 from data_agent.agent.publication.runtime import snapshot_for_turn,publish,commit
 loop,cfg,rid,result,effect,source_answer=_conv_unit_effect(engine,monkeypatch);snap=snapshot_for_turn(loop);host=snap.as_dict();row=next(r for r in host['requirements'] if r['effect_ids'])
 body,error=publish(loop,encode({'schema':'answer_bindings.v2','snapshot_digest':snap.digest,'sections':[{'requirement_ids':[row['id']],'parts':[{'kind':'effect','ref':row['effect_ids'][0]}]}]}));assert error is None
 if change=='output':(cfg.sessions_resolved.parent/result['artifact_path']).write_text('changed after render',encoding='utf-8')
 elif change=='answer_source':source_answer.write_bytes(source_answer.read_bytes()+b' ')
 else:loop.context.analysis_state.tool_receipts[-1]['operation_binding']['source_snapshot']['history_revision']+=1
 assert commit(loop,{'role':'assistant'},body)
 assert len(loop.context.analysis_state.accepted_answers)==1


@pytest.mark.parametrize('change',['append','rewrite','remove'])
def test_conv_export_persisted_prefix_identity_allows_only_appends(engine,monkeypatch,change):
 from data_agent.tools.report import _conversation_source
 from data_agent.session.history import push_messages,load_canonical_history,save_session
 loop,cfg,rid,result,effect,source_answer=_conv_unit_effect(engine,monkeypatch);source=result['source_binding']
 if change=='append':
  push_messages(loop.session_id,[{'role':'tool','content':'unrelated later result','tool_call_id':'later'}]);assert _conversation_source(loop.session_id,False,source)[1]==source;return
 messages=list(load_canonical_history(loop.session_id).messages)
 if change=='rewrite':messages[0]['content']='changed prefix'
 else:messages=messages[1:]
 save_session(messages,loop.session_id,extra_meta={'publication_schema':'answer_bindings.v2'},merge_protect=False)
 with pytest.raises(ValueError):_conversation_source(loop.session_id,False,source)


@pytest.mark.parametrize('fault',['output','manifest','readback','pdf_write'])
def test_conv_export_caught_storage_failure_preserves_existing_files_and_manifest(engine,monkeypatch,fault):
 from data_agent.tools import report
 from data_agent.utils import atomic_files
 loop,cfg=engine;save_session(_CONV_EXPORT_MESSAGES,loop.session_id);first=json.loads(report.export_conversation(format='markdown'));assert first['status']=='exported'
 sdir=cfg.sessions_resolved/loop.session_id;root=sdir/'reports';before={str(p.relative_to(sdir)):p.read_bytes() for p in root.iterdir()};before['artifacts.json']=(sdir/'artifacts.json').read_bytes()
 original=atomic_files.write_text_atomic;original_bytes=atomic_files.write_bytes_atomic
 def write(path,content):
  original(path,content)
  if fault=='output' and path.parent==root or fault=='manifest' and path.name=='artifacts.json':raise OSError('injected export storage failure')
 def write_bytes(path,content):original_bytes(path,content);raise OSError('injected PDF storage failure')
 if fault=='readback':monkeypatch.setattr(report,'_conversation_outputs',lambda *a,**kw:(_ for _ in ()).throw(OSError('injected export readback')))
 elif fault=='pdf_write':monkeypatch.setattr(atomic_files,'write_bytes_atomic',write_bytes)
 else:monkeypatch.setattr(atomic_files,'write_text_atomic',write)
 result=json.loads(report.export_conversation(format='pdf' if fault=='pdf_write' else 'html'));assert result['error_type']=='conversation_export_failed'
 after={str(p.relative_to(sdir)):p.read_bytes() for p in root.iterdir()};after['artifacts.json']=(sdir/'artifacts.json').read_bytes();assert after==before


@pytest.mark.parametrize('case',['undeclared','other_action','wrong_title','wrong_chart_option'])
def test_conv_export_normal_guard_requires_matching_operation_before_writing(engine,monkeypatch,case):
 from data_agent.agent.publication.native import operation_spec
 loop,cfg=engine;args={'title':'Exact','format':'html','include_charts':False}
 if case=='undeclared':request(loop,'请导出会话')
 else:
  declared=deepcopy(args)
  if case=='wrong_title':declared['title']='OTHER'
  if case=='wrong_chart_option':declared['include_charts']=True
  action='write_file' if case=='other_action' else 'export_conversation';values={'path':'output/other.txt','content':'other'} if case=='other_action' else declared
  request(loop,'请执行精确声明操作',{'kind':'operation','scope':{'operation':{'action':action,'arguments':values}}})
 error=loop._current_task_scope_guard('export_conversation',args);assert error and json.loads(error)['error_type']=='operation_plan_required'
 assert not list((cfg.sessions_resolved/loop.session_id/'reports').glob('*'))


@pytest.mark.parametrize('kind',['measurement','table','fit','forecast','chart'])
def test_conv_export_effect_cannot_be_used_as_data_fact(kind):
 from data_agent.agent.publication.deliveries import validate_business_scope
 scope={'operation':{'action':'export_conversation','arguments':{'format':'html'}}}
 with pytest.raises(ValueError):validate_business_scope(scope,required=True,measurement=kind=='measurement',metadata=kind=='table')



@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('transport',['stdio','sse','streamable-http'])
def test_mcp_all_declared_transports_keep_local_configuration_and_required_field_contract(engine,tmp_path,monkeypatch,route,transport):
 from data_agent.tools import mcp_tools
 cfg,path,old_bytes,old=_mcp_config_setup(engine,tmp_path,monkeypatch)
 def forbidden(*a,**kw):raise AssertionError('Local configuration acceptance must not start or connect remote MCP')
 monkeypatch.setattr(MCPClientManager,'start',forbidden);monkeypatch.setattr(MCPClientManager,'connect_server',forbidden)
 args=dict(name='declared',transport=transport,enabled=False)
 try:
  failure=mcp_tools.add_mcp_server(**args) if route=='direct' else registry.execute('add_mcp_server',args)
 except ValueError:failure=None
 assert path.read_bytes()==old_bytes
 if failure is not None:assert 'error' in str(failure).lower()
 args.update(command='never-launch-local-fixture') if transport=='stdio' else args.update(url='http://127.0.0.1:9/never-connect')
 result=mcp_tools.add_mcp_server(**args) if route=='direct' else registry.execute('add_mcp_server',args)
 actual=load_mcp_config(path);created=next(s for s in actual.servers if s.name=='declared')
 assert created.transport==transport and created.enabled is False and actual.servers[0]==old.servers[0]
 assert result.data['state']['configuration']==actual.model_dump(exclude_none=True)
 assert created.command==args['command'] if transport=='stdio' else created.url==args['url']
 (tmp_path/'local-transport-contract.json').write_text(json.dumps(dict(arguments=args,state=result.data,Provider=0,remote_MCP=0),ensure_ascii=False,indent=2),encoding='utf-8')
