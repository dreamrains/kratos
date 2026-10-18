"""Public-input model and session fixtures shared by publication contract tests."""
from copy import deepcopy
from data_agent.agent.publication.contracts import encode
from types import SimpleNamespace

def request(loop,content,delivery=None,kind="result",purposes=None,source_answer_id=None):
    if not hasattr(loop,"_turn_tools_used"):loop._reset_turn_tracking()
    from data_agent.session.history import save_session
    from data_agent.agent.publication.requirements import update_requirements
    from data_agent.session.history import load_canonical_history
    loop.messages.append({"role":"user","content":content,"request_id":"msg_runtime_"+str(len(loop.messages))})
    save_session(loop.messages,loop.session_id,extra_meta={"publication_schema":"answer_bindings.v2"},merge_protect=False)
    loop._last_jsonl_idx=len(loop.messages)
    proposed={"op":"add","start":0,"end":len(content),"kind":kind}
    if purposes: proposed["purposes"]=purposes
    if source_answer_id: proposed["source_answer_id"]=source_answer_id
    specs=delivery if isinstance(delivery,list) else [delivery] if delivery else []
    if specs:
        from data_agent.agent.publication.deliveries import validate_business_scope
        for d in specs:validate_business_scope(d["scope"],required=True,operation=d["kind"]=="operation")
        proposed["business_scope"]=deepcopy(specs[0]["scope"]) if len(specs)==1 else {"datasets":sorted({n for d in specs for n in d["scope"].get("datasets",[])})}
    ids=update_requirements(loop.context.analysis_state,load_canonical_history(loop.session_id),loop.messages[-1]["request_id"],[proposed],expected_revision=loop.context.analysis_state.requirement_revision)
    if delivery:
        from tests.support.plan_inputs import declare_goal_deliveries
        declare_goal_deliveries(loop,[(ids[0],d["kind"],d["scope"]) for d in specs])
    loop.context.turn_intent=SimpleNamespace(intent_type="knowledge_qa" if kind=="knowledge" else "directed_analysis")
    loop._publication_turn_id="runtime_turn"
    loop.context.turn_requirement_ids=ids


def draft(snapshot):
    host=snapshot.as_dict()
    return encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":[{"requirement_ids":[r["id"] for r in host["requirements"] if not r["withdrawn"]],"parts":[{"kind":"claim","ref":c["id"]} for c in [c for c in host["claims"] if any(c["id"] in r.get("claim_ids",[]) for r in host["requirements"] if not r["withdrawn"])][:64]]}]})


class AppClient:
    def __init__(self,loop,tool=None,args=None):
        self.loop,self.tool,self.args,self.called=loop,tool,args,0
    def chat(self,messages,system="",tools=None,**kw):
        from data_agent.llm.client import Response,ToolCall
        from data_agent.agent.publication.runtime import snapshot_for_turn
        if self.tool and not getattr(self,"planned",False):
            self.planned=True
            state=self.loop.context.analysis_state
            from data_agent.tools.data_io import _record_trust_workflow
            for name in self.loop.context.workspace.list_datasets():
                if not any(c.get("dataset")==name for c in state.dataset_contracts):
                    _record_trust_workflow(session_id=self.loop.session_id,state=state,dataset=name,df=self.loop.context.workspace.get(name),applied=[],needs_confirm=[],quality={},interpretation_data={},detail_path="")
            steps=(state.analysis_plan or {}).get("method_plan",[])
            if steps and set(self.loop.context.turn_requirement_ids).issubset({rid for step in steps for rid in step["requirement_ids"]}):
                plan=deepcopy(state.analysis_plan);plan["requirement_revision"]=state.requirement_revision
                for step in plan["method_plan"]:step["required_deliveries"]=[{"id":d["id"]} for d in step["required_deliveries"]]
            else:
                factual=[r for r in state.answer_requirements if r.get("lifecycle_status")=="active" and r["id"] in self.loop.context.turn_requirement_ids and r["semantic_kind"]=="result"]
                declarations=[]
                for r in factual:
                    scope=deepcopy(r.get("business_scope",{}));scope.setdefault("datasets",["orders"]);scope.setdefault("quantity","rows")
                    for name in scope["datasets"]:
                        declarations.append({"requirement_id":r["id"],"kind":"measurement","label":r["original_text"]+" / "+name,"scope":dict(scope,datasets=[name])})
                plan={"contract_version":"stage3c0b.v2","requirement_revision":state.requirement_revision,"goal":"App fixture declared goals","method_plan":[{"step_id":"app","goal":"Execute original goals","expected_output":"Declared products","dataset_inputs":sorted({n for d in declarations for n in d["scope"]["datasets"]}),"combination_mode":"independent","evidence_requirements":["receipt"],"required_deliveries":declarations}],"visualization_strategy":[]}
            if plan["method_plan"][0]["required_deliveries"]:
                return Response(tool_calls=[ToolCall("app_plan","record_analysis_plan",{"plan_json":plan})])
        self.called+=1
        if self.tool and self.called==1:
            return Response(tool_calls=[ToolCall("app_native",self.tool,self.args)])
        snapshot=snapshot_for_turn(self.loop)
        host=snapshot.as_dict()
        parts=[{"kind":"claim","ref":c["id"]} for c in host["claims"] if any(c["id"] in r.get("claim_ids",[]) for r in host["requirements"] if not r["withdrawn"])]+[{"kind":"artifact","ref":a["id"]} for a in host["artifacts"] if any(a["id"] in r.get("artifact_ids",[]) for r in host["requirements"] if not r["withdrawn"])]
        if host["mode"]=="consultation":
            parts=[{"kind":"text","purpose":"knowledge","text":"回归描述变量间的条件关系，不证明因果。","claim_refs":[]}]
        return Response(text=encode({"schema":"answer_bindings.v2","snapshot_digest":snapshot.digest,"sections":[{"requirement_ids":[r["id"] for r in host["requirements"] if not r["withdrawn"]],"parts":parts}]}))
    def stream_chat_structured(self,*args,**kwargs):
        from data_agent.llm.client import StreamTextDelta,StreamComplete
        response=self.chat(*args,**kwargs)
        yield StreamTextDelta(response.text)
        yield StreamComplete(response)


def intent_for_app(monkeypatch,kind,content,scope=None):
    from data_agent.agent.intent import TurnIntent
    mode="knowledge_qa" if kind=="knowledge" else "data_operation"
    result=TurnIntent(mode,"clear","data_loaded","execute","answer_directly" if kind=="knowledge" else "execute_operation",execution_readiness="ready",requested_outputs=[{"kind":kind,"exact_span":content,**({"business_scope":scope} if scope else {})}])
    import data_agent.agent.intent as intent
    monkeypatch.setattr(intent,"plan_turn_intent",lambda *a,**kw:result)


class _NativeProductModel:
    """One public-only model fixture; never reads state, receipts or workspace."""
    def __init__(self,content,dataset,tool,args,specs,preparatory_calls=()):
        self.content,self.dataset,self.tool,self.args,self.specs=content,dataset,tool,args,specs
        self.preparatory_calls=list(preparatory_calls)
        self.ticket=None;self.calls=[];self.step=0
    def chat(self,messages,system="",tools=None,**kw):
        from data_agent.llm.client import Response,ToolCall
        from scripts.testing.run_p7_browser_rehearsal import ScriptedClient
        if system=="你是一个JSON输出器，只返回JSON，不要其他内容。":
            return Response(text=encode({"intent_type":"directed_analysis","requested_outputs":[{"kind":"result","exact_span":self.content,"business_scope":({"datasets":[self.dataset]} if self.dataset else {})}],"upload_bindings":[{"upload_id":self.ticket["upload_id"],"dataset":self.dataset,"relation":"new","exact_span":"将其命名为"+self.dataset}] if self.dataset else []}))
        view=ScriptedClient._current_host_snapshot(messages,system)
        if view.get("model_view_issue"):
            return Response(text=encode({"schema":"answer_bindings.v2","snapshot_digest":view["snapshot_digest"],"sections":[]}))
        self.step+=1
        ordinal=self.step if self.dataset else self.step+1
        if ordinal<=3+len(self.preparatory_calls):
            if ordinal==1:name,args="describe_dataset",{"name":self.dataset}
            elif ordinal==2:
                goal=next(r for r in view["execution_targets"] if r["semantic_kind"]=="result")
                declarations=[dict(d,requirement_id=goal["id"],label="原工具业务产物 "+str(i)) for i,d in enumerate(self.specs)]
                name,args="record_analysis_plan",{"plan_json":{"contract_version":"stage3c0b.v2","requirement_revision":view["requirement_revision"],"goal":self.content,"visualization_strategy":[],"method_plan":[{"step_id":"native_product","goal":self.content,"expected_output":"原方法、指标和来源的业务产物","dataset_inputs":[self.dataset] if self.dataset else [],"evidence_requirements":["original receipt"],"required_deliveries":declarations}]}}
            elif ordinal<3+len(self.preparatory_calls):name,args=self.preparatory_calls[ordinal-3]
            else:name,args=self.tool,self.args
            self.calls.append(name)
            return Response(tool_calls=[ToolCall("native_call_"+str(self.step),name,args)])
        return Response(text=encode({"schema":"answer_bindings.v2","snapshot_digest":view["snapshot_digest"],"sections":[{"requirement_ids":[r["id"]],"parts":[{"kind":"claim","ref":cid} for cid in r["claim_ids"]]+[{"kind":"effect","ref":eid} for eid in r.get("effect_ids",[])]} for r in view["requirements"] if not r["withdrawn"]]}))
    def stream_chat_structured(self,*args,**kwargs):
        from data_agent.llm.client import StreamTextDelta,StreamComplete
        response=self.chat(*args,**kwargs)
        if response.text:yield StreamTextDelta(response.text)
        yield StreamComplete(response)

