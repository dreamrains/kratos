"""P0-2: tool_search must survive phrasing the model actually uses.

Real failure (GLM r3 M04, session ce819a377ad7): the model searched
"analysis plan" and "competing hypotheses ..." and got zero matches, so it
never called record_analysis_plan and the scenario died on
analysis_audit_incomplete.  The old matcher required the whole keyword as a
substring of the name/description; multi-word English keywords with spaces
never match underscore identifiers, and Chinese descriptions never match
English tokens at all.
"""

from __future__ import annotations

import json

from data_agent.tools import discover_tools
from data_agent.tools.registry import registry, tool_search

discover_tools()


def _names(result_json: str) -> list[str]:
    payload = json.loads(result_json)
    return [m["name"] for m in payload.get("tools") or []]


def test_multi_word_keyword_matches_underscore_identifier():
    assert "record_analysis_plan" in _names(tool_search("analysis plan"))


def test_evidence_relation_keyword_matches_schema_field():
    found = _names(tool_search("competing hypotheses"))
    assert "record_evidence_record" in found, found


def test_single_keyword_matching_still_works():
    found = _names(tool_search("hypothesis"))
    assert found, "single keyword should still match something"


def test_all_tokens_required_so_unrelated_words_do_not_flood():
    found = _names(tool_search("kitchen sink plan"))
    assert "record_analysis_plan" not in found, found


def test_registered_search_exposes_keyword_to_the_model():
    tool = registry.get("tool_search")
    assert tool is not None
    assert set(tool.parameters["properties"]) == {"keyword"}
    assert tool.parameters["required"] == ["keyword"]


def test_registered_search_dispatch_reaches_and_activates_capability():
    registry.reset_groups()
    try:
        assert "eda" not in registry._get_active_groups()
        result = registry.execute("tool_search", {"keyword": "synthesize"})
        assert "synthesize_time_series" in _names(result.summary), result.summary
        assert "eda" in registry._get_active_groups()
    finally:
        registry.reset_groups()

# Complete search scope and normal app path.
from pathlib import Path
import json,io,hashlib
import pytest
from tests.test_trusted_publication_semantics import engine
from tests.test_trusted_publication_runtime import _NativeProductModel
from data_agent.tools.registry import registry,tool_search
_DISCOVERY_OUT=Path('tmp/s3-tool-discovery-20261013-r1')
_DISCOVERY_CASE_OUT=_DISCOVERY_OUT
def _discovery_inventory():
 return [{k:getattr(t,k) for k in ['name','description','parameters']} for t in registry._tools.values()]
def _save_discovery(name,value):
 _DISCOVERY_CASE_OUT.mkdir(parents=True,exist_ok=True)
 with (_DISCOVERY_CASE_OUT/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
def _discovery_complete(value):
 return value['matches']==value['returned']==len(value['tools'])
@pytest.mark.parametrize('keyword',['name','data'])
@pytest.mark.parametrize('route',['direct','registry'])
def test_search_does_not_silently_drop_matches(engine,monkeypatch,route,keyword):
 _,cfg=engine;monkeypatch.setitem(globals(),'_DISCOVERY_CASE_OUT',_DISCOVERY_OUT/'evidence'/cfg.sessions_resolved.parents[1].name)
 result=json.loads(tool_search(keyword) if route=='direct' else registry.execute('tool_search',{'keyword':keyword}).summary)
 _save_discovery(route+'_'+keyword+'.json',{'result':result,'registered_tools':_discovery_inventory(),'active_groups':sorted(registry._get_active_groups()),'active_definitions':registry.active_definitions(),'provider_calls':0})
 assert _discovery_complete(result)
@pytest.mark.parametrize('keyword',['name','data'])
def test_normal_app_discovery_scope_is_transparent_and_data_answer_remains_real(engine,monkeypatch,keyword):
 from data_agent.web.app import create_app
 from data_agent.web.agent_manager import AgentManager
 from data_agent.session.history import load_session
 from data_agent.agent.publication.runtime import read_answer
 from data_agent.tools.report import export_assistant_reply
 _,cfg=engine;monkeypatch.setitem(globals(),'_DISCOVERY_CASE_OUT',_DISCOVERY_OUT/'evidence'/cfg.sessions_resolved.parents[1].name);sid='tool_discovery_'+keyword
 content='分析上传数据，将其命名为experiment；先检索关键词'+keyword+'的可用工具供后续选择；本次正式结果只报告实际记录数，工具目录不当作数据事实。'
 class Observe(_NativeProductModel):
  def chat(self,*args,**kwargs):
   self.schemas_seen.append(kwargs.get('tools'))
   return super().chat(*args,**kwargs)
 script=Observe(content,'experiment','describe_dataset',{'name':'experiment'},[{'kind':'measurement','scope':{'datasets':['experiment'],'quantity':'rows'}}],[('tool_search',{'keyword':keyword})]);script.schemas_seen=[]
 manager=AgentManager(client_factory=lambda **kw:script,auxiliary_client_factory=lambda:script);app=create_app();app.config['agent_manager']=manager
 data=b'amount\n10\n20\n30\n'
 with app.test_client() as http:
  ticket=http.post('/api/upload',data={'file':(io.BytesIO(data),'experiment.csv')},content_type='multipart/form-data').get_json();script.ticket=ticket
  response=http.post('/api/chat',json={'session_id':sid,'message':content,'uploads':[ticket]})
  events=[(b.split('\n',1)[0][7:],json.loads(b.split('\ndata: ',1)[1])) for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
  refreshed=http.get('/api/sessions/'+sid).get_json()
 saved=load_session(sid);answer=read_answer(sid,saved['messages'][-1]['answer_ref']);result=json.loads(next(d['web']['summary'] for e,d in events if e=='tool_result' and d['name']=='tool_search'))
 export=export_assistant_reply(sid,answer['body'],'md');assert export['status']=='exported';md=cfg.sessions_resolved/sid/'reports'/export['artifact_path'].split('/')[-1]
 _save_discovery('normal_'+keyword+'.json',{'result':result,'registered_tools':_discovery_inventory(),'events':events,'answer':answer,'saved':saved,'refreshed':refreshed,'calls':script.calls,'schemas_seen':script.schemas_seen,'session_dir':str(cfg.sessions_resolved/sid),'csv_text':data.decode(),'upload_ticket':ticket,'export':export,'md_path':str(md),'provider_calls':0});(_DISCOVERY_CASE_OUT/('normal_'+keyword+'.md')).write_bytes(md.read_bytes())
 ends=[d for e,d in events if e=='turn_end'];assert len(ends)==1 and ends[0]['status']=='completed' and ends[0]['reply_content']==answer['body']
 req=answer['source_snapshot']['requirements'][0];delivered=[c for c in answer['source_snapshot']['claims'] if c['id'] in req['claim_ids']];assert len(delivered)==1 and delivered[0]['value']==3 and delivered[0]['label']=='记录数'
 assert all(p['tool_name']=='describe_dataset' for c in answer['source_snapshot']['claims'] for p in c['basis_refs'])
 assert saved['messages'][-1]['content']==answer['body'] and answer['body'] in md.read_text(encoding='utf-8')
 assert any(m.get('answer_ref')==saved['messages'][-1]['answer_ref'] for m in refreshed['messages'])
 assert _discovery_complete(result)

@pytest.mark.parametrize('route',['direct','registry'])
@pytest.mark.parametrize('keyword',['name','data','column','analysis plan','competing hypotheses','synthesize','kitchen sink plan'])
def test_complete_discovery_preserves_scores_order_and_summary_range(engine,monkeypatch,route,keyword):
 _,cfg=engine;monkeypatch.setitem(globals(),'_DISCOVERY_CASE_OUT',_DISCOVERY_OUT/'evidence'/cfg.sessions_resolved.parents[1].name)
 definitions=_discovery_inventory();kw=keyword.lower().strip();tokens=[t for t in __import__('re').split(r'[\s,;/]+',kw.replace('_',' ')) if t];expected=[]
 for t in definitions:
  text=' '.join([t['name'],t['description'],json.dumps(t['parameters'],ensure_ascii=False)]).lower().replace('_',' ');score=4 if kw in t['name'].lower() else 0
  if tokens and all(token in text for token in tokens):score+=2*len(tokens)+int(kw in t['description'].lower())
  if score:expected.append((t['name'],score,t['description']))
 expected.sort(key=lambda item:-item[1])
 result=json.loads(tool_search(keyword) if route=='direct' else registry.execute('tool_search',{'keyword':keyword}).summary)
 _save_discovery('scope_'+route+'_'+keyword.replace(' ','_')+'.json',{'result':result,'registered_tools':definitions,'expected':expected,'provider_calls':0})
 assert result['matches']==result['returned']==len(expected)==len(result['tools'])
 assert [(t['name'],t['relevance']) for t in result['tools']]==[(n,s) for n,s,d in expected]
 assert [(t['description'],t['description_truncated']) for t in result['tools']]==[(d[:200],len(d)>200) for n,s,d in expected]

@pytest.mark.parametrize('keyword',['',' ','\t\n'])
@pytest.mark.parametrize('route',['direct','registry'])
def test_empty_discovery_keeps_explicit_error_and_does_not_expand(engine,keyword,route):
 before=set(registry._get_active_groups());result=json.loads(tool_search(keyword) if route=='direct' else registry.execute('tool_search',{'keyword':keyword}).summary)
 assert result.get('error') and registry._get_active_groups()==before

@pytest.mark.parametrize('value',[True,1,1.0,None])
def test_registry_discovery_invalid_keyword_does_not_expand(engine,value):
 before=set(registry._get_active_groups());result=registry.execute('tool_search',{'keyword':value})
 assert json.loads(result.summary).get('error') and registry._get_active_groups()==before

def test_discovery_expansion_stays_with_current_agent_context(engine):
 from data_agent.agent.context import AgentContext,use_agent_context
 first=AgentContext('discovery_first');second=AgentContext('discovery_second')
 with use_agent_context(first):
  result=json.loads(tool_search('synthesize'));assert any(t['name']=='synthesize_time_series' for t in result['tools']);assert 'eda' in registry._get_active_groups()
 with use_agent_context(second):assert registry._get_active_groups()=={'core'}
 with use_agent_context(first):assert 'eda' in registry._get_active_groups()

def test_search_discovers_before_matching_and_uses_existing_expansion(engine,monkeypatch):
 import data_agent.tools as package
 calls=[];before=package.discover_tools
 monkeypatch.setattr(registry,'_discovered',False)
 def discover():calls.append(True);before()
 monkeypatch.setattr(package,'discover_tools',discover)
 result=json.loads(tool_search('synthesize'));assert calls==[True] and any(t['name']=='synthesize_time_series' for t in result['tools']) and 'eda' in registry._get_active_groups()

