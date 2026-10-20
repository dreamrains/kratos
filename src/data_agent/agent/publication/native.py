"""Closed adapters for original descriptive measurements; no prose parsing."""
from copy import deepcopy
from datetime import datetime
import math

from .contracts import ContractError, encode, digest, fields
from .facts import load_receipt_result, resolve_artifact, resolve_result_claim


RESULT_FIELDS = {
    "list_mcp_servers": ("servers","health"),
    "list_skills": ("skills",),
    "read_file": ("content",),
    "list_files": ("entries",),
    "interpret_dataset": ("columns_classified","column_role_basis","grain_basis","theme_basis","date_observation","time_range","analysis_signals","data_shape","suggested_analyses","cross_dataset_hints"),
    "suggest_column_types": ("suggestions","observation"),
    "list_data": ("datasets", "transform_history"),
    "curve_fitting": ("points","fits","scenarios","sensitivity","effective_n","parameters","zero_value_semantics","claim_ceiling","status"),
    "derive_field": ("rows","preserved_columns"),
    "transform_data": ("rows","columns","measurement_records","operation","source_observation","resample_audit"),
    "run_python": ("result_data",),
    "analyze_time_series": ("data_points","statistics","trend","window_comparisons","change_points","autocorrelation","seasonality","date_range","observation"),
    "synthesize_time_series": ("aligned_data","aligned_rows","coverage","observation","missing_aligned_dates","source_identities"),
    "top_n": ("records","sort_by","ascending","n","parameters","observation"),
    "preview_data": ("data","rows","columns","shape"),
    "quick_profile": ("shape","columns","quality","grain","grain_hint","readiness","warnings","summary","column_diagnostics","suggested_next","suggested_analyses"),
    "assess_readiness": ("overall","findings","recommendations","rows","cols","column_diagnostics"),
    "detect_data_quality": ("issues","total_issues","summary"),
    "correlation_analysis": ("columns_analyzed","correlation_matrix","pairwise_counts","excluded_columns","high_correlations","method"),
    "distribution_analysis": ("columns",),
    "segmentation_analysis": ("clusters","requested_n_clusters","n_clusters","total_samples","observation","parameters","analysis_unit","status"),
    "cohort_analysis": ("cohorts","observation","age_axis","observation_window","analysis_unit","cohort_definition","right_censoring","final_month_incomplete","parameters","status"),
    "contribute_decomposition": ("decomposition","total_change","total_change_pct","period_a","period_b","comparability","daily_normalized","observation","parameters","status"),
    "funnel_analysis": ("steps","overall_conversion","biggest_drop","dimension_funnels","analysis_unit","temporal_order_verified","step_order","parameters","status"),
    "ab_test": ("groups","difference","test","method","design","analysis_unit","unit_aggregation","paired_sample_size","excluded_unpaired_units","contingency_table","wilcoxon_signed_rank","limitations"),
    "forecast": ("forecast","backtest","interval","observation","date_range"),
    "classification": ("metrics","feature_importance","method","n_classes","train_size","test_size","cv","validation","class_metrics","label_mapping","positive_class","confusion_matrix","coefficients_by_class"),
    "regression_analysis": ("metrics","coefficients","feature_importance","method","train_size","test_size","cv","validation"),
    "causal_analysis": ("did_effect","ci_95","standard_error","p_value","group_means","cell_counts","total_observations","assumptions","status","reason_code","method"),
    "shap_analysis": ("shap_importance","per_class_importance","aggregation","unexplained_classes","model_identity","model_type","target","n_observations","status","claim_ceiling"),
    "attribution_analysis": ("estimates","bivariate_associations","observation","excluded_features","unstable_features","vif","unit_observation","time_observation","effective_n"),
    "what_if_simulation": ("baseline","projected","impact","breakdown","optimal_changes","achieved_target","constraints","mode","target","goal_pct","status","baseline_total","gap","required_total_pct"),
}


# Published producer contracts point to this unique closed adapter. They do not
# authorize model-selected paths or confer method validity beyond native proofs.
MINIMAL_PRODUCT_CONTRACTS={
    "list_mcp_servers":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{}},
    "list_skills":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{}},
    "read_file":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{}},
    "list_files":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{}},
    "interpret_dataset":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{}},
    "suggest_column_types":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{}},
    "detect_data_quality":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{}},
    "preview_data":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{"n":"preview_n"}},
    "list_data":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{}},
    "analyze_time_series":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{"date_col":"time_series_date_col","value_col":"time_series_value_col"}},
    "attribution_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{"features":"factor_features","unit_col":"factor_unit_col","time_col":"factor_time_col"}},
    "contribute_decomposition":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{"dimension":"decomposition_dimension","agg_func":"decomposition_aggregation","date_col":"decomposition_date_col","period_a":"period_a","period_b":"period_b"}},
    "top_n":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement","operation"],"parameters":{"sort_by":"topn_sort_by","ascending":"topn_ascending","n":"topn_n","columns":"topn_columns"}},
    "segmentation_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{"features":"segmentation_features","n_clusters":"segmentation_n_clusters"}},
    "cohort_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{"user_col":"cohort_user_col","time_col":"cohort_time_col","event_col":"cohort_event_col"}},
    "funnel_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{"mode":"funnel_mode","steps":"funnel_steps","dimension":"funnel_dimension","window_hours":"funnel_window_hours"}},
    "what_if_simulation":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["scenario"],"parameters":{"mode":"simulation_mode","goal_pct":"goal_pct","constraints":"allocation_constraints"}},
    "classification":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["fit","measurement"],"parameters":{"requested_method":"classification_method","cv_folds":"cv_folds"}},
    "regression_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["fit","measurement"],"parameters":{"requested_method":"regression_method","cv_folds":"cv_folds"}},
    "shap_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{"model_identity.kind":"model_kind","aggregation":"shap_aggregation"}},
    "ab_test":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["measurement","table"],"parameters":{"requested_method":"ab_method","design":"ab_design","analysis_unit":"ab_unit","unit_aggregation":"unit_aggregation"}},
    "causal_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["measurement","table"],"parameters":{"method":"causal_method"}},
    "correlation_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table","measurement"],"parameters":{"method":"correlation_method"}},
    "compare_periods":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["measurement","table"],"parameters":{"date_col":"comparison_date_col","dimensions":"comparison_dimensions","metric_formulas":"comparison_formulas","period_a":"period_a","period_b":"period_b"}},
    "quick_profile":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{"compact":"profile_compact"}},
    "assess_readiness":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["table"],"parameters":{"intent":"readiness_intent"}},
    "describe_dataset":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["measurement"],"parameters":{}},
    "distribution_analysis":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["measurement","table"],"parameters":{}},
    "forecast":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["forecast","table"],"parameters":{"periods":"forecast_periods","date_col":"forecast_date_col","method":"forecast_method"}},
    "synthesize_time_series":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["series","table","measurement"],"parameters":{"date_col":"synthesis_date_col","metrics":"synthesis_metrics"}},
    "curve_fitting":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_native_claims","kinds":["series","fit","scenario","measurement","table"],"parameters":{"zero_values":"zero_values","scenario_points":"scenario_points","weight_col":"curve_weight_col","mature_through_col":"curve_mature_through_col","value_scale":"curve_value_scale","compare_weights":"curve_compare_weights"}},
    "derive_field":{"version":"native_business_product.v1","adapter":"data_agent.agent.publication.native.resolve_operation_effect","kinds":["operation"],"effect":"derived_dataset_with_verified_parent"},
}


DATASET_OPERATIONS=frozenset({"derive_features","derive_field","clean_data","apply_type_conversion","transform_data","top_n","synthesize_time_series"})
FILE_OPERATIONS=frozenset({"write_file","edit_file"})
SKILL_OPERATIONS=frozenset({"load_skill","unload_skill","enable_skill","disable_skill","delete_skill"})
RULE_OPERATIONS=frozenset({"update_project_rules"})
KNOWLEDGE_OPERATIONS=frozenset({"create_knowledge_item"})
MEMORY_OPERATIONS=frozenset({"create_memory_candidate","confirm_memory"})
MCP_CONFIG_OPERATIONS=frozenset({"add_mcp_server","enable_mcp_server","disable_mcp_server","delete_mcp_server"})
CONVERSATION_OPERATIONS=frozenset({"export_conversation"})
OPERATION_TOOLS=CONVERSATION_OPERATIONS | MCP_CONFIG_OPERATIONS | DATASET_OPERATIONS | FILE_OPERATIONS | SKILL_OPERATIONS | RULE_OPERATIONS | KNOWLEDGE_OPERATIONS | MEMORY_OPERATIONS


def operation_requested(action,arguments):
    return action in OPERATION_TOOLS and (action not in {"top_n","synthesize_time_series"} or bool(arguments.get("save_as")))


def operation_spec(action,arguments):
    import inspect
    from jsonschema import Draft7Validator
    from data_agent.tools.registry import registry
    tool=registry.get(action)
    if action not in OPERATION_TOOLS or tool is None or not isinstance(arguments,dict):
        raise ContractError("operation_action","未知操作或参数对象。")
    errors=list(Draft7Validator(tool.parameters).iter_errors(arguments))
    if errors:raise ContractError("operation_arguments",errors[0].message)
    try:
        bound=inspect.signature(tool.func).bind(**arguments);bound.apply_defaults()
    except TypeError as exc:raise ContractError("operation_arguments",str(exc)) from exc
    args=dict(bound.arguments)
    if action in CONVERSATION_OPERATIONS and args.get("reply_target")=="conversation":
        args.pop("reply_target")  # Preserve historical normalized operation identities.
    if not operation_requested(action,args):raise ContractError("operation_arguments","TopN 操作交付须指定 save_as 新对象。")
    if action=="transform_data":
        import json
        from data_agent.tools.data_transform import _transform_parameters
        args={"name":args["name"],"operation":args["operation"],"save_as":args["save_as"],
            "params":json.dumps(_transform_parameters(args),ensure_ascii=False,sort_keys=True,separators=(",",":"))}
    if action in CONVERSATION_OPERATIONS:
        from data_agent.tools.report import _conversation_format
        args["format"]=_conversation_format(args["format"])
    result={"action":action,"arguments":args};encode(result);return result


def operation_sources(action,arguments):
    if action=="synthesize_time_series":
        from data_agent.tools.multifile import _synthesis_parameters
        return _synthesis_parameters(arguments)[0]
    if action=="transform_data":
        from data_agent.tools.data_transform import _transform_sources
        return _transform_sources(arguments)
    return [arguments["name"]] if action in DATASET_OPERATIONS else []


def _file_state(path):
    import hashlib
    if path.exists() and not path.is_file():raise ContractError("operation_file","操作对象不是文件。")
    return {"exists":path.is_file(),"sha256":"sha256:"+hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def _operation_path(action,args):
    from data_agent.tools.file_ops import _safe_path,_get_session_output_dir
    from data_agent.tools._utils import sanitize_filename
    if action=="write_file":
        directory=_get_session_output_dir()
        if directory is None:raise ContractError("operation_session","文件交付需要当前会话。")
        path=args["path"].replace("\\","/")
        resolved=_safe_path(path) if path.startswith(("output/","sessions/")) else directory/sanitize_filename(path)
        if not resolved.resolve().is_relative_to(directory.resolve()):raise ContractError("operation_permission","写入越过当前会话输出范围。")
        return resolved
    return _safe_path(args["path"])


def _global_rule_target():
    from data_agent.config import get_config
    from data_agent.tools import knowledge_tools
    knowledge_tools._ensure_instances()
    rules=knowledge_tools._project_rules
    path=rules.path.resolve()
    if path!=(get_config().knowledge_dir/"project_rules.md").resolve():
        raise ContractError("operation_permission","全局规则对象不是配置的规则文件。")
    return rules,path


def _global_knowledge_target():
    from data_agent.config import get_config
    from data_agent.tools import knowledge_tools
    library=knowledge_tools._library();root=get_config().knowledge_dir.resolve()
    if (library.root.resolve()!=root or library.db.path.resolve()!=root/"knowledge.sqlite3"
            or library.library_dir.resolve()!=root/"library"):
        raise ContractError("operation_permission","知识库对象不是配置的全局知识目录及数据库。")
    return library,root


def _knowledge_record(item):
    from dataclasses import asdict
    record=asdict(item);record["status"]=item.status.value;record["source"]=item.source.value
    return record


def _global_memory_target():
    from data_agent.config import get_config
    from data_agent.tools import knowledge_tools
    store=knowledge_tools._memory();root=get_config().knowledge_dir.resolve()
    if store.root.resolve()!=root or store.db.path.resolve()!=root/"knowledge.sqlite3":
        raise ContractError("operation_permission","记忆对象不是配置的全局记忆目录及数据库。")
    return store,root


def _memory_record(item):
    from dataclasses import asdict
    record=asdict(item);record["type"]=item.type.value;record["status"]=item.status.value
    return record


def _resolve_memory_effect(session_id,action,args,before,result):
    store,root=_global_memory_target();old=before.get("object_before",{})
    def reject():raise ContractError("operation_memory","实际记忆条目、状态或完整元数据与执行前对象、参数或原回执不一致。")
    if (before.get("permission_scope")!="configured_global_memory" or old.get("root")!=str(root)
            or old.get("database_path")!=str(store.db.path.resolve()) or not isinstance(result.get("id"),str)):
        reject()
    item=store.get(result["id"])
    if item is None:reject()
    record=_memory_record(item)
    public_keys={"id","type","text","summary","status","confidence","domain","tags","source_session_id","project_id",
                 "updated_at","reason","source_evidence_ids","needs_review","review_note","dedup_key"}
    if (set(result)!=public_keys|{"state","before"} or result["state"]!=record
            or any(result[k]!=record[k] for k in public_keys)):
        reject()
    if action=="create_memory_candidate":
        if (not isinstance(old.get("existing_ids"),list) or record["id"] in old["existing_ids"]
                or result["before"] is not None or not record["created_at"]):reject()
        expected={"id":record["id"],"type":args["memory_type"],"text":args["text"],"summary":args["summary"],
                  "status":"candidate","confidence":float(args["confidence"]),"source_session_id":session_id,
                  "source_message_ids":[],"source_tool_call_ids":[],"project_id":"","domain":args["domain"].strip() or "general",
                  "tags":args["tags"] or [],"last_used_at":"","hit_count":0,"created_at":record["created_at"],
                  "updated_at":record["created_at"],"promotion_target":"none","reason":"","source_evidence_ids":[],
                  "needs_review":False,"review_note":"","dedup_key":""}
        previous=None;changed=True
    else:
        previous=old.get("record")
        if (not isinstance(previous,dict) or previous.get("id")!=args["memory_id"] or record["id"]!=args["memory_id"]
                or old.get("sha256")!=digest(encode(previous)) or result["before"]!=previous
                or previous.get("status") not in {"candidate","confirmed"}):reject()
        expected=deepcopy(previous);changed=previous["status"]=="candidate"
        if changed:
            if not record["updated_at"]:reject()
            expected.update(status="confirmed",confidence=min(0.95,previous["confidence"]+0.15),updated_at=record["updated_at"])
    if record!=expected:reject()
    identity={"sha256":digest(encode(record)),"status":record["status"]}
    return ({"kind":"memory","name":item.id,"identity":identity},
            {"details":{"memory":record,"changed":changed,"transition":{"from":previous["status"] if previous else None,"to":record["status"]}}})


def _skill_state(name):
    from data_agent.tools.skill_tools import _loader
    loader=_loader();skill=loader.get(name)
    if skill is None:return {"exists":False,"enabled":False,"loaded":False,"path":None,"sha256":None}
    path=skill.path.resolve()
    if not any(path.is_relative_to(root.resolve()) for root in loader._dirs):raise ContractError("operation_permission","扩展对象不在配置目录内。")
    return {"exists":True,"enabled":skill.enabled,"loaded":name in loader._loaded,"path":str(path),"sha256":_file_state(path)["sha256"]}


def capture_operation_binding(context,action,arguments):
    if not operation_requested(action,arguments):return None
    spec=operation_spec(action,arguments);args=spec["arguments"]
    before={"session_id":context.session_id,"operation":spec}
    if action in DATASET_OPERATIONS:
        names=operation_sources(action,args)
        identities={n:context.workspace.get_data_identity(n) for n in names}
        if any(not identity for identity in identities.values()):raise ContractError("operation_source","操作来源没有当前身份。")
        before.update(source_data_identities=identities,existing_objects=list(context.workspace.list_datasets()),permission_scope="current_task_dataset")
    elif action in CONVERSATION_OPERATIONS:
        from data_agent.tools.report import _conversation_source,_conversation_reports_root
        from data_agent.session.history import list_artifacts
        if args.get("reply_target")=="current_answer":
            before.update(source_reply=None,reports_root=str(_conversation_reports_root(context.session_id)),
                existing_artifact_paths=[r["path"] for r in list_artifacts(context.session_id)],permission_scope="current_session_reply_export")
        else:
            _,source=_conversation_source(context.session_id,args["include_charts"])
            before.update(source_snapshot=source,reports_root=str(_conversation_reports_root(context.session_id)),existing_artifact_paths=[r["path"] for r in list_artifacts(context.session_id)],permission_scope="current_session_conversation_export")
    elif action in FILE_OPERATIONS:
        path=_operation_path(action,args)
        before.update(object_before=dict(_file_state(path),path=str(path.resolve())),permission_scope="existing_safe_file_path")
        if action=="edit_file" and path.is_file():
            content=path.read_text(encoding="utf-8")
            before["expected_sha256"]=digest(content.replace(args["old_text"],args["new_text"],1)) if content.count(args["old_text"])==1 else None
        elif action=="write_file":before["expected_sha256"]=digest(args["content"])
    elif action in MEMORY_OPERATIONS:
        store,root=_global_memory_target()
        old={"root":str(root),"database_path":str(store.db.path.resolve())}
        if action=="create_memory_candidate":
            with store.db.connect() as conn:
                old["existing_ids"]=[r["id"] for r in conn.execute("SELECT id FROM memory_items ORDER BY id")]
        else:
            item=store.get(args["memory_id"])
            if item is None or item.status.value not in {"candidate","confirmed"}:
                raise ContractError("operation_memory_state","确认仅支持待审候选或已确认记忆；目标不存在或状态不支持。")
            old.update(record=_memory_record(item));old["sha256"]=digest(encode(old["record"]))
        before.update(object_before=old,permission_scope="configured_global_memory")
    elif action in KNOWLEDGE_OPERATIONS:
        library,root=_global_knowledge_target()
        with library.db.connect() as conn:
            existing_ids=[r["id"] for r in conn.execute("SELECT id FROM knowledge_items ORDER BY id")]
        before.update(object_before={"root":str(root),"database_path":str(library.db.path.resolve()),"existing_ids":existing_ids},
                      expected_sha256=digest(args["content"]),permission_scope="configured_global_knowledge")
    elif action in MCP_CONFIG_OPERATIONS:
        from data_agent.mcp.config import mcp_config_state
        from data_agent.config import get_config
        before.update(object_before=mcp_config_state(get_config().global_mcp_config_path), permission_scope="configured_global_mcp")
    elif action in RULE_OPERATIONS:
        _,path=_global_rule_target()
        before.update(object_before=dict(_file_state(path),path=str(path)),expected_sha256=digest(args["content"]),permission_scope="configured_global_rules")
    else:
        state=_skill_state(args["name"])
        if action=="delete_skill" and state["exists"]:
            from pathlib import Path
            from data_agent.tools.skill_tools import _loader
            loader=_loader();target=(loader._dirs[0]/args["name"]).resolve()
            if not target.is_relative_to(loader._dirs[0].resolve()) or target/"SKILL.md"!=Path(state["path"]):raise ContractError("operation_permission","删除扩展的实际目录与已发现对象不一致。")
        before.update(object_before=state,permission_scope="current_session_skills" if action in {"load_skill","unload_skill"} else "configured_global_skills")
    return before


def resolve_operation_effect(*,session_id,receipt_id):
    context,receipt,result,binding=load_receipt_result(session_id=session_id,receipt_id=receipt_id,operation=True)
    action=receipt["tool_name"]
    if not operation_requested(action,receipt["arguments"]):return None
    before=receipt.get("operation_binding")
    spec=operation_spec(action,receipt["arguments"])
    if not isinstance(before,dict) or before.get("session_id")!=session_id or before.get("operation")!=spec or not receipt.get("plan_id") or not receipt.get("required_delivery_ids"):
        raise ContractError("operation_predispatch","操作效果缺少执行前的计划、对象、参数和权限绑定。")
    if not isinstance(result,dict):raise ContractError("operation_result","操作结果必须结构化。")
    args=spec["arguments"];extra={}
    if action in CONVERSATION_OPERATIONS and args.get("reply_target")=="current_answer" and result.get("status")=="deferred":
        if before.get("permission_scope")!="current_session_reply_export" or before.get("source_reply") is not None:
            raise ContractError("operation_reply","Deferred current report has an invalid original binding.")
        return None
    if action in DATASET_OPERATIONS:
        target=result.get("dataset");identity=binding["data_identities"].get(target)
        sources=before.get("source_data_identities",{});names=operation_sources(action,args)
        if action=="transform_data":_validate_transform_result(receipt,result,binding)
        if action=="top_n":_validate_top_n_result(context,receipt,result)
        if action=="synthesize_time_series":_validate_time_synthesis_result(context,receipt,result)
        source_matches=(result.get("source_datasets")==names if action=="synthesize_time_series" else result.get("source_dataset")==args["name"])
        if not identity or target in before.get("existing_objects",[]) or not source_matches or not sources or set(sources)!=set(names) or identity.get("parent_version_ids")!=[sources.get(n,{}).get("version_id") for n in names] or any(binding["data_identities"].get(n)!=i for n,i in sources.items()):
            raise ContractError("operation_parent","实际新对象与执行前来源/父版本不一致。")
        if args.get("save_as") and args["save_as"]!=target:raise ContractError("operation_target","新对象不是指定目标。")
        obj={"kind":"dataset","name":target,"identity":deepcopy(identity)}
        if action=="synthesize_time_series":
            extra={"details":{"observation":deepcopy(result["observation"]),"missing_aligned_dates":deepcopy(result["missing_aligned_dates"])}}
            if result["completion_gaps"]:extra["completion_gap"]={"status":"evidence_insufficient","reason":"新对齐表已创建；"+" ".join(result["completion_gaps"])}
        elif action=="clean_data":extra=_cleaning_effect_details(context,args,result,target)
        elif action=="apply_type_conversion":extra=_conversion_effect_details(context,args,result,target)
        elif action=="transform_data" and args["operation"]=="resample":extra=_resample_effect_details(context,args,result)
    elif action in CONVERSATION_OPERATIONS:
        obj,extra=_resolve_conversation_effect(session_id,args,before,result)
    elif action in FILE_OPERATIONS:
        path=_operation_path(action,args);current=_file_state(path)
        if str(path.resolve())!=before["object_before"]["path"] or current["sha256"]!=before.get("expected_sha256") or not current["exists"] or result.get("sha256")!=current["sha256"]:
            raise ContractError("operation_file","实际文件字节与执行前参数或原回执不一致。")
        from data_agent.tools.file_ops import _safe_path
        if _safe_path(result["path"]).resolve()!=path.resolve():raise ContractError("operation_target","文件结果引用与实际对象不同。")
        obj={"kind":"file","name":result["path"],"identity":current}
    elif action in MEMORY_OPERATIONS:
        obj,extra=_resolve_memory_effect(session_id,action,args,before,result)
    elif action in KNOWLEDGE_OPERATIONS:
        from data_agent.knowledge.library import _safe_domain
        library,root=_global_knowledge_target();old=before.get("object_before",{})
        def reject_knowledge():raise ContractError("operation_knowledge","实际新知识条目、正文、数据库元数据与执行前对象、参数或原回执不一致。")
        if (before.get("permission_scope")!="configured_global_knowledge" or old.get("root")!=str(root)
                or old.get("database_path")!=str(library.db.path.resolve())
                or before.get("expected_sha256")!=digest(args["content"])
                or not isinstance(old.get("existing_ids"),list) or not isinstance(result.get("id"),str)
                or result["id"] in old["existing_ids"]):reject_knowledge()
        item=library.get(result["id"])
        if item is None:reject_knowledge()
        record=_knowledge_record(item)
        expected={"title":args["title"],"domain":_safe_domain(args["domain"]) if args["domain"].strip() else "general",
                  "content":args["content"],"summary":args["summary"],"tags":args["tags"] or [],
                  "version":1,"status":"active","source":"user","deprecated_at":"","supersedes":"","superseded_by":""}
        path=library._resolve_library_path(item.path);current=_file_state(path)
        if (record!=result or any(record[k]!=v for k,v in expected.items()) or not record["created_at"]
                or record["created_at"]!=record["updated_at"] or not current["exists"]
                or current["sha256"]!=before["expected_sha256"]):reject_knowledge()
        metadata={k:v for k,v in record.items() if k!="content"}
        obj={"kind":"file","name":item.path.replace("\\","/"),"identity":dict(current,path=str(path),database_path=str(library.db.path.resolve()),knowledge=metadata)}
        extra={"details":{"knowledge":metadata}}
    elif action in MCP_CONFIG_OPERATIONS:
        from data_agent.mcp.config import MCPConfig, mcp_config_state
        from data_agent.tools.mcp_tools import _next_mcp_config
        from data_agent.config import get_config
        current=mcp_config_state(get_config().global_mcp_config_path);old=before.get("object_before",{})
        try:
            expected=_next_mcp_config(MCPConfig(**old["configuration"]),action,args)
        except (KeyError,TypeError,ValueError) as exc:
            raise ContractError("operation_mcp","执行前MCP配置无效。") from exc
        if (before.get("permission_scope")!="configured_global_mcp" or old.get("path")!=current["path"]
                or set(result)!={"path","before","state"} or result.get("path")!=current["path"]
                or result.get("before")!=old or result.get("state")!=current or not current["exists"]
                or expected is None or current["configuration"]!=expected.model_dump(exclude_none=True)
                or binding["data_identities"]):
            raise ContractError("operation_mcp","实际MCP配置、文件摘要与执行前对象、完整参数或原回执不一致。")
        obj={"kind":"file","name":"global/mcp_servers.yaml","identity":deepcopy(current)}
        extra={"details":{"server":args["name"],"changed":old["configuration"]!=current["configuration"],
            "boundary":"仅核验全局配置保存；未核验连接、断连或远端执行状态。"}}
    elif action in RULE_OPERATIONS:
        rules,path=_global_rule_target();current=_file_state(path);old=before.get("object_before",{})
        expected=digest(args["content"])
        if (old.get("path")!=str(path) or before.get("permission_scope")!="configured_global_rules"
                or before.get("expected_sha256")!=expected or not current["exists"] or current["sha256"]!=expected
                or result.get("path")!=str(path) or result.get("state")!=current
                or result.get("before")!={k:old.get(k) for k in ("exists","sha256")}
                or rules.content!=args["content"]):
            raise ContractError("operation_rules","实际全局规则文件、提示内容与执行前对象、参数或原回执不一致。")
        obj={"kind":"file","name":"global/project_rules.md","identity":dict(current,path=str(path))}
    else:
        current=_skill_state(args["name"]);old=before["object_before"]
        expected={"load_skill":("loaded",True),"unload_skill":("loaded",False),"enable_skill":("enabled",True),"disable_skill":("enabled",False),"delete_skill":("exists",False)}[action]
        if not old["exists"] or current[expected[0]]!=expected[1] or result.get("state")!=current:
            raise ContractError("operation_skill","扩展效果未满足请求状态或原对象不存在。")
        if action=="delete_skill":
            from pathlib import Path
            if Path(old["path"]).exists():raise ContractError("operation_skill","原扩展文件仍存在。")
        elif old["path"]!=current["path"]:raise ContractError("operation_skill","扩展对象身份变化。")
        obj={"kind":"skill","name":args["name"],"identity":current}
    return {"id":"eff_"+digest(encode([session_id,receipt_id,spec,obj]))[7:31],"session_id":session_id,
        **spec,"object":obj,"before":deepcopy(before),"permission_scope":before["permission_scope"],
        "receipt_id":receipt_id,"result_sha256":binding["result_sha256"],"data_identities":deepcopy(binding["data_identities"]),**extra}


def _resolve_conversation_effect(session_id,args,before,result):
    from data_agent.tools.report import _conversation_source,_conversation_reports_root,_conversation_outputs
    def reject():raise ContractError("operation_conversation","导出文件、参数或原会话/答案/图表来源与执行前绑定不一致。")
    if args.get("reply_target")=="current_answer":
        from .runtime import read_answer
        from data_agent.session.history import load_canonical_history
        source=before.get("source_reply")
        if (before.get("permission_scope")!="current_session_reply_export" or not isinstance(source,dict)
                or before.get("reports_root")!=str(_conversation_reports_root(session_id))
                or result.get("parameters")!=args or result.get("source_reply")!=source):raise ContractError("operation_reply_binding","Current reply original parameters/permission/source mismatch")
        owners=[m for m in load_canonical_history(session_id).messages if m.get("reply_id")==source.get("reply_id") and m.get("answer_ref")==source.get("answer_ref")]
        if len(owners)!=1 or owners[0].get("answer_ref")!=source.get("answer_ref"):raise ContractError("operation_reply_owner","Current reply has no exact canonical owner")
        accepted=read_answer(session_id,source["answer_ref"])
        if owners[0].get("content")!=accepted["body"]:raise ContractError("operation_reply_body","Original reply body differs from AcceptedAnswer")
        outputs=_conversation_outputs(session_id,result)
        if (outputs!=result.get("outputs") or result.get("status")!="exported" or len(outputs)!=1
                or outputs[0]["format"]!=args["format"] or any(o["path"] in before.get("existing_artifact_paths",[]) for o in outputs)):raise ContractError("operation_reply_output","Current reply export bytes/status/format/fresh artifact mismatch")
        main=outputs[0]
        return {"kind":"file","name":main["path"],"identity":{"exists":True,"sha256":main["sha256"],"format":main["format"]}}, {"details":{"format":main["format"],"outputs":outputs,"source_reply":source,"boundary":"只导出这份已保存原AcceptedAnswer；原正文和保存时的交付状态不回写。"}}
    source=before.get("source_snapshot")
    if (before.get("permission_scope")!="current_session_conversation_export" or not isinstance(source,dict)
            or before.get("reports_root")!=str(_conversation_reports_root(session_id))
            or result.get("parameters")!=args or result.get("source_binding")!=source):reject()
    _,current=_conversation_source(session_id,args["include_charts"],source)
    outputs=_conversation_outputs(session_id,result)
    if current!=source or outputs!=result.get("outputs") or any(o["path"] in before.get("existing_artifact_paths",[]) for o in outputs):reject()
    status=result.get("status");partial=status=="degraded"
    if (result.get("type")!="conversation" or result.get("format")!=args["format"]
            or status not in {"exported","degraded"} or partial and args["format"]!="pdf"):reject()
    expected=[args["format"]]+(["html"] if args["format"]=="pdf" else []) if not partial else ["html"]
    if [o["format"] for o in outputs]!=expected:reject()
    main=outputs[0];extra={"details":{"format":main["format"],"requested_format":args["format"],"outputs":outputs,
                                    "source_message_count":source["message_count"],"boundary":"仅证明已绑定公开会话快照的导出，不验证正文中的数据结论。"}}
    if partial:
        if not isinstance(result.get("reason"),str) or not result["reason"]:reject()
        extra["completion_gap"]={"status":"evidence_insufficient","reason":"PDF未生成；已保存HTML备用件。"+result["reason"]}
    return {"kind":"file","name":main["path"],"identity":{"exists":True,"sha256":main["sha256"],"format":main["format"]}},extra


def _validate_transform_result(receipt,result,binding):
    from data_agent.tools.data_transform import _transform_parameters,_transform_sources
    args=receipt["arguments"];sources=_transform_sources(args)
    identity=binding["data_identities"].get(result.get("dataset"),{})
    expected=[binding["data_identities"].get(n,{}).get("version_id") for n in sources]
    if (result.get("source_dataset")!=args["name"] or result.get("source_datasets")!=sources
            or result.get("parameters")!=_transform_parameters(args) or result.get("operation")!=args["operation"]
            or not all(expected) or identity.get("parent_version_ids")!=expected):
        raise ContractError("native_transform_scope","变换产物的实际参数、全部来源或父版本与原派发不一致。")


def _resample_effect_details(context,args,result):
    from data_agent.tools.data_transform import _transform_parameters
    actual=context.workspace._publication_resample_audit(args["name"],_transform_parameters(args).get("date_col",""))
    if actual is None or result.get("resample_audit")!=actual or result.get("status")!=("partial" if actual["excluded_rows"] else "complete"):
        raise ContractError("native_resample_scope","重采样有效/排除范围与实际来源或完成状态不一致。")
    extra={"details":{"resample_audit":deepcopy(actual)}}
    if actual["excluded_rows"]:
        extra["completion_gap"]={"status":"evidence_insufficient","reason":f"新表已创建；{actual['effective_rows']} 条有效日期记录已计算，{actual['excluded_rows']} 条日期缺失或无法解析的记录已排除，原请求范围未完整覆盖。"}
    return extra


def _conversion_effect_details(context,args,result,target):
    rows=result.get("conversion_audit")
    def reject():raise ContractError("operation_conversion","类型转换审计与实际新表、参数或完成状态不一致。")
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):reject()
    if len({r.get("column") for r in rows})!=len(rows):reject()
    if not args["auto"] and (len(rows)!=1 or rows[0].get("column")!=args["column"] or rows[0].get("to")!=args["target_type"]):reject()
    applied={r["column"]:r for r in result.get("auto_applied",[])} if args["auto"] else {}
    if args["auto"] and set(applied)!={r.get("column") for r in rows}:reject()
    from data_agent.tools.registry import registry
    allowed=registry.get("apply_type_conversion").parameters["properties"]["target_type"]["enum"]
    requests=[]
    for row in rows:
        if not row.get("to") or row["to"] not in allowed:reject()
        item=applied.get(row.get("column"),{})
        if args["auto"] and "error" not in item and item.get("converted_to")!=row.get("to"):reject()
        requests.append((row.get("column"),row.get("to"),item.get("error","")))
    actual=context.workspace._publication_conversion_audit(args["name"],target,requests)
    if actual is None or actual!=rows:reject()
    partial=any(r["conversion_failures"] or r["reason"] for r in actual)
    if result.get("status")!=("partial" if partial else "complete"):reject()
    extra={"details":{"conversion_audit":deepcopy(actual)}}
    if args["auto"]:extra["details"]["skipped"]=deepcopy(result.get("skipped",[]))
    if partial:
        extra["completion_gap"]={"status":"evidence_insufficient","reason":"新表已创建；部分类型转换未完成："+"；".join(str(r["column"])+"："+str(r["conversion_failures"])+" 条无法转换（"+r["reason"]+"）" for r in actual if r["conversion_failures"] or r["reason"])}
    return extra


def _cleaning_effect_details(context,args,result,target):
    columns=[c.strip() for c in args["columns"].split(",") if c.strip()] if args["columns"] else ()
    source=context.workspace._publication_cleaning_state(args["name"],columns,args["deduplicate"])
    child=context.workspace._publication_cleaning_state(target,columns)
    report=result.get("missing_handling",{});rows=report.get("columns",[])
    def reject():raise ContractError("operation_cleaning","清洗回执计数、范围或完成状态与实际对象不一致。")
    if not source or not child or report.get("strategy")!=args["missing_strategy"] or not isinstance(rows,list):reject()
    if [r.get("column") for r in rows]!=[r["column"] for r in source["columns"]]:reject()
    if result.get("final_rows")!=child["rows"] or result.get("rows_removed")!=result.get("original_rows",-1)-child["rows"]:reject()
    stage_rows=report.get("rows_after_strategy")
    if type(stage_rows) is not int or not child["rows"]<=stage_rows<=source["rows"]:reject()
    for row,before,after in zip(rows,source["columns"],child["columns"]):
        if any(type(row.get(k)) is not int or row[k]<0 for k in ("missing_before","filled","missing_after_strategy","missing_after")):reject()
        if row["missing_before"]!=before["missing"] or row["missing_after"]!=after["missing"] or not isinstance(row.get("reason"),str):reject()
        stage=row["missing_after_strategy"]
        if not row["missing_after"]<=stage<=row["missing_before"]:reject()
        expected=row["missing_before"]-stage if args["missing_strategy"].startswith("fill_") else 0
        if row["filled"]!=expected:reject()
        if args["missing_strategy"]=="drop" and stage:reject()
        if args["missing_strategy"]=="keep" and stage!=row["missing_before"]:reject()
        if args["outlier_strategy"]!="drop" and row["missing_after"]!=stage:reject()
    if report.get("filled")!=sum(r["filled"] for r in rows) or report.get("remaining")!=sum(r["missing_after"] for r in rows):reject()
    partial=args["missing_strategy"]!="keep" and bool(report["remaining"])
    if result.get("status")!=("partial" if partial else "complete"):reject()
    extra={"details":{"missing_handling":deepcopy(report)}}
    if partial:
        unresolved=[str(r["column"])+"："+str(r["missing_after"])+" 条缺失（"+r["reason"]+"）" for r in rows if r["missing_after"]]
        extra["completion_gap"]={"status":"evidence_insufficient","reason":"新表已创建；所选范围仍有未解决缺失："+"；".join(unresolved)}
    return extra


def _number(value):
    if type(value) not in {int,float} or not math.isfinite(value):
        raise ContractError("native_number", "原测量不是有限数值。")


def _days(start,end):
    a,b=(datetime.fromisoformat(v.replace("Z","+00:00")) for v in (start,end))
    if b < a: raise ContractError("native_window", "原测量时间窗口倒置。")
    return (b.date()-a.date()).days+1


def _claim(receipt,binding,path,value,label,unit=None,scope="",limitations=(),derivation=None):
    dataset=receipt.get("arguments",{}).get("name") or next(iter(binding["data_identities"]),None)
    catalog=receipt["tool_name"]=="list_data" and isinstance(binding.get("catalog_binding"),dict)
    file=receipt["tool_name"] in {"read_file","list_files"} and isinstance(binding.get("file_binding"),dict)
    skills=receipt["tool_name"]=="list_skills" and isinstance(binding.get("skills_binding"),dict)
    mcp=receipt["tool_name"]=="list_mcp_servers" and isinstance(binding.get("mcp_binding"),dict)
    if catalog or file or skills or mcp: dataset=None
    if not (catalog or file or skills or mcp) and (not isinstance(dataset,str) or dataset not in binding["data_identities"]):
        raise ContractError("native_dataset", "原生测量没有绑定唯一执行数据集。")
    encode(value)
    result={"id":"c_"+digest(encode([receipt["id"],path,label]))[7:31],"label":label,"value":deepcopy(value),"unit":unit,
        "scope":{"dataset":dataset,"population":"当前回执读取范围","time_scope":scope,"grain":"原工具计算粒度"},
        "limitations":list(limitations) or ["仅描述当前观测；未授予因果、统计推断或外推验证"],
        "basis_refs":[{"receipt_id":receipt["id"],"session_id":binding["session_id"],"tool_name":receipt["tool_name"],
            "result_sha256":binding["result_sha256"],"data_identities":deepcopy(binding["data_identities"]),"result_path":list(path),
            **({"catalog_binding":deepcopy(binding["catalog_binding"])} if catalog else {}),
            **({"file_binding":deepcopy(binding["file_binding"])} if file else {}),
            **({"skills_binding":deepcopy(binding["skills_binding"])} if skills else {}),
            **({"mcp_binding":deepcopy(binding["mcp_binding"])} if mcp else {})}]}
    if any(origin.get("kind")=="session_generated" for identity in binding["data_identities"].values()
           for origin in identity.get("source_origins",[])):
        result["limitations"].append("包含会话生成文件来源；仅描述该探索输入，未证明其代表原上传源或完整保留原记录")
    result["target"]={"dataset":dataset,"tool":receipt["tool_name"],"parameters":deepcopy(receipt.get("arguments",{}))}
    if receipt["tool_name"]=="run_python":
        # Every dependency was read by the actual execution and revalidated.
        # An input anchor does not claim that a derived field came from only it.
        result["scope"]["population"]="当前 Python 回执的全部实际读取来源"
    if len(path)>1 and path[0]=="metrics": result["target"]["metric"]=path[1]
    if derivation: result["derivation"]=derivation
    return result


def resolve_native_claims(*,session_id,receipt_id,result_paths=()):
    context,receipt,result,binding=load_receipt_result(session_id=session_id,receipt_id=receipt_id)
    if receipt["tool_name"] in DATASET_OPERATIONS-{"transform_data","top_n","synthesize_time_series"}:return []
    binding=dict(binding,session_id=session_id)
    if not isinstance(result,dict): raise ContractError("native_shape", "原生结果不是结构化对象。")
    # Reject a mismatched execution dataset before accepting any field.
    _claim(receipt,binding,["dataset"],None,"范围")
    if receipt["tool_name"]=="transform_data":
        _validate_transform_result(receipt,result,binding)
        if result["operation"]=="resample":_resample_effect_details(context,receipt["arguments"],result)
    if receipt["tool_name"]=="what_if_simulation":
        if result.get("mode")=="optimize":_validate_allocation_result(receipt,result)
        elif result.get("mode") in {"sensitivity","sensitivity_reverse"}:_validate_sensitivity_result(receipt,result)
        elif result.get("mode")=="predict":_validate_model_scenario(receipt,result,binding)
        else:raise ContractError("result_contract_mismatch","未知模拟结果模式。")
    facts=[]
    def add(path,value,label,unit=None,scope="",derivation=None):
        facts.append(_claim(receipt,binding,path,value,label,unit,scope,derivation=derivation))
    if receipt["tool_name"] in {"read_file","list_files"}:
        fb=binding["file_binding"]
        key="content" if receipt["tool_name"]=="read_file" else "entries"
        add([key],result[key],"文件原文片段" if key=="content" else "文件目录快照")
        facts[-1]["scope"].update(population="当前会话核验文件范围："+encode({k:fb[k] for k in ("captured_at","canonical_path","parameters")}),grain="文件原文" if key=="content" else "文件目录")
        if key=="content":
            facts[-1]["scope"]["time_scope"]=encode({k:result[k] for k in ("sha256","offset","end_offset","next_offset","total_chars","total_bytes")})
        facts[-1]["limitations"]=["仅证明该文件原文或枚举快照；文件内部数据结论未经核验。", "目录新增对象不属于此枚举时点；当前会话与路径读取权限已核。"]
        if key=="entries" and result["skipped_entries"]:
            facts[-1]["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"枚举时有不可访问或瞬时消失条目；未覆盖范围不称为空。"}
    elif receipt["tool_name"] == "list_mcp_servers":
        for key,label in (("servers","当前全局MCP配置目录"),("health","当前进程MCP连接记录")):
            add([key],result[key],label)
            facts[-1]["scope"].update(population="当前会话绑定的全局配置文件及当前进程内存快照",grain="MCP目录元数据")
            facts[-1]["limitations"]=["配置保存不表示该配置已应用于当前连接；连接记录与配置分别核验。", "连接记录只来自当前进程缓存，未主动探活或调用远端；无管理器时连接状态未知。", "连接记录中的工具字段是原摘要；完整工具发现另核，不授予远端执行权限或数据事实。"]
    elif receipt["tool_name"] == "list_skills":
        add(["skills"],result["skills"],"当前全局Skills及本会话加载目录")
        facts[-1]["scope"].update(population="当前会话绑定的全局目录及文件摘要",grain="Skills目录元数据")
        facts[-1]["limitations"]=["安装/启用为全局状态；加载状态只属于当前会话。", "按宿主现有发现规则注册的目录元数据，不核验Skills正文所述数据结论或授予执行权限。"]
    elif receipt["tool_name"] == "list_data":
        actual = context.workspace._publication_catalog_result(binding["catalog_binding"])["result"]
        if actual is None or encode(result) != encode(actual):
            raise ContractError("result_contract_mismatch", "目录的完整字段、记录数、可见父源或变换历史与原回执来源不一致。")
        for key, label in (("datasets", "当前授权范围完整数据集目录"), ("transform_history", "当前可见对象间完整变换历史")):
            add([key], result[key], label)
            facts[-1]["scope"].update(population="当前回执授权可见对象集合",grain="目录元数据")
            facts[-1]["limitations"] = ["仅当前回执绑定的授权可见范围；空集合不表示不可见范围为空，也不包含原始记录值。"]
    elif receipt["tool_name"] == "preview_data":
        actual=context.workspace._publication_diagnostic_result("preview_data",receipt["arguments"])
        if actual is None or encode(result)!=encode(actual):
            raise ContractError("result_contract_mismatch","预览原值、顺序或请求/返回/源表范围与实际来源不一致。")
        for key,label in (("data","源表当前顺序前行预览"),("observation","预览范围：请求、实际返回及源表总行数"),("rows","预览实际返回行数"),("columns","预览源列"),("shape","预览源表形状")):
            add([key],result[key],label)
            facts[-1]["target"]["deliverable"]=key in {"data","observation"}
            facts[-1]["limitations"]=["仅源表当前顺序前行预览；不表示全表交付、随机样本或总体推断。"]
    elif receipt["tool_name"] == "interpret_dataset":
        actual=context.workspace._publication_diagnostic_result("interpret_dataset",dict(receipt["arguments"],_bound_reads=list(binding["data_identities"])))
        if actual is None or encode(result)!=encode(actual):
            raise ContractError("result_contract_mismatch","解释候选、依据、日期范围或实际跨表来源与绑定数据不一致。")
        for key in RESULT_FIELDS["interpret_dataset"]:
            add([key],result[key],"数据解释候选与观测："+key)
            facts[-1]["limitations"]=list(result["limitations"])
    elif receipt["tool_name"] == "suggest_column_types":
        actual=context.workspace._publication_diagnostic_result("suggest_column_types",receipt["arguments"])
        if actual is None or encode(result)!=encode(actual):
            raise ContractError("result_contract_mismatch","类型建议、置信度或样本范围与当前实际来源不一致。")
        for key,label in (("suggestions","类型转换建议"),("observation","类型建议的原表与样本范围")):
            add([key],result[key],label)
            facts[-1]["limitations"]=list(result["limitations"])
    elif receipt["tool_name"] == "detect_data_quality":
        actual=context.workspace._publication_diagnostic_result("detect_data_quality",receipt["arguments"])
        if actual is None or encode(result)!=encode(actual):
            raise ContractError("result_contract_mismatch","质量诊断、有效/排除范围或IQR边界与实际来源不一致。")
        for key in ("issues","total_issues","column_diagnostics","observation","rows"):
            add([key],result[key],"基础质量诊断："+key,"条" if key=="rows" else "项" if key=="total_issues" else None)
            facts[-1]["limitations"]=list(result["limitations"])
    elif receipt["tool_name"] == "describe_dataset":
        if result.get("dataset") != receipt["arguments"]["name"]:
            raise ContractError("native_dataset", "描述结果与执行数据集不一致。")
        rows=result.get("shape",{}).get("rows")
        if type(rows) is not int or rows<0: raise ContractError("native_rows", "记录数无效。")
        add(["shape","rows"],rows,"记录数","条")
        facts[-1]["target"]["statistic"]="rows"
        for column,window in result.get("observation_window",{}).get("columns",{}).items():
            days=_days(window["min"],window["max"])
            path=["observation_window","columns",column]
            add(path,days,"观测日期含首尾日数","天",window["min"]+"/"+window["max"],
                {"operator":"inclusive_calendar_days","operand_paths":[path+["min"],path+["max"]]})
        for index,field in enumerate(result.get("field_statistics",[])):
            column=field["name"]
            measured={key:field[key] for key in ("missing_count","missing_pct","unique_values","top_values") if key in field}
            measured.update({key:value for key,value in field.get("stats",{}).items() if key in {"sum","mean","std","min","25%","50%","75%","max"}})
            for statistic,value in measured.items():
                # Undefined statistics are local gaps, never a reason to lose row/date facts.
                if value is None or (type(value) is float and not math.isfinite(value)): continue
                path=["field_statistics",index]+(["stats"] if statistic in field.get("stats",{}) else [])+[statistic]
                add(path,value,column+"："+statistic,"percent" if statistic=="missing_pct" else None)
                facts[-1]["target"].update(metric=column,statistic=statistic)
    elif receipt["tool_name"] in {"quick_profile","assess_readiness"}:
        actual=context.workspace._publication_diagnostic_result(receipt["tool_name"],receipt["arguments"])
        if actual is None or actual!=result:raise ContractError("result_contract_mismatch","基础诊断、列范围或方法边界与当前实际数据不一致。")
        for key in RESULT_FIELDS[receipt["tool_name"]]:
            if key in result:
                add([key],result[key],"列级基础诊断："+key)
                facts[-1]["limitations"].extend(result["limitations"])
    elif receipt["tool_name"] == "compare_periods":
        for period in ("period_a","period_b"):
            part=result[period]
            if part["day_count"] != _days(*part["range"]) or type(part["rows"]) is not int or part["rows"]<0:
                raise ContractError("native_period", "时段日数或记录数不匹配。")
        scope=encode({p:result[p]["range"] for p in ("period_a","period_b")})
        groups=[]
        if result.get("dimensions"):
            for i,row in enumerate(result.get("comparisons",[])):
                for metric,item in row.items():
                    if metric not in {"dimension","dimension_values"}: groups.append((["comparisons",i,metric],metric+" / "+row["dimension"],metric,item,("a","b","diff")))
        else:
            for metric,item in (result.get("metrics") or {}).items():
                groups.append((["metrics",metric],metric,metric,item,("period_a","period_b","diff")))
        if not groups: raise ContractError("native_metrics", "该比较结果尚无完整指标组。")
        for path,label,metric,item,keys in groups:
            exact=item.get("exact_aggregates")
            if not isinstance(exact,dict) or set(exact)!=set(keys):
                raise ContractError("native_precision", "比较缺少原精度测量，不能从舍入值恢复。")
            aggregation=item.get("aggregation",{"operator":"sum"})
            if aggregation.get("operator")=="ratio_of_sums":
                fields(aggregation,{"operator","numerator","denominator","operand_sums"})
                formula=receipt["arguments"].get("metric_formulas",{}).get(metric)
                if not isinstance(formula,dict) or any(aggregation.get(k)!=formula.get(k) for k in ("operator","numerator","denominator")):
                    raise ContractError("native_ratio_definition","窗口比率公式与原执行参数不一致。")
                unknown=[]
                for period in keys[:2]:
                    operands=aggregation["operand_sums"][period]
                    fields(operands,{"numerator","denominator"})
                    if operands["denominator"] in (None,0) or operands["numerator"] is None:
                        unknown.append(period)
                        if exact[period] is not None:
                            raise ContractError("native_ratio","零分母或缺失输入不能授予比率。")
                    else:
                        _number(operands["numerator"]);_number(operands["denominator"])
                        if exact[period]!=operands["numerator"]/operands["denominator"]:
                            raise ContractError("native_ratio","窗口比率不等于原分子合计除以原分母合计。")
                if unknown:
                    if item.get("status")!="evidence_insufficient" or exact[keys[2]] is not None or item.get("change_pct") is not None:
                        raise ContractError("native_ratio","存在未知期值时不能授予差值或相对变化。")
                    gap={"status":"evidence_insufficient","reason":"窗口比率的分母为零或原列合计缺失："+", ".join(unknown)+"。差值与相对变化未知。"}
                    for key,title in zip(keys[:2],("前期","后期")):
                        if item.get(key)!=(round(exact[key],4) if exact[key] is not None else None):
                            raise ContractError("native_display","比率期值显示与原测量不一致。")
                        add(path+["exact_aggregates",key],exact[key],label+"："+title,None,scope)
                        facts[-1]["target"].update(metric=metric,statistic="ratio_of_sums",completion_gap=gap)
                        facts[-1]["limitations"].append("窗口比率的分母为零或原列合计缺失："+", ".join(unknown)+"；差值与相对变化未知。")
                        facts[-1]["limitations"].append("窗口比率 = SUM("+aggregation["numerator"]+") / SUM("+aggregation["denominator"]+")；不是逐行比率之和")
                    continue
            elif aggregation.get("operator")!="sum":
                raise ContractError("native_aggregation","未知聚合算术。")
            if aggregation.get("operator")=="sum" and any(v is None for v in exact.values()):
                if exact[keys[2]] is not None or item.get("change_pct") is not None or item.get("status")!="evidence_insufficient":raise ContractError("native_sum","未知合计不能授予差值或相对变化。")
                for key,title in zip(keys,("前期","后期","差值")):
                    if exact[key] is not None:_number(exact[key])
                    if item.get(key)!=(round(exact[key],4) if exact[key] is not None else None):raise ContractError("native_display","未知合计显示与原值不一致。")
                    add(path+["exact_aggregates",key],exact[key],label+"："+title,None,scope)
                    facts[-1]["target"]["metric"]=metric
                add(path+["change_pct"],None,label+"：相对变化","percent",scope);facts[-1]["target"]["metric"]=metric
                continue
            for value in exact.values(): _number(value)
            a,b,d=(exact[k] for k in keys)
            if b-a != d: raise ContractError("native_difference", "比较差值不等于原两期值相减。")
            if any(type(item[k]) not in {int,float} or item[k] != round(exact[k],4) for k in keys):
                raise ContractError("native_display", "比较显示值与原精度不一致。")
            pct=item.get("change_pct")
            expected=round(d/abs(a)*100,2) if a!=0 else None
            if pct != expected or (pct is not None and type(pct) not in {int,float}):
                raise ContractError("native_percent", "相对变化或零分母处理不正确。")
            for key,title in zip(keys,("前期","后期","差值")):
                add(path+["exact_aggregates",key],exact[key],label+"："+title,None,scope)
                facts[-1]["target"]["metric"]=metric
                if aggregation["operator"]=="ratio_of_sums":
                    facts[-1]["target"]["statistic"]="ratio_of_sums"
                    facts[-1]["limitations"].append("窗口比率 = SUM("+aggregation["numerator"]+") / SUM("+aggregation["denominator"]+")；不是逐行比率之和")
            add(path+["change_pct"],pct,label+"：相对变化","percent",scope)
            facts[-1]["target"]["metric"]=metric
        for period,label in (("period_a","前期"),("period_b","后期")):
            for key,unit in (("rows","条"),("day_count","天")):
                add([period,key],result[period][key],label+("记录数" if key=="rows" else "含首尾日数"),unit,scope)
        combined=result["combined"]
        windows=[[datetime.fromisoformat(v).date() for v in result[p]["range"]] for p in ("period_a","period_b")]
        overlap=max(0,(min(w[1] for w in windows)-max(w[0] for w in windows)).days+1)
        total_days=sum(result[p]["day_count"] for p in ("period_a","period_b"))-overlap
        rows=[result[p]["rows"] for p in ("period_a","period_b")]
        if (type(combined["day_count"]) is not int or combined["day_count"]!=total_days
                or type(combined["row_count"]) is not int or not max(rows)<=combined["row_count"]<=sum(rows)
                or not overlap and combined["row_count"]!=sum(rows)):
            raise ContractError("native_combined_scope", "合并范围日历并集或源记录数不匹配；不能重复计重叠窗口。")
        for key,label,unit in (("row_count","合并范围记录数","条"),("day_count","合并范围日历日数","天")):
            add(["combined",key],combined[key],label,unit,scope)
        actual=context.workspace._publication_period_comparison_result(receipt["arguments"])
        if actual is None or actual!=result:raise ContractError("result_contract_mismatch","时段比较原合计、差值、日均、完整分组或真实范围与实际来源不一致。")
        comparison_key="comparisons" if result.get("dimensions") else "metrics"
        add([comparison_key],result[comparison_key],"完整时段比较（含真实有效范围）",None,scope)
        facts[-1]["target"].update(deliverable=True)
        add(["observation"],result["observation"],"时段比较原日期范围审计",None,scope)
        for claim in facts:
            path=claim["basis_refs"][0]["result_path"];gaps=list(result["completion_gaps"]) if path[0]!="observation" and path[-1] not in {"day_count"} else []
            if path[:1]==["metrics"] and len(path)>1:item=result["metrics"][path[1]]
            elif path[:1]==["comparisons"] and len(path)>2:item=result["comparisons"][path[1]][path[2]]
            else:item=None
            if item:
                point=path[-1] if "exact_aggregates" in path and path[-1]!="diff" else None
                gaps+=item["period_gaps"].get(point,[]) if point else item["completion_gaps"]
                if path[-1]=="change_pct" and item["percentage_limitation"]:gaps.append(item["percentage_limitation"])
                if claim["value"] is None:gaps.append("该期值或派生量未知；不能把未观测/不可计算当零。")
            if path==[comparison_key]:
                for _,_,_,item,_ in groups:gaps+=item["completion_gaps"]+([item["percentage_limitation"]] if item["percentage_limitation"] else [])
            claim["limitations"].extend(result["limitations"])
            if gaps:claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":" ".join(dict.fromkeys(gaps))}
            elif item:claim["target"].pop("completion_gap",None)

    else:
        selected=RESULT_FIELDS.get(receipt["tool_name"])
        if selected is None:
            raise ContractError("native_unsupported", "该工具没有公开测量适配；原产物仍可保留，不能自动提升任意字段。")
        if result.get("method_contract"):
            dataset=receipt.get("arguments",{}).get("name")
            if result.get("data_identity") is not None and result.get("data_identity")!=binding["data_identities"].get(dataset):
                raise ContractError("native_method_identity", "方法产物的原数据身份不匹配。")
        limits=list(result.get("limitations") or [])+["原工具返回值；单位未声明时保持未知，不能升级为因果识别或已验证外推"]
        if receipt["tool_name"]=="run_python":
            if result.get("result_data_status")!="available" or not result.get("dataset_reads"):
                raise ContractError("native_python", "Python 没有结构化执行值与实际读取身份；stdout 不作为事实。")
            parameters=receipt.get("arguments",{}).get("business_parameters") or {}
            if result.get("business_parameters",{})!=parameters:
                raise ContractError("native_python_parameters","Python 执行参数与前置回执不一致。")
            limits += ["探索性 Python 计算，尚未授予推断或预测验证强度", "业务参数为执行前声明，不证明方法正确或预测有效"]
        if receipt["tool_name"] in {"classification","regression_analysis"}:
            _validate_supervised_result(receipt,result,binding)
        if receipt["tool_name"]=="shap_analysis":
            _validate_shap_result(receipt,result,binding)
        if receipt["tool_name"]=="ab_test":
            _validate_ab_result(receipt,result)
        if receipt["tool_name"]=="causal_analysis":
            _validate_did_result(receipt,result)
        if receipt["tool_name"]=="correlation_analysis":
            _validate_correlation_result(receipt,result)
        if receipt["tool_name"]=="forecast":
            _validate_forecast_result(context,receipt,result)
        if receipt["tool_name"]=="analyze_time_series":
            _validate_time_series_result(context,receipt,result)
        if receipt["tool_name"]=="synthesize_time_series":
            _validate_time_synthesis_result(context,receipt,result)
        if receipt["tool_name"]=="attribution_analysis":
            _validate_factor_result(context,receipt,result)
        if receipt["tool_name"]=="contribute_decomposition":
            _validate_contribution_result(context,receipt,result)
        if receipt["tool_name"]=="top_n":
            _validate_top_n_result(context,receipt,result)
        if receipt["tool_name"]=="segmentation_analysis":
            _validate_segmentation_result(context,receipt,result)
        if receipt["tool_name"]=="cohort_analysis":
            _validate_cohort_result(context,receipt,result)
        if receipt["tool_name"]=="funnel_analysis":
            _validate_funnel_result(context,receipt,result)
        if receipt["tool_name"]=="distribution_analysis":
            _validate_distribution_result(context,receipt,result)
            selected=[key for key in result if key!="_suggested_next"]
        if receipt["tool_name"]=="forecast" and result.get("forecast"):
            periods=receipt["arguments"].get("periods",7)
            if result.get("periods")!=periods or result.get("parameters",{}).get("periods")!=periods or len(result["forecast"])!=periods:
                raise ContractError("result_contract_mismatch", "Forecast horizon differs from the dispatched business parameters.")
        for key in selected:
            if key in result:
                value=result[key]
                encode(value)
                facts.append(_claim(receipt,binding,[key],value,receipt["tool_name"]+"："+key,
                    limitations=limits,scope=encode({k:result[k] for k in ("date_range","coverage","observation_window","parameters") if k in result})))
                if receipt["tool_name"]=="run_python": facts[-1]["target"]["parameters"].update(parameters)
                if receipt["tool_name"]=="curve_fitting" and key=="scenarios":
                    facts[-1]["label"]="未验证参数情景（未来真实值未知）"
                    facts[-1]["target"]["statistic"]="scenario"
                facts[-1]["target"]["deliverable"] = key not in {"parameters","method","status","claim_ceiling","zero_value_semantics","limitations","source_identities","validation","coverage","missing_aligned_dates","right_censoring","analysis_unit","sort_by","ascending"} and value is not None and value != [] and value != {}
                if receipt["tool_name"]=="correlation_analysis":
                    facts[-1]["target"]["deliverable"]=key=="correlation_matrix"
                    if key=="correlation_matrix":facts[-1]["unit"]="无量纲"
                if receipt["tool_name"]=="causal_analysis":
                    facts[-1]["target"]["deliverable"]=key in {"did_effect","ci_95","standard_error","p_value","group_means","cell_counts","total_observations"}
                    if value is None:
                        facts[-1]["target"]["completion_gap"]={"status":"evidence_insufficient","reason":result["inference_limitation"]}
                    if key=="did_effect": facts[-1]["label"]="DID差中差点估计（因果假设未验证）"
                    if key=="p_value":facts[-1]["unit"]="无量纲"
        if not facts: raise ContractError("native_fields", "该结果没有对应的原生公开字段。")
    if receipt["tool_name"]=="distribution_analysis":
        for column in selected:
            row=result[column];excluded=row["observation"]["excluded_nonfinite"]
            scope_gap={"status":"evidence_insufficient","reason":f"{column} 有 {excluded} 条非有限值被排除；仅 {row['count']} 条有限观测已计算，原范围未完整覆盖。"} if excluded else None
            for claim in facts:
                if claim["basis_refs"][0]["result_path"]==[column]:
                    claim["limitations"].extend(row["limitations"])
                    if scope_gap:claim["target"]["completion_gap"]=deepcopy(scope_gap)
                    elif any(row[k] is None for k in ("mean","std","skewness","kurtosis")) or any(v is None for v in row["quantiles"].values()) or row["normality_test"]["p_value"] is None:
                        claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"部分分布统计或正态性推断未知；可计算描述量保留。"}
            for statistic in ("count","mean","std","min","25%","50%","75%","max"):
                quantile=statistic in row["quantiles"]
                value=row["quantiles"][statistic] if quantile else row[statistic]
                if value is not None:_number(value)
                add([column,"quantiles",statistic] if quantile else [column,statistic],value,column+"："+statistic)
                facts[-1]["target"].update(metric=column,statistic=statistic,deliverable=True)
                facts[-1]["limitations"].extend(row["limitations"])
                if scope_gap:facts[-1]["target"]["completion_gap"]=deepcopy(scope_gap)
                elif value is None:facts[-1]["target"]["completion_gap"]={"status":"evidence_insufficient","reason":column+" 没有可用有限观测；"+statistic+" 未知。"}
    if receipt["tool_name"]=="forecast":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            claim["target"]["metric"]=result["parameters"]["target_col"]
            claim["label"]="原有序留出预测（启发带未校准）："+key
            gaps=list(result["completion_gaps"])
            if key=="observation":gaps=[]
            elif key in {"backtest","date_range"}:gaps=[g for g in gaps if "原范围" in g]
            if gaps:claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":" ".join(gaps)}
    if receipt["tool_name"]=="synthesize_time_series":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            claim["target"]["deliverable"]=key in {"aligned_data","aligned_rows","coverage","observation","missing_aligned_dates"}
            claim["scope"]["grain"]="自然日；时区："+str(result["parameters"]["timezone"] or "未指定时区的本地日期")
            if key=="aligned_data":
                claim["label"]="多来源自然日合计与外对齐原值"
                if result["completion_gaps"]:claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":" ".join(result["completion_gaps"])}
    if receipt["tool_name"]=="analyze_time_series":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0];claim["target"].update(metric=result["parameters"]["value_col"],deliverable=True)
            gaps=list(result["completion_gaps"]) if key!="observation" else []
            if key=="trend" and result["trend"]["inference_limitation"]:gaps.append(result["trend"]["inference_limitation"])
            if key in {"window_comparisons","change_points"} and (result["data_points"]<10 or any(r["change_pct"] is None for r in result["window_comparisons"])):gaps.append("滑窗未计算或存在零前均值；部分百分比/阈值判定未知，绝对差保留。")
            if key in {"autocorrelation","seasonality"} and result["seasonality"]["autocorrelation"] is None:gaps.append("有效点不足或序列退化，自相关候选未知；未验证季节性。")
            if gaps:claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":" ".join(gaps)}
    if receipt["tool_name"]=="attribution_analysis":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            claim["target"].update(metric=result["parameters"]["target"],deliverable=True)
            claim["label"]="因素调整关联（非因果）："+key
            if key in {"estimates","bivariate_associations","vif"} and result["completion_gaps"]:
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":" ".join(result["completion_gaps"])}
    if receipt["tool_name"]=="contribute_decomposition":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            claim["target"]["deliverable"]=key in {"decomposition","total_change","total_change_pct","period_a","period_b","comparability","daily_normalized","observation"}
            if key=="total_change_pct":claim["unit"]="percent"
            if key=="decomposition" and result["completion_gaps"]:
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":" ".join(result["completion_gaps"])}
            if key=="total_change_pct" and claim["value"] is None:
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"前期值为0，总体变化百分比未知；原值与绝对变化保留。"}
    if receipt["tool_name"]=="top_n":
        for claim in facts:
            claim["target"]["deliverable"]=claim["basis_refs"][0]["result_path"][0] in {"records","n","observation"}
    if receipt["tool_name"]=="segmentation_analysis":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            claim["target"]["deliverable"]=key in {"clusters","observation","requested_n_clusters","n_clusters","total_samples"}
            if key in {"requested_n_clusters","n_clusters"}:claim["unit"]="簇"
            elif key=="total_samples":claim["unit"]="条"
            if key=="clusters" and result["completion_gaps"]:
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":" ".join(result["completion_gaps"])}
    if receipt["tool_name"]=="cohort_analysis":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            claim["target"]["deliverable"]=key in {"cohorts","observation"}
            if key=="cohorts" and result["status"]=="partial":
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"原范围有 "+str(result["observation"]["excluded_rows"])+" 条缺失用户/缺失或无效时间记录被排除；已计算的有效观测留存矩阵仍保留。"}
    if receipt["tool_name"]=="funnel_analysis":
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            claim["target"]["deliverable"]=key in {"steps","overall_conversion","dimension_funnels","biggest_drop"} and (key!="dimension_funnels" or result[key] is not None)
            if key=="overall_conversion":claim["unit"]="无量纲"
            if result["status"]=="partial" and claim["target"]["deliverable"]:
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"漏斗含缺失步骤、未知量或零分母；已知步骤和完整分组仍保留。"}
    if receipt["tool_name"] in {"classification","regression_analysis","shap_analysis"}:
        for claim in facts:
            key=claim["basis_refs"][0]["result_path"][0]
            if receipt["tool_name"]=="shap_analysis":
                claim["target"].update(metric=result["target"],deliverable=key in {"shap_importance","per_class_importance","n_observations"} and (key=="shap_importance" or claim["value"] not in (None,[],{})))
                if key=="shap_importance" and claim["value"] is None:
                    claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"模型未返回全部类别解释；完整总体重要性未知。"}
            else:
                claim["target"].update(metric=result["target_col"],deliverable=key in {"metrics","feature_importance","class_metrics","confusion_matrix","coefficients_by_class","coefficients","train_size","test_size","cv"} and claim["value"] not in (None,[],{}))
                claim["limitations"].append("实际算法："+result["method"]+"；验证：random_holdout（按行，非时间验证）")
    if receipt["tool_name"]=="ab_test":
        for claim in facts:
            claim["target"].update(metric=result["metric_col"],deliverable=claim["basis_refs"][0]["result_path"][0] in {"groups","difference","test","contingency_table","paired_sample_size"})
            claim["limitations"].append("实际检验方法："+result["method"]+"；设计："+result["design"]+"；分析单位："+result["analysis_unit"])
        products=[(["test","p_value"],result["test"]["p_value"],"A/B检验p值","无量纲"),
                  (["test","statistic"],result["test"]["statistic"],"A/B检验统计量","无量纲")]
        if "difference" in result:
            products.append((["difference","absolute"],result["difference"]["absolute"],"A/B第二组减第一组差值（因果假设未验证）",None))
            if "confidence_interval_95" in result["difference"]:
                products.append((["difference","confidence_interval_95"],result["difference"]["confidence_interval_95"],"配对均值差95%区间",None))
        for path,value,label,unit in products:
            add(path,value,label,unit)
            facts[-1]["target"].update(metric=result["metric_col"],deliverable=True)
            facts[-1]["limitations"]=list(result["limitations"])+["实际方法："+result["method"]+"；设计："+result["design"]+"；分析单位："+result["analysis_unit"]]
            if value is None:facts[-1]["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"A/B样本不足或检验方差退化；该产物未知。"}
        if result.get("status")=="limited":
            for claim in facts:
                if claim["basis_refs"][0]["result_path"]==["test"]:
                    claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"A/B推断不足；统计量、p值或区间未知。"}
    if receipt["tool_name"]=="what_if_simulation" and result.get("mode")=="optimize":
        for claim in facts:
            claim["limitations"]=list(result["limitations"])+["实际方法：约束分配候选（份额/逐次剪裁）。"]
            if claim["basis_refs"][0]["result_path"]==["breakdown"] and result["status"]!="candidate_verified":
                claim["value"]=None
                claim["target"]["deliverable"]=True
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"当前方法未找到通过全部边界与目标复核的候选；不证明数学不可行。"}
    if receipt["tool_name"]=="what_if_simulation" and result.get("mode") in {"sensitivity","sensitivity_reverse","predict"}:
        for claim in facts:
            claim["limitations"]=list(result["limitations"])
            key=claim["basis_refs"][0]["result_path"]
            if result.get("status")=="limited" and key in (["breakdown"],["required_total_pct"]):
                claim["target"]["deliverable"]=True
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"总量为零且目标非零，等比例反推及比例未知；基线、目标和缺口仍可计算。"}
    if receipt["tool_name"]=="transform_data":
        if result.get("source_dataset")!=receipt["arguments"]["name"] or result.get("dataset") not in binding["data_identities"]:
            raise ContractError("native_transform_scope", "派生结果未绑定原执行来源和派生身份。")
        observed=result.get("source_observation")
        if observed is not None:
            if not isinstance(observed,dict) or result.get("operation")!="group_aggregate" or type(observed.get("rows")) is not int or type(result["rows"]) is not int or not 0<=result["rows"]<=observed["rows"]:
                raise ContractError("native_source_rows", "聚合源记录数或操作无效。")
            for claim in facts:
                if claim["basis_refs"][0]["result_path"]==["rows"]:
                    claim["label"]="派生表 "+result["dataset"]+" 记录数"
                    claim["unit"]="条"
                if claim["basis_refs"][0]["result_path"]==["source_observation"]:
                    claim["label"]="源数据观测范围"
                if claim["basis_refs"][0]["result_path"]==["measurement_records"]:
                    claim["limitations"].append("count：非空值个数；size：组内行数；nunique：非空唯一值个数；sum：全缺失保留未知")
            for column,window in observed.get("observation_window",{}).get("columns",{}).items():
                path=["source_observation","observation_window","columns",column]
                add(path,_days(window["min"],window["max"]),"源观测日期含首尾日数","天",window["min"]+"/"+window["max"],
                    {"operator":"inclusive_calendar_days","operand_paths":[path+["min"],path+["max"]]})
        if result["operation"]=="resample":
            details=_resample_effect_details(context,receipt["arguments"],result)
            for claim in facts:
                if claim["basis_refs"][0]["result_path"] in (["measurement_records"],["resample_audit"]):
                    claim["limitations"].append("空日期桶或全缺失 sum 为未知；真实观测零保留为零。")
                    if "completion_gap" in details:claim["target"]["completion_gap"]=deepcopy(details["completion_gap"])
        facts.extend(_confirmed_aggregate_claims(session_id,receipt,result,binding))
    if receipt["tool_name"]=="curve_fitting":
        args=receipt["arguments"]
        if args.get("compare_weights"):
            expected=context.workspace._publication_curve_sensitivity(args)
            if expected is None or encode(result.get("sensitivity"))!=encode(expected):
                raise ContractError("result_contract_mismatch", "敏感性比较与当前原观测、人数及成熟/零值筛选不一致。")
        elif "sensitivity" in result:
            raise ContractError("result_contract_mismatch", "未请求敏感性比较，原件不能自报独立比较值。")
        if args.get("compare_weights") and result["sensitivity"]["max_absolute_difference"] is not None:
            add(["sensitivity","max_absolute_difference"],result["sensitivity"]["max_absolute_difference"],"最大绝对口径敏感性差")
        unit=_confirmed_curve_unit(session_id,receipt)
        declared=args.get("value_scale","unknown")
        if declared!="unknown" and unit and unit!={"fraction":"proportion","percentage_points":"percent"}.get(declared):
            raise ContractError("unit_scope_conflict", "声明呈现口径与有效原单位确认冲突。")
        for index,point in enumerate(result.get("points",[])):
            _number(point["x"]);_number(point["y"])
            add(["points",index,"y"],point["y"],"观测点 "+str(point["x"]),unit)
            facts[-1]["target"]["metric"]=receipt["arguments"].get("y_col",point.get("column", ""))
    for claim in facts:
        params=receipt.get("arguments",{})
        metric=params.get("value_col") or params.get("target_col") or params.get("y_col")
        if metric: claim["target"].setdefault("metric",metric)
    # Project only descendants of an already validated public measurement.
    # Metadata, stdout and closed derivations cannot acquire field authority.
    public=list(facts)
    # Python exposes named business products at its result root. Keep each
    # product whole; recursively duplicating array cells makes the model view
    # grow with every fitted point and lets incidental internals look deliverable.
    paths=list(result_paths)
    if receipt["tool_name"]=="run_python" and isinstance(result.get("result_data"),dict):
        from data_agent.agent.context import get_current_context
        ctx=get_current_context()
        goals=getattr(getattr(ctx,"analysis_state",None),"answer_requirements",[])
        metrics={m for req in goals if req.get("lifecycle_status")=="active" for delivery in req.get("necessary_deliveries",[]) for m in delivery["scope"].get("metrics",[])}
        paths.extend(["result_data",key] for key,value in result["result_data"].items() if key in metrics and value is not None)
    for path in paths:
        if any(c["basis_refs"][0]["result_path"]==path for c in facts): continue
        parent=next((c for c in public if c["target"].get("deliverable",True) and not c.get("derivation")
            and len(c["basis_refs"])==1 and len(path)>len(c["basis_refs"][0]["result_path"])
            and path[:len(c["basis_refs"][0]["result_path"])]==c["basis_refs"][0]["result_path"]),None)
        if parent is None: continue
        label=parent["label"]+" / "+" / ".join(str(k) for k in path[len(parent["basis_refs"][0]["result_path"]):])
        try:
            projected=resolve_result_claim(session_id=session_id,receipt_id=receipt_id,
                claim_id="c_"+digest(encode([receipt_id,path,label]))[7:31],label=label,result_path=path,
                scope=parent["scope"],limitations=parent["limitations"])
        except ContractError as exc:
            if exc.code=="result_field": continue
            raise
        projected["target"]=deepcopy(parent["target"])
        projected["target"]["deliverable"]=projected["value"] is not None
        if not projected["target"].get("metric") and isinstance(path[-1],str):
            projected["target"]["metric"]=path[-1]
        facts.append(projected)
    for claim in facts:
        product=_minimal_business_product(claim,receipt,result)
        if product is not None: claim["target"]["business_product"]=product
        if receipt["tool_name"]=="curve_fitting":
            path=claim["basis_refs"][0]["result_path"]
            if path==["sensitivity","max_absolute_difference"]:
                claim["label"]="最大绝对口径敏感性差"
            if path==["sensitivity"] and not result["sensitivity"]["points"]:
                claim["target"]["completion_gap"]={"status":"evidence_insufficient","reason":"没有共同成熟且有效的可比较观测，最大差未知。"}
            if (path==["points"] or len(path)==3 and path[0]=="points" and path[-1]=="y") and args.get("value_scale","unknown")!="unknown":
                state=context.analysis_state
                ids=set(receipt.get("required_delivery_ids",[]))
                declarations=[d for req in state.answer_requirements if req.get("lifecycle_status")=="active" for d in req.get("necessary_deliveries",[]) if d["id"] in ids]
                if any(d.get("scope",{}).get("parameters",{}).get("curve_value_scale")==args["value_scale"]
                       and args["name"] in d["scope"].get("datasets",[])
                       and product and set(product.get("metrics",[])) <= set(d["scope"].get("metrics",[]))
                       and all(product.get("parameters",{}).get(k)==v for k,v in d["scope"].get("parameters",{}).items())
                       for d in declarations):
                    claim["target"]["curve_display"]={"value_scale":args["value_scale"],"basis":"plan_declaration","source_unit_verified":unit is not None}
                    if unit is None: claim["limitations"].append("按本次计划声明的呈现口径显示；原值保留，源单位未独立核定。")
    # Successful native products own these closed data/method coverage limits.
    # Arbitrary requirement failures and audit rejection prose are not facts.
    for claim in facts:
        gap = claim.get("target", {}).get("completion_gap")
        if gap and gap["reason"] not in claim["limitations"]:
            claim["limitations"].append(gap["reason"])
    from .source_units import apply_source_units
    return apply_source_units(context,receipt,result,facts)


def _validate_model_scenario(receipt,result,binding):
    import json
    from data_agent.tools.ml import _model_key
    def reject(message):raise ContractError("result_contract_mismatch",message)
    args=receipt["arguments"];identity=result.get("model_identity",{});changes=json.loads(args["feature_changes"])
    if args.get("mode")!="predict" or result.get("target_col")!=args["target_col"] or identity.get("target_col")!=args["target_col"] or identity.get("kind")!="regression" or identity.get("model_key")!=_model_key(args["name"],"regression",args["target_col"]) or identity.get("data_identity")!=binding["data_identities"].get(args["name"]):reject("模型情景没有绑定本会话当前来源的回归目标。")
    if result.get("claim_ceiling")!="model_scenario" or result.get("model_reused") is not True or not isinstance(changes,dict) or not changes or changes!=result.get("feature_changes") or set(changes)-set(identity.get("feature_cols",[])):reject("模型情景改变量或模型复用合同不一致。")
    for value in changes.values():_number(value)
    predictions=result.get("scenario_predictions",{});n=result.get("effective_rows")
    if type(n) is not int or n<1 or result.get("source_rows",-1)-result.get("excluded_missing_rows",-1)!=n:reject("模型情景有效观测数不一致。")
    for key in ("baseline","projected"):
        values=predictions.get(key,[])
        if not isinstance(values,list) or len(values)!=n:reject("模型情景原逐行预测不完整。")
        for value in values:_number(value)
    baseline=sum(predictions["baseline"])/n;projected=sum(predictions["projected"])/n;impact=projected-baseline
    if result.get("baseline")!=round(baseline,4) or result.get("projected")!=round(projected,4) or result.get("impact")!={"absolute":round(impact,4),"relative_pct":round(impact/abs(baseline)*100,2) if baseline!=0 else None}:reject("模型情景均值或变化不等于原逐行预测。")


def _validate_sensitivity_result(receipt,result):
    def reject(message):raise ContractError("result_contract_mismatch",message)
    args=receipt["arguments"];reverse=bool(args.get("target_value"));mode="sensitivity_reverse" if reverse else "sensitivity"
    params={"simulation_mode":mode,"simulation_dimension":args["dimension"]}
    if args.get("mode","sensitivity")!="sensitivity" or result.get("mode")!=mode or result.get("metric")!=args["metric"] or result.get("dimension")!=args["dimension"] or result.get("claim_ceiling")!="arithmetic_scenario":reject("算术情景方法、指标、维度或结论边界不匹配。")
    basis=result.get("basis_by_dimension",{});rows=result.get("breakdown",[])
    if not isinstance(basis,dict) or not basis or len(rows)!=len(basis) or len({r.get("dimension_value") for r in rows})!=len(basis) or {r.get("dimension_value") for r in rows}!=set(basis):reject("算术情景遗漏或重复实际分组。")
    for value in basis.values():_number(value)
    baseline=sum(basis.values())
    def same(actual,expected):
        if expected is None:return actual is None
        return type(actual) in (int,float) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-8)
    if reverse:
        if args.get("dim_value"):reject("反推不能静默忽略维度选择。")
        target=float(args["target_value"]);_number(target);gap=target-baseline;unknown=baseline==0 and gap!=0
        params["simulation_target"]=target
        if any(not same(result.get(k),v) for k,v in {"baseline_total":baseline,"target":target,"gap":gap,"required_total_pct":gap/baseline*100 if baseline!=0 else None}.items()):reject("反推总量、目标、缺口或比例不一致。")
        for row in rows:
            value=basis[row["dimension_value"]];required=None if unknown else (gap*value/baseline if baseline!=0 else 0.0)
            pct=required/value*100 if required is not None and value!=0 else None
            if not same(row.get("current"),value) or not same(row.get("required_change"),required) or not same(row.get("required_pct"),pct):reject("反推分组算术或未知边界错误。")
    else:
        change=args.get("change_pct",0);_number(change);selected=args.get("dim_value","");unknown=False
        params["simulation_change_pct"]=change
        if selected:
            if selected not in basis:reject("情景没有唯一实际维度选择。")
            params["simulation_dimension_value"]=selected
        projected=0.0
        for row in rows:
            key=row["dimension_value"];value=basis[key];new=value*(1+change/100) if not selected or key==selected else value;projected+=new
            if not same(row.get("baseline"),value) or not same(row.get("projected"),new) or not same(row.get("change"),new-value):reject("正向分组算术错误。")
        impact=projected-baseline;pct=impact/baseline*100 if baseline!=0 else None
        if not same(result.get("baseline",{}).get("total"),baseline) or not same(result.get("projected",{}).get("total"),projected) or not same(result.get("impact",{}).get("absolute"),impact) or not same(result.get("impact",{}).get("relative_pct"),pct):reject("正向情景总量或影响不一致。")
    if result.get("scenario_parameters")!=params or result.get("status")!=("limited" if unknown else "arithmetic_complete"):reject("情景参数或可计算状态与原派发不同。")


def _validate_allocation_result(receipt,result):
    import json
    def reject(reason):raise ContractError("result_contract_mismatch",reason)
    args=receipt["arguments"]
    constraints=json.loads(args.get("constraints") or "{}") if isinstance(args.get("constraints",""),str) else args["constraints"]
    if result.get("method")!="share_allocation_sequential_clipping" or result.get("goal_pct")!=args.get("goal_pct",0) or result.get("constraints")!=constraints or result.get("dimension")!=args.get("dimension") or result.get("metric")!=(args.get("target_metric") or args.get("metric")) or result.get("default_bounds")!={"min":-100,"max":100}:reject("分配的实际方法、目标或约束与原派发不同。")
    basis=result.get("basis_by_dimension",{})
    if not basis:reject("分配缺少各维原基数。")
    for value in basis.values():
        _number(value)
        if value<=0:reject("分组基数不为正。")
    baseline=sum(basis.values());target=baseline*(1+result["goal_pct"]/100)
    if not math.isclose(result["baseline"],baseline,rel_tol=1e-10,abs_tol=1e-8) or not math.isclose(result["target"],target,rel_tol=1e-10,abs_tol=1e-8):reject("分配总量与目标算术不匹配。")
    if result.get("status")=="candidate_not_found":
        if result.get("breakdown")!=[] or result.get("projected") is not None or result.get("actual_pct") is not None:reject("未核候选仍输出分配或预计总量。")
        return
    if result.get("status")!="candidate_verified" or result.get("verification")!={"all_bounds_satisfied":True,"target_satisfied":True}:reject("候选没有全部约束/目标核验。")
    rows=result.get("breakdown",[])
    if len(rows)!=len(basis) or {r.get("dimension_value") for r in rows}!=set(basis):reject("候选维度遗漏或重复。")
    for row in rows:
        dv=row["dimension_value"];current=basis[dv];c=constraints.get(dv,{})
        lower,upper=c.get("min",-100),c.get("max",100)
        for key in ("current","required_change","required_pct","min_pct","max_pct"):_number(row[key])
        if row["current"]!=current or row["min_pct"]!=lower or row["max_pct"]!=upper or not lower-1e-9<=row["required_pct"]<=upper+1e-9 or not math.isclose(row["required_change"],current*row["required_pct"]/100,rel_tol=1e-10,abs_tol=1e-8):reject("交付候选越界或每维变化算术错误。")
    projected=baseline+sum(r["required_change"] for r in rows)
    if not math.isclose(projected,target,rel_tol=1e-10,abs_tol=1e-8) or not math.isclose(result.get("projected",float("nan")),projected,rel_tol=1e-10,abs_tol=1e-8):reject("交付候选没有达到目标。")


def _validate_supervised_result(receipt,result,binding):
    """Verify declared algorithm and metrics from the original holdout predictions."""
    def reject(message):raise ContractError("result_contract_mismatch",message)
    args=receipt["arguments"];tool=receipt["tool_name"];requested=args.get("method","auto")
    algorithms={"classification":{"auto":"GradientBoostingClassifier","logistic":"LogisticRegression","rf":"RandomForestClassifier"},
                "regression_analysis":{"auto":"GradientBoostingRegressor","gbrt":"GradientBoostingRegressor","rf":"RandomForestRegressor","linear":"ElasticNet"}}
    if result.get("requested_method")!=requested or result.get("method")!=algorithms[tool].get(requested) or result.get("target_col")!=args["target_col"]:
        reject("模型实际算法、请求方法或目标指标与原派发不同。")
    if result.get("method_contract")!="analysis_method_result.v1" or result.get("data_identity")!=binding["data_identities"].get(args["name"]):reject("模型结果没有匹配原派发数据版本。")
    features=result.get("feature_cols",[])
    if not features or len(set(features))!=len(features) or args["target_col"] in features:reject("模型特征为空、重复或包含目标泄漏。")
    if args.get("features") and features!=list(dict.fromkeys(c.strip() for c in args["features"].split(",") if c.strip())):reject("模型特征与显式选择不同。")
    validation=result.get("validation",{});n=result.get("test_size");train=result.get("train_size")
    if type(n) is not int or type(train) is not int or min(n,train)<1 or validation.get("effective_rows")!=n+train or validation.get("scheme")!="random_holdout" or validation.get("stratified") is not False or validation.get("time_aware") is not False:
        reject("模型留出样本数或原验证设计不匹配。")
    if validation.get("random_state")!=42 or validation.get("test_fraction")!=.2 or validation.get("split_unit")!="row" or validation.get("source_rows",-1)-validation.get("excluded_missing_rows",-1)!=n+train or n!=math.ceil((n+train)*.2):reject("模型验证参数或有效样本数与原随机留出不一致。")
    truth=result.get("evaluation",{}).get("y_true",[]);pred=result.get("evaluation",{}).get("y_pred",[])
    if len(truth)!=n or len(pred)!=n:reject("模型原留出预测与样本数不同。")
    if tool=="classification":
        k=result.get("n_classes");mapping=result.get("label_mapping",[])
        if type(k) is not int or k<2 or len(mapping)!=k or [entry.get("encoded") for entry in mapping]!=list(range(k)) or any(type(v) is not int or not 0<=v<k for v in truth+pred):reject("分类原标签或编码不完整。")
        if result.get("positive_class")!=(mapping[1]["label"] if k==2 else None):reject("默认正类与公开标签映射不匹配。")
        matrix=[[sum(t==i and p==j for t,p in zip(truth,pred)) for j in range(k)] for i in range(k)]
        if result.get("confusion_matrix")!=matrix:reject("分类混淆计数不等于原留出预测。")
        precision=[];recall=[];f1=[]
        rows=result.get("class_metrics",[])
        if len(rows)!=k:reject("分类每类指标遗漏。")
        for i,row in enumerate(rows):
            tp=matrix[i][i];positive=sum(matrix[j][i] for j in range(k));support=sum(matrix[i]);p=tp/positive if positive else 0;r=tp/support if support else 0;f=2*p*r/(p+r) if p+r else 0
            precision.append(p);recall.append(r);f1.append(f)
            expected={"encoded":i,"label":mapping[i]["label"],"support":support,"precision":round(p,4),"recall":round(r,4),"f1":round(f,4)}
            if row!=expected:reject("分类每类指标与原混淆计数不同。")
        metrics={"accuracy":round(sum(t==p for t,p in zip(truth,pred))/n,4),"f1_macro":round(sum(f1)/k,4),"precision_macro":round(sum(precision)/k,4),"recall_macro":round(sum(recall)/k,4)}
        if k==2:metrics.update(f1=round(f1[1],4),precision=round(precision[1],4),recall=round(recall[1],4))
    else:
        for value in truth+pred:_number(value)
        mean=sum(truth)/n;sse=sum((a-b)**2 for a,b in zip(truth,pred));sst=sum((a-mean)**2 for a in truth)
        metrics={"r2":round(1-sse/sst if sst else 1 if not sse else 0,4),"rmse":round(math.sqrt(sse/n),4),"mae":round(sum(abs(a-b) for a,b in zip(truth,pred))/n,4)}
    if result.get("metrics")!=metrics:reject("模型评估指标不等于原留出预测的算术结果。")
    folds=args.get("cv_folds",0);cv=result.get("cv")
    if bool(folds)!=bool(cv):reject("模型CV执行与声明不一致。")
    if folds:
        if cv.get("scheme")!=("stratified_kfold_without_shuffle" if tool=="classification" else "kfold_without_shuffle") or cv.get("scoring")!=("accuracy" if tool=="classification" else "r2"):reject("模型CV设计或评分与声明不同。")
        scores=cv.get("scores",[])
        if cv.get("folds")!=folds or len(scores)!=folds:reject("模型CV折数不匹配。")
        for value in scores:_number(value)
        mean=sum(scores)/folds;std=math.sqrt(sum((v-mean)**2 for v in scores)/folds)
        if cv.get("mean")!=round(mean,4) or cv.get("std")!=round(std,4):reject("CV均值和标准差与各折分数不一致。")


def _validate_shap_result(receipt,result,binding):
    def reject(message):raise ContractError("result_contract_mismatch",message)
    from data_agent.tools.ml import _model_key
    model=result.get("model_identity",{});features=model.get("feature_cols",[]);kind=model.get("kind")
    args=receipt["arguments"]
    if result.get("method_contract")!="analysis_method_result.v1" or result.get("data_identity")!=binding["data_identities"].get(args["name"]) or model.get("model_key")!=_model_key(args["name"],kind,args["target_col"]):reject("SHAP模型不是本会话原派发的当前数据版本。")
    if type(result.get("n_observations")) is not int or result["n_observations"]<1:reject("SHAP实际解释观测数无效。")
    if result.get("target")!=receipt["arguments"]["target_col"] or model.get("target_col")!=result.get("target") or kind not in {"classification","regression"} or not features or result.get("n_features")!=len(features):reject("SHAP目标、模型或特征不匹配。")
    if receipt["arguments"].get("model_kind","auto") not in {"auto",kind}:reject("SHAP原模型类型与显式选择不同。")
    def vector(rows):
        if not isinstance(rows,list) or len(rows)!=len(features) or {r.get("feature") for r in rows}!=set(features):reject("SHAP重要性遗漏原特征。")
        values={}
        for row in rows:
            value=row.get("mean_abs_shap");_number(value)
            if value<0:reject("SHAP绝对重要性不能为负。")
            values[row["feature"]]=value
        return values
    overall=result.get("shap_importance");per_class=result.get("per_class_importance",[])
    if kind=="regression":
        if result.get("aggregation")!="mean_abs_across_observations" or per_class:reject("回归SHAP不应冒充分类聚合。")
        vector(overall)
    elif result.get("aggregation")=="equal_weight_mean_across_classes":
        labels=[entry["label"] for entry in model.get("label_mapping",[])]
        if [row.get("label") for row in per_class]!=labels or not labels or result.get("unexplained_classes"):reject("分类SHAP遗漏原类别。")
        vectors=[vector(row["importance"]) for row in per_class];total=vector(overall)
        # Each public class mean is rounded to 6 decimals; averaging those
        # displayed values may differ from rounding the raw mean by <=1e-6.
        if any(abs(total[f]-sum(v[f] for v in vectors)/len(vectors))>1.000001e-6 for f in features):reject("SHAP总体不是明确的各类等权平均。")
    elif result.get("aggregation")=="single_model_output":
        if result.get("status")!="limited" or overall is not None or not result.get("unexplained_classes") or len(per_class)!=1:reject("单输出SHAP不能冒充完整类别平均。")
        labels=[entry["label"] for entry in model.get("label_mapping",[])]
        if len(labels)!=2 or per_class[0].get("label")!=labels[1] or result["unexplained_classes"]!=labels[:1]:reject("SHAP单输出类别与原二分类映射不同。")
        vector(per_class[0]["importance"])
    else:reject("SHAP聚合方式不支持。")


def _validate_ab_result(receipt,result):
    """Bind the actual design and check original group arithmetic before delivery."""
    def reject(message):raise ContractError("result_contract_mismatch",message)
    args=receipt["arguments"];requested=args.get("method","auto")
    if result.get("requested_method")!=requested or any(result.get(k)!=args[k] for k in ("group_col","metric_col")):
        reject("A/B指标、组或请求方法与派发参数不同。")
    design=result.get("design");method=result.get("method")
    allowed={"paired_ttest"} if design=="paired" and requested in {"auto","ttest"} else {"ttest","mannwhitneyu"} if design=="independent" and requested=="auto" else {requested} if design=="independent" else set()
    if method not in allowed:reject("A/B实际方法与设计不匹配；不能静默更换显式方法。")
    if args.get("unit_col") and result.get("analysis_unit")!=args["unit_col"]:reject("A/B分析单位不匹配。")
    if result.get("analysis_unit")!="row" and result.get("unit_aggregation")!=args.get("unit_aggregation","sum"):reject("A/B单位聚合口径不匹配。")
    if result.get("assumptions")!={"random_assignment":"unverified","independence":"unverified"}:reject("A/B设计不能自动证明随机分配或独立性。")
    groups=result.get("groups",{});test=result.get("test",{})
    if len(groups)!=2 or any(type(v.get("n")) is not int or v["n"]<0 for v in groups.values()):reject("A/B必须完整保留两组样本数。")
    for key in ("statistic","p_value"):
        if test.get(key) is not None:
            _number(test[key])
            if key=="p_value" and not 0<=test[key]<=1:reject("A/B p值越界。")
    if method=="chi2":
        table=result.get("contingency_table",{})
        if set(table)!=set(groups) or len(next(iter(table.values()),{}))<2:reject("A/B列联表缺组或类别。")
        for g,row in table.items():
            if any(type(v) is not int or v<0 for v in row.values()) or sum(row.values())!=groups[g]["n"]:reject("A/B列联计数与样本数不一致。")
        return
    exact=result.get("exact_statistics",{})
    if set(exact)!=set(groups):reject("A/B原精度组统计缺失。")
    for g,v in exact.items():
        if v["n"]!=groups[g]["n"]:reject("A/B样本数不一致。")
        if v["mean"] is not None:_number(v["mean"])
        if groups[g]["mean"]!=(round(v["mean"],4) if v["mean"] is not None else None):reject("A/B显示均值不等于原精度均值。")
        if v["sample_variance"] is not None:
            _number(v["sample_variance"])
            if v["sample_variance"]<0:reject("A/B样本方差无效。")
    a,b=list(exact.values());diff=b["mean"]-a["mean"] if a["mean"] is not None and b["mean"] is not None else None
    difference=result.get("difference",{})
    if difference.get("absolute")!=(round(diff,4) if diff is not None else None):reject("A/B差值不等于原两组均值相减。")
    limited=result.get("status")=="limited"
    if design=="paired":
        proof=result.get("paired_difference_statistics",{});n=result.get("paired_sample_size")
        if n!=a["n"] or n!=b["n"] or proof.get("n")!=n or not (proof.get("mean")==diff or diff is not None and proof.get("mean") is not None and math.isclose(proof["mean"],diff,rel_tol=1e-12,abs_tol=1e-12)):
            reject("A/B配对数或配对差均值不一致。")
        variance=proof.get("sample_variance")
        insufficient=n<2 or variance in (None,0)
    else:
        insufficient=min(a["n"],b["n"])<2 or method=="ttest" and a["sample_variance"]==b["sample_variance"]==0
    if insufficient!=limited:reject("A/B样本或方差不足状态不一致。")
    if limited:
        if any(test.get(k) is not None for k in ("statistic","p_value","significant")) or difference.get("confidence_interval_95") is not None:
            reject("A/B推断不足不能生成显著性或区间。")
    elif method in {"ttest","paired_ttest"}:
        from scipy.special import stdtr
        if design=="paired":
            if variance<0:reject("配对方差无效。")
            se=math.sqrt(variance/n);degrees=n-1
        else:
            va,vb=a["sample_variance"],b["sample_variance"];na,nb=a["n"],b["n"]
            if result.get("levene_test",{}).get("equal_variance"):
                degrees=na+nb-2;se=math.sqrt(((na-1)*va+(nb-1)*vb)/degrees*(1/na+1/nb))
            else:
                se=math.sqrt(va/na+vb/nb);degrees=(va/na+vb/nb)**2/((va/na)**2/(na-1)+(vb/nb)**2/(nb-1))
        statistic=diff/se;p_value=float(2*stdtr(degrees,-abs(statistic)))
        if test.get("statistic")!=round(statistic,4) or test.get("p_value")!=round(p_value,6) or test.get("significant")!=bool(p_value<.05):reject("A/B t推断与原组方差或配对差方差不一致。")
        if design=="paired":
            from scipy.special import stdtrit
            critical=float(stdtrit(degrees,.975))
            if difference.get("confidence_interval_95")!=[round(diff-critical*se,4),round(diff+critical*se,4)]:reject("A/B配对区间与原差值方差不一致。")


def _validate_did_result(receipt,result):
    """Verify four-cell arithmetic and preserve missing inference as a local gap."""
    def reject(reason): raise ContractError("result_contract_mismatch",reason)
    args=receipt["arguments"];outcome=args.get("target_col") or args.get("outcome_col")
    if result.get("method")!="DID" or args.get("method","did")!="did" or any(result.get(key)!=value for key,value in {"outcome_col":outcome,"treatment_col":args["treatment_col"],"time_col":args["time_col"]}.items()):
        reject("DID原方法或指标/组/期次列与派发参数不同。")
    keys={f"treatment={t}_period={p}" for t in (0,1) for p in (0,1)}
    tables=[result.get(key) for key in ("cell_counts","exact_cell_means","group_means","cell_variances")]
    if any(not isinstance(table,dict) or set(table)!=keys for table in tables):reject("DID缺少完整四格原测量。")
    counts,means,shown,variances=tables
    for key in keys:
        n=counts[key];value=means[key];variance=variances[key]
        if type(n) is not int or n<0:reject("DID单元样本量无效。")
        if value is not None:_number(value)
        if variance is not None:_number(variance)
        if (n==0)!=(value is None) or shown[key]!=(round(value,4) if value is not None else None) or (n<2)!=(variance is None) or variance is not None and variance<0:
            reject("DID单元原均值、样本方差与观测数不一致。")
    if result.get("total_observations")!=sum(counts.values()) or result.get("assumptions")!={"parallel_trends":"unverified","independent_groups":"unverified"}:
        reject("DID样本数或未验证假设边界不一致。")
    unknown=any(n==0 for n in counts.values())
    if unknown:
        if result.get("did_effect") is not None or result.get("reason_code")!="missing_did_cell":reject("缺DID单元不能生成效应或以零替代。")
        se=None
    else:
        control=means["treatment=0_period=1"]-means["treatment=0_period=0"]
        treated=means["treatment=1_period=1"]-means["treatment=1_period=0"]
        effect=treated-control
        if any(result.get(key)!=round(value,4) for key,value in {"did_effect":effect,"control_diff":control,"treatment_diff":treated}.items()):reject("DID效应不是原四格均值之差。")
        se=None if any(v is None for v in variances.values()) else math.sqrt(sum(variances[key]/counts[key] for key in keys))
    if result.get("standard_error")!=(round(se,4) if se is not None else None):reject("DID标准误与四格方差不一致。")
    if se is None or se==0:
        if any(result.get(key) is not None for key in ("ci_95","p_value","t_statistic","significant_at_005")) or result.get("status")!="limited" or not result.get("inference_limitation"):
            reject("DID推断不足时不能授予区间、p值或显著性。")
    else:
        z=effect/se;p=math.erfc(abs(z)/math.sqrt(2))
        if result.get("ci_95")!=[round(effect-1.96*se,4),round(effect+1.96*se,4)] or result.get("p_value")!=round(p,6) or result.get("t_statistic")!=round(z,4) or result.get("significant_at_005")!=bool(p<.05) or result.get("status")!="supported":
            reject("DID独立四格近似的区间或p值与原测量不一致。")


def _validate_forecast_result(context,receipt,result):
    actual=context.workspace._publication_forecast_result(receipt["arguments"])
    if actual is None or result!=actual:
        raise ContractError("result_contract_mismatch","预测时间戳、点值、留出误差、残差启发带、真实筛样或参数与原来源不一致。")


def _validate_time_synthesis_result(context,receipt,result):
    actual=context.workspace._publication_time_synthesis_result(receipt["arguments"])
    if actual is None or actual!=result:
        raise ContractError("result_contract_mismatch","多来源日聚合原值、有限范围、参数、来源身份或实际派生对象与原回执不一致。")


def _validate_time_series_result(context,receipt,result):
    actual=context.workspace._publication_time_series_result(receipt["arguments"])
    if actual is None or result!=actual:
        raise ContractError("result_contract_mismatch","时间序列原统计、逐记录趋势、完整窗口、自相关候选或有效范围与实际来源不一致。")


def _validate_factor_result(context,receipt,result):
    actual=context.workspace._publication_factor_result(receipt["arguments"])
    if actual is None or result!=actual:
        raise ContractError("result_contract_mismatch","因素系数、HC3/Holm 推断、VIF、真实筛样或单位/时间范围与原来源不一致。")


def _validate_contribution_result(context,receipt,result):
    actual=context.workspace._publication_contribution_result(receipt["arguments"])
    if actual is None or result!=actual:
        raise ContractError("result_contract_mismatch","贡献分解的原算法、均值/条数、窗口、百分比分母或排除范围与真实来源不一致。")


def _validate_top_n_result(context,receipt,result):
    actual=context.workspace._publication_top_n_result(receipt["arguments"])
    if actual is None or result!=actual:
        raise ContractError("result_contract_mismatch","TopN 原值、排序范围、参数或真实派生对象与来源不一致。")


def _validate_segmentation_result(context,receipt,result):
    actual=context.workspace._publication_segmentation_result(receipt["arguments"])
    if actual is None or result!=actual:
        raise ContractError("result_contract_mismatch","分群实际簇数、原特征/算法参数、样本描述或缺失排除范围与真实来源不一致。")


def _validate_cohort_result(context,receipt,result):
    actual=context.workspace._publication_cohort_result(receipt["arguments"])
    if actual is None or "error" in actual or result!=actual:
        raise ContractError("result_contract_mismatch","留存月份轴、原参数、去重人数/比例或观测排除范围与真实来源不一致。")


def _validate_funnel_result(context,receipt,result):
    actual=context.workspace._publication_funnel_result(receipt["arguments"])
    if actual is None or {k:v for k,v in result.items() if k!="_suggested_next"}!=actual:
        raise ContractError("result_contract_mismatch","漏斗路径、总体/分组、计数/比例与原派发和实际范围不一致。")


def _validate_distribution_result(context,receipt,result):
    actual=context.workspace._publication_distribution_audit(receipt["arguments"]["name"],receipt["arguments"].get("columns",""))
    def reject():raise ContractError("result_contract_mismatch","分布列、有限观测范围或正态性边界与原派发不一致。")
    if actual is None or set(result)-{"_suggested_next"}!=set(actual):reject()
    for column,audit in actual.items():
        row=result[column];n=audit["observation"]["count"];constant=audit["constant_sample"]
        if not isinstance(row,dict) or row.get("observation")!=audit["observation"] or row.get("constant_sample") is not constant or row.get("count")!=n or row.get("status")!=("partial" if audit["observation"]["excluded_nonfinite"] else "complete"):reject()
        if row.get("quantile_interpolation")!="linear" or row.get("quantiles")!=audit["quantiles"]:reject()
        if not isinstance(row.get("limitations"),list) or any(not isinstance(v,str) for v in row["limitations"]):reject()
        for key in ("mean","std","skewness","kurtosis"):
            if key not in row:reject()
            if row[key] is not None:_number(row[key])
        if n==0 and any(row[k] is not None for k in ("mean","std","skewness","kurtosis")):reject()
        if (n<2 or constant) and any(row[k] is not None for k in ("skewness","kurtosis")):reject()
        if row["std"] is not None and row["std"]<0:reject()
        normality=row.get("normality_test",{})
        if set(normality)!={"test","p_value","reject_normality","conclusion","reason"} or normality["test"]!="shapiro":reject()
        reason="insufficient_sample" if n<3 else "sample_limit" if n>=5000 else "constant_sample" if constant else ""
        if reason or normality["reason"]=="undefined_test":
            if normality["reason"]!=(reason or "undefined_test") or normality["p_value"] is not None or normality["reject_normality"] is not None or normality["conclusion"]!="unknown":reject()
        else:
            p=normality["p_value"];_number(p)
            if not 0<=p<=1 or normality["reason"] or normality["reject_normality"] is not (p<=.05) or normality["conclusion"]!=("rejected" if p<=.05 else "not_rejected"):reject()


def _validate_correlation_result(receipt,result):
    """Validate only this producer's declared matrix, not generic object shapes."""
    def reject(reason): raise ContractError("result_contract_mismatch",reason)
    args=receipt["arguments"];columns=result.get("columns_analyzed")
    if result.get("method")!=args.get("method","pearson") or result.get("method") not in {"pearson","spearman","kendall"}:
        reject("相关方法与派发参数不一致。")
    if not isinstance(columns,list) or not columns or any(not isinstance(c,str) or not c for c in columns) or len(set(columns))!=len(columns):
        reject("相关矩阵必须绑定不重复的实际数值列。")
    excluded=result.get("excluded_columns")
    if not isinstance(excluded,list) or any(not isinstance(c,str) for c in excluded) or len(set(excluded))!=len(excluded) or set(columns)&set(excluded):
        reject("相关矩阵的分析列与排除列不一致。")
    requested=list(dict.fromkeys(c.strip() for c in args.get("columns","").split(",") if c.strip()))
    if requested and (set(requested)!=set(columns)|set(excluded) or columns!=[c for c in requested if c not in excluded]):
        reject("相关矩阵列不属于原执行选择。")
    matrix=result.get("correlation_matrix");counts=result.get("pairwise_counts")
    for table in (matrix,counts):
        if not isinstance(table,dict) or set(table)!=set(columns) or any(not isinstance(row,dict) or set(row)!=set(columns) for row in table.values()):
            reject("相关矩阵或成对样本量不是完整的已分析列方阵。")
    for a in columns:
        for b in columns:
            value=matrix[a][b];n=counts[a][b]
            if value is not None and (type(value) not in {int,float} or not math.isfinite(value) or not -1<=value<=1):
                reject("相关系数必须在[-1,1]内或为未知。")
            if type(n) is not int or n<0 or type(counts[a][a]) is not int or type(counts[b][b]) is not int or n>min(counts[a][a],counts[b][b]):
                reject("成对样本量无效。")
            if matrix[b][a]!=value or counts[b][a]!=n or n<2 and value is not None:
                reject("相关矩阵对称性或最小样本量不一致。")


def _minimal_business_product(claim,receipt,result):
    """Unique closed adapter for declared producers; no type inference from values."""
    tool=receipt["tool_name"]; target=claim["target"]
    if tool not in MINIMAL_PRODUCT_CONTRACTS: return None
    path=claim["basis_refs"][0]["result_path"]
    parameters={}; metrics=[target["metric"]] if target.get("metric") else []
    quantity=target.get("statistic","value");kind=None
    if not target.get("deliverable",True): return {"kind":None}
    if claim.get("derivation",{}).get("operator")=="inclusive_calendar_days": quantity="calendar_days"
    if quantity in {"business_sum","accounting_net"}: quantity="value"
    if tool=="what_if_simulation":
        if result["mode"]=="optimize":
            if path==["breakdown"]:
                kind="scenario";metrics=[result["metric"]]
                parameters={"simulation_mode":"optimize","goal_pct":result["goal_pct"],"allocation_constraints":result["constraints"]}
        elif result["mode"]=="predict":
            if len(path)==1 and path[0] in {"baseline","projected","impact"}:
                kind="scenario";metrics=[result["target_col"]]
                parameters={"simulation_mode":"predict","simulation_feature_changes":result["feature_changes"],"simulation_output":path[0],"model_kind":"regression","model_algorithm":result["model_type"]}
        elif len(path)==1 and path[0] in {"baseline","baseline_total","projected","impact","breakdown","target","gap","required_total_pct"}:
            kind="scenario";metrics=[result["metric"]];parameters=dict(result["scenario_parameters"],simulation_output=path[0])
    elif tool=="compare_periods":
        args=result["parameters"]
        parameters={"comparison_date_col":args["date_col"],"comparison_dimensions":args["dimensions"],"comparison_formulas":args["metric_formulas"],"period_a":args["period_a"],"period_b":args["period_b"]}
        if path in (["metrics"],["comparisons"],["observation"]):
            kind="table";metrics=list(args["metrics"]);parameters["comparison_output"]="observation" if path==["observation"] else "comparison"
        else:
            kind="measurement";parameters["comparison_output"]="measurement"
            if target.get("statistic")=="ratio_of_sums":quantity="ratio_of_sums"
            elif "exact_aggregates" in path:quantity="difference" if path[-1]=="diff" else "sum"
            else:quantity={"change_pct":"relative_change","day_count":"calendar_days","row_count":"rows","rows":"rows"}.get(path[-1],"value")
    elif tool=="synthesize_time_series":
        if len(path)==1 and path[0] in {"aligned_data","aligned_rows","coverage","observation","missing_aligned_dates"}:
            kind="series" if path[0]=="aligned_data" else "measurement" if path[0]=="aligned_rows" else "table"
            quantity="count" if kind=="measurement" else "value";metrics=list(dict.fromkeys(result["parameters"]["metric_map"].values()))
            parameters={"synthesis_date_col":result["parameters"]["date_col"],"synthesis_metrics":deepcopy(result["parameters"]["metric_map"]),"synthesis_output":path[0]}
    elif tool=="interpret_dataset":
        if len(path)==1 and path[0] in RESULT_FIELDS[tool]:
            kind="table";parameters={"interpret_output":path[0]}
    elif tool=="suggest_column_types":
        if len(path)==1 and path[0] in {"suggestions","observation"}:
            kind="table";parameters={"type_advice_output":path[0]}
    elif tool=="detect_data_quality":
        if len(path)==1 and path[0] in {"issues","column_diagnostics","observation","rows","total_issues"}:
            kind="measurement" if path[0] in {"rows","total_issues"} else "table"
            quantity="count" if kind=="measurement" else "value"
            parameters={"quality_output":path[0]}
    elif tool in {"quick_profile","assess_readiness"}:
        kind="table";metrics=list(result["column_diagnostics"]);parameters={"diagnostic_output":path[0]}
        if tool=="quick_profile":parameters["profile_compact"]=receipt["arguments"].get("compact",False)
        else:parameters["readiness_intent"]=receipt["arguments"].get("intent","")
    elif tool in {"read_file","list_files"}:
        if path==(["content"] if tool=="read_file" else ["entries"]):
            kind="table";parameters=deepcopy(receipt["file_binding"]["parameters"])
    elif tool=="list_mcp_servers":
        if path in (["servers"],["health"]):kind="table";parameters={"catalog_scope":"current_visible","catalog_output":"mcp_servers" if path==["servers"] else "mcp_health"}
    elif tool=="list_skills":
        if path==["skills"]:kind="table";parameters={"catalog_scope":"current_visible","catalog_output":"skills"}
    elif tool=="list_data":
        if path in (["datasets"], ["transform_history"]):kind="table";parameters={"catalog_scope":"current_visible","catalog_output":path[0]}
    elif tool=="describe_dataset": kind="measurement"
    elif tool in {"classification","regression_analysis"}:
        key=path[0];parameters={"classification_method" if tool=="classification" else "regression_method":result["requested_method"],"cv_folds":receipt["arguments"].get("cv_folds",0),"model_algorithm":result["method"]}
        if len(path)==1 and key in {"metrics","feature_importance","class_metrics","confusion_matrix","coefficients_by_class","coefficients","cv"}:
            kind="fit";parameters["model_output"]=key;metrics=[result["target_col"]]
            if key in {"feature_importance","coefficients","coefficients_by_class"}:metrics+=result["feature_cols"]
        elif path in (["train_size"],["test_size"]):kind="measurement";quantity="count";parameters["model_output"]=key;metrics=[result["target_col"]]
    elif tool=="shap_analysis":
        parameters={"model_kind":result["model_identity"]["kind"],"shap_aggregation":result["aggregation"]}
        metrics=[result["target"]]
        if path in (["shap_importance"],["per_class_importance"]):kind="table";parameters["shap_output"]="overall" if path[0]=="shap_importance" else "per_class"
        elif path==["n_observations"]:kind="measurement";quantity="count";parameters["shap_output"]="observations"
    elif tool=="ab_test":
        outputs={("groups",):("groups","table"),("difference",):("difference","table"),("test",):("test","table"),
                 ("contingency_table",):("contingency","table"),("paired_sample_size",):("paired_sample_size","measurement"),
                 ("difference","absolute"):("difference","measurement"),("difference","confidence_interval_95"):("confidence_interval","table"),
                 ("test","p_value"):("p_value","measurement"),("test","statistic"):("statistic","measurement")}
        if tuple(path) in outputs:
            output,kind=outputs[tuple(path)];metrics=[result["metric_col"]]
            quantity="difference" if tuple(path)==("difference","absolute") else "count" if output=="paired_sample_size" else "value"
            parameters={"ab_method":result["requested_method"],"ab_design":result["design"],"ab_unit":result["analysis_unit"],"ab_output":output}
            if result.get("unit_aggregation"):parameters["unit_aggregation"]=result["unit_aggregation"]
    elif tool=="causal_analysis":
        outputs={"did_effect":("effect","measurement"),"ci_95":("confidence_interval","table"),"p_value":("p_value","measurement"),
                 "standard_error":("standard_error","measurement"),"group_means":("cell_means","table"),"cell_counts":("cell_counts","table"),"total_observations":("observations","measurement")}
        if len(path)==1 and path[0] in outputs:
            output,kind=outputs[path[0]]
            metrics=[result["outcome_col"]];quantity="count" if output=="observations" else "value"
            parameters={"causal_method":"did","causal_output":output}
    elif tool=="correlation_analysis":
        parameters={"correlation_method":result["method"]}
        if path==["correlation_matrix"]:
            kind="table";metrics=list(result["columns_analyzed"]);quantity="value"
        elif len(path)==3 and path[0]=="correlation_matrix" and claim["value"] is not None:
            kind="measurement";metrics=list(dict.fromkeys(path[1:]));quantity="value"
    elif tool=="analyze_time_series":
        args=result["parameters"];metrics=[args["value_col"]]
        parameters={"time_series_date_col":args["date_col"],"time_series_value_col":args["value_col"]}
        if len(path)==1 and path[0] in RESULT_FIELDS[tool]:
            kind="measurement" if path==["data_points"] else "table";quantity="count" if path==["data_points"] else "value";parameters["time_series_output"]=path[0]
    elif tool=="attribution_analysis":
        args=result["parameters"];metrics=[args["target"]]
        parameters={"factor_features":args["features"],"factor_unit_col":args["analysis_unit"],"factor_time_col":args["time_col"]}
        if len(path)==1 and path[0] in RESULT_FIELDS[tool]:
            kind="measurement" if path==["effective_n"] else "table";quantity="count" if path==["effective_n"] else "value";parameters["factor_output"]=path[0]
    elif tool=="contribute_decomposition":
        args=result["parameters"];metrics=[args["metric"]]
        parameters={"decomposition_dimension":args["dimension"],"decomposition_aggregation":args["agg_func"],"decomposition_date_col":args["date_col"],"period_a":args["period_a"],"period_b":args["period_b"]}
        if len(path)==1 and path[0] in {"decomposition","total_change","total_change_pct","period_a","period_b","comparability","daily_normalized","observation"}:
            kind="measurement" if path[0] in {"total_change","total_change_pct"} else "table"
            quantity="difference" if path[0]=="total_change" else "relative_change" if path[0]=="total_change_pct" else "value";parameters["decomposition_output"]=path[0]
    elif tool=="preview_data":
        if path in (["data"],["observation"]):
            kind="table";metrics=[];quantity="value"
            parameters={"preview_n":result["observation"]["requested_rows"],"preview_output":path[0]}
    elif tool=="top_n":
        args=result["parameters"];metrics=list(args["columns"])
        parameters={"topn_sort_by":args["sort_by"],"topn_ascending":args["ascending"],"topn_n":args["n"],"topn_columns":args["columns"]}
        if path in (["records"],["observation"],["n"]):
            kind="measurement" if path==["n"] else "table"
            quantity="count" if path==["n"] else "value";parameters["topn_output"]=path[0]
    elif tool=="segmentation_analysis":
        args=result["parameters"];metrics=list(args["features"])
        parameters={"segmentation_features":args["features"],"segmentation_n_clusters":args["n_clusters"]}
        if len(path)==1 and path[0] in {"clusters","observation","requested_n_clusters","n_clusters","total_samples"}:
            kind="table" if path[0] in {"clusters","observation"} else "measurement"
            quantity="value" if kind=="table" else "count";parameters["segmentation_output"]=path[0]
    elif tool=="cohort_analysis":
        args=result["parameters"]
        parameters={"cohort_user_col":args["user_col"],"cohort_time_col":args["time_col"],"cohort_event_col":args["event_col"]}
        if path in (["cohorts"],["observation"]):kind="table";parameters["cohort_output"]=path[0]
    elif tool=="funnel_analysis":
        args=result["parameters"]
        parameters={"funnel_mode":result["mode"],"funnel_steps":args["steps"],"funnel_dimension":args["dimension"],"funnel_window_hours":args["window_hours"],"funnel_user_col":args["user_col"],"funnel_event_col":args["event_col"],"funnel_time_col":args["time_col"],"funnel_step_col":args["step_col"],"funnel_count_col":args["count_col"],"funnel_rate_cols":args["rate_cols"]}
        if len(path)==1 and path[0] in {"steps","dimension_funnels","biggest_drop","overall_conversion"}:
            kind="measurement" if path[0]=="overall_conversion" else "table";parameters["funnel_output"]=path[0]
    elif tool=="distribution_analysis":
        metrics=[path[0]]
        kind="table" if len(path)==1 else "measurement"
    elif tool=="forecast":
        metrics=[result["parameters"]["target_col"]]
        kind="forecast" if path==["forecast"] else "table" if path in (["backtest"],["interval"],["observation"],["date_range"]) else None
        parameters={"forecast_periods":result["periods"],"forecast_date_col":result["date_col"],"forecast_method":result["parameters"]["requested_method"]}
        if kind:parameters["forecast_output"]=path[0]
    elif tool=="curve_fitting":
        args=receipt["arguments"]
        parameters={"zero_values":args.get("zero_values","exclude")}
        for argument,business,default in (("value_scale","curve_value_scale","unknown"),("compare_weights","curve_compare_weights",False)):
            if result.get("parameters",{}).get(argument,default)!=args.get(argument,default):
                raise ContractError("result_contract_mismatch", "曲线声明呈现或敏感性参数与原执行不一致。")
            if args.get(argument,default)!=default:parameters[business]=args[argument]
        for argument, business in (("weight_col", "curve_weight_col"), ("mature_through_col", "curve_mature_through_col")):
            if result.get("parameters",{}).get(argument, "") != args.get(argument, ""):
                raise ContractError("result_contract_mismatch", "曲线人数权重或成熟范围与原执行参数不一致。")
            if args.get(argument):
                parameters[business] = args[argument]
        if result.get("parameters",{}).get("zero_values") != parameters["zero_values"]:
            raise ContractError("result_contract_mismatch","曲线零值口径与原执行参数不一致。")
        if args.get("scenario_points"): parameters["scenario_points"]=deepcopy(args["scenario_points"])
        metrics=[args["y_col"]] if args.get("y_col") else [c.strip() for c in args.get("series_columns","").split(",") if c.strip()]
        kind={"points":"series","fits":"fit","scenarios":"scenario"}.get(path[0]) if len(path)==1 else None
        if path==["sensitivity"]:
            kind="table";parameters["curve_output"]="sensitivity"
        if path==["sensitivity","max_absolute_difference"]:
            kind="measurement";quantity="difference";parameters["curve_output"]="max_absolute_difference"
        if kind and path!=["sensitivity","max_absolute_difference"]: quantity="value"
        if path==["effective_n"]: kind="measurement";quantity="count"
        if len(path)==3 and path[0]=="points" and path[2] in {"x","y","n_observed","n_excluded_zeros"}:
            kind="measurement";quantity="count" if path[2].startswith("n_") else "value"
            if target.get("metric"): metrics=[target["metric"]]
        if len(path)==3 and path[0]=="fits" and path[2] in {"r_squared","sse","mean_residual","max_abs_residual"}: kind="measurement"
        if len(path)==4 and path[0]=="fits" and path[2]=="parameters" and path[3] in {"a","b"}: kind="measurement"
    return {"kind":kind,"metrics":metrics,"quantity":quantity,"parameters":parameters} if kind else {"kind":None}


def _confirmed_curve_unit(session_id,receipt):
    """A real, current business choice may scale matching original points only."""
    from data_agent.agent.context import get_current_context
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.session.history import load_canonical_history
    from .requirements import resolve_confirmation
    ctx=get_current_context()
    loaded=ConfirmationStore(__import__("data_agent.config",fromlist=["get_config"]).get_config().sessions_resolved,session_id).load()
    if loaded.integrity_status!="ok": return None
    units=[]
    args=receipt["arguments"]
    for record in loaded.records.values():
        mapping=record.resolution_params.get("measurement_mapping",{})
        if not mapping or mapping.get("dataset")!=args.get("name") or mapping.get("column")!=args.get("y_col") or mapping.get("x_column", "")!=args.get("x_col", ""):
            continue
        candidate=ctx.workspace._publication_measurement_candidate(session_id=session_id,turn_id=record.turn_id,canonical_history=load_canonical_history(session_id),**mapping)
        if candidate is None: continue
        try:
            from data_agent.agent.confirmation.models import ConfirmationRequest
            selected=resolve_confirmation(ConfirmationRequest.from_candidate(candidate))
            if selected["response"] in {"fraction","percentage_points"}:
                units.append("proportion" if selected["response"]=="fraction" else "percent")
        except (ValueError,KeyError,TypeError): pass
    return units[0] if units and len(set(units))==1 else None


def resolve_hypothesis_claims(*,session_id,hypothesis_set,evidence_records):
    from data_agent.agent.context import get_current_context
    from data_agent.agent.hypotheses import receipt_verified_hypothesis_measurements, receipt_verified_descriptive_directions, update_hypotheses_from_evidence
    ctx=get_current_context()
    if ctx is None or ctx.session_id!=session_id or ctx.analysis_state is None:
        raise ContractError("hypothesis_session", "假设没有当前执行上下文。")
    state=ctx.analysis_state
    if not hypothesis_set.get("plan_id") or (state.analysis_plan or {}).get("id")!=hypothesis_set["plan_id"]:
        raise ContractError("hypothesis_plan", "假设没有绑定当前真实计划。")
    registered=[r for r in state.hypothesis_sets if isinstance(r,dict) and r.get("id")==hypothesis_set.get("id")]
    if len(registered)!=1 or not registered[0].get("sha256"):
        raise ContractError("hypothesis_registration", "假设不是当前已注册的有摘要产物。")
    from pathlib import Path
    from data_agent.config import get_config
    own=(get_config().sessions_resolved/session_id).resolve()
    path=Path(registered[0]["artifact_path"]).resolve()
    if not path.is_relative_to(own):
        raise ContractError("hypothesis_artifact_scope", "假设产物不属于当前会话。")
    reference=path.relative_to(own).as_posix()
    source_artifact=resolve_artifact(session_id=session_id,artifact_id=registered[0]["id"],path=reference,
        kind="hypothesis_set",description="当前假设集",expected_sha256=registered[0]["sha256"])
    import json
    if encode(json.loads(path.read_text(encoding="utf-8")))!=encode(hypothesis_set):
        raise ContractError("hypothesis_artifact", "假设候选与宿主已注册原产物不一致。")
    hypotheses=hypothesis_set.get("hypotheses",[])
    if len({h.get("id") for h in hypotheses})!=len(hypotheses):
        raise ContractError("hypothesis_identity", "假设身份重复。")
    valid=[]
    for record in evidence_records:
        try:
            for rid in record.get("tool_receipt_ids",[]): load_receipt_result(session_id=session_id,receipt_id=rid)
            valid.append(record)
        except (ValueError,OSError,KeyError,TypeError): pass
    updated=update_hypotheses_from_evidence(hypothesis_set,valid,
        verified_measurements=receipt_verified_hypothesis_measurements(state,valid),
        verified_directions=receipt_verified_descriptive_directions(state,valid))
    from data_agent.agent.artifact_refs import hydrate_refs
    from data_agent.agent.hypotheses import _STATUS_LABELS, hypothesis_distinguishing_step
    plan=state.analysis_plan or {}
    contract_ids={cid for step in plan.get("method_plan",[]) for cid in step.get("dataset_contract_ids",[])}
    current_content=any(r.get("id") in contract_ids and r.get("dataset")==hypothesis_set["dataset"]
        and r.get("trust_resolution",{}).get("status")=="current"
        for r in hydrate_refs(state.dataset_contracts,trust_records=True))
    current_roles=current_content
    # Current receipt proof can also anchor the original pending competitors.
    # Their text remains a proposed explanation, never a relation grant.
    for record in valid:
        if record.get("plan_id")!=hypothesis_set["plan_id"] or record.get("dataset")!=hypothesis_set["dataset"]:continue
        for rid in record.get("tool_receipt_ids",[]):
            try:
                _,_,_,binding=load_receipt_result(session_id=session_id,receipt_id=rid)
                identity=binding["data_identities"].get(hypothesis_set["dataset"])
                if identity and ctx.workspace._receipt_identity_matches(hypothesis_set["dataset"],identity):current_content=True
            except (ValueError,OSError,KeyError,TypeError,PermissionError):pass
    claims,gaps=[],[]
    for item in updated["hypotheses"]:
        original_text=item.get("claim") if current_content and isinstance(item.get("claim"),str) else ""
        label="候选解释："+original_text if original_text else "假设 "+item["id"]
        relations=item.get("evidence_relations",[])
        next_step=hypothesis_distinguishing_step(item) if current_roles else ""
        if not current_roles and item.get("distinguishing_test",{}).get("kind"):
            next_step="原字段角色原件、版本或原权限尚未核定；无法列出具体区分检验。"
        if item["status"] not in {"supported","refuted","contested"} or not relations:
            gaps.append({"hypothesis_id":item["id"],"dataset":hypothesis_set["dataset"],"plan_id":hypothesis_set["plan_id"],"status":"evidence_insufficient","reason":label+"；"+_STATUS_LABELS.get(item["status"],item["status"])+("；"+next_step if next_step else "")+"；"+("缺少可核当前原测量关系。" if current_content else "原假设内容与当前对象、版本及原权限尚未核定；缺少可核当前原测量关系。"),
                "public_context":{"kind":"hypothesis_pending","hypothesis_id":item["id"],"dataset":hypothesis_set["dataset"],
                    "claim":original_text,"source_current":current_content,"roles_current":current_roles,
                    "candidate_action":next_step if current_roles else ""}})
            continue
        proofs=[]
        for relation in relations:
            _,receipt,result,binding=load_receipt_result(session_id=session_id,receipt_id=relation["receipt_id"])
            path=["trend","slope"] if receipt["tool_name"]=="analyze_time_series" else ["metrics",relation["metric"],"diff"]
            proof=_claim(receipt,dict(binding,session_id=session_id),path,result[path[0]][path[1]] if len(path)==2 else result[path[0]][path[1]][path[2]],"原测量")
            proofs.extend(proof["basis_refs"])
        claim=_claim(receipt,dict(binding,session_id=session_id),path,item["status"],label+" 的当前关系","hypothesis_status",
            limitations=["仅描述性关系；不授予因果或统计推断强度"],
            derivation={"operator":"hypothesis_relation","hypothesis_id":item["id"],"plan_id":hypothesis_set["plan_id"],"evidence_ids":[r["evidence_id"] for r in relations],"predicate":item.get("decision_rule",{}).get("predicate",""),"source_artifact":source_artifact})
        claim["basis_refs"]=proofs
        claim["target"].update(hypothesis_id=item["id"],metric=relation["metric"],statistic="hypothesis_status")
        claims.append(claim)
    return claims,gaps


def _preserved_column_proof(session_id, receipt, binding, dataset, columns):
    """One derive-field edge preserves original accounting inputs.

    Other transformations need their own algebra; names and expression strings
    alone cannot authorize a formula on an arbitrary derived dataset.
    """
    from data_agent.agent.context import get_current_context
    current=receipt["arguments"]["name"]
    if current == dataset:
        return []
    ctx=get_current_context()
    candidates=[r for r in ctx.analysis_state.tool_receipts if r.get("tool_name")=="derive_field"
                and r.get("arguments",{}).get("name")==dataset]
    proofs=[]
    if len(candidates)>32: raise ContractError("lineage_limit","派生列证明超过读取预算。")
    for old in candidates:
        # Other child versions remain auditable history, not candidates for
        # this exact current aggregate. Do not load stale siblings first.
        if old.get("data_identities",{}).get(current) != binding["data_identities"].get(current):
            continue
        _, parent, result, origin=load_receipt_result(session_id=session_id,receipt_id=old["id"])
        if result.get("dataset") != current: continue
        identities=origin["data_identities"]
        source=identities.get(dataset,{});child=identities.get(current,{})
        if (result.get("operation")!="derive_field" or result.get("source_dataset")!=dataset
                or result.get("field_name")!=parent["arguments"].get("field_name")
                or result.get("expression")!=parent["arguments"].get("expression")
                or result.get("rows")!=result.get("source_rows")
                or child!=binding["data_identities"].get(current)
                or child.get("parent_version_ids")!=[source.get("version_id")]
                or child.get("source_fingerprint")!=source.get("fingerprint")
                or not set(columns).issubset(result.get("preserved_columns",[]))):
            raise ContractError("lineage_preservation","派生列没有保全当前公式的原列、行范围和精确父版本。")
        proofs.append(_claim(parent,dict(origin,session_id=session_id),["preserved_columns"],result["preserved_columns"],"原列保全证据")["basis_refs"][0])
    if len(proofs)!=1: raise ContractError("lineage_origin","没有唯一当前原列保全回执。")
    return proofs


def _confirmed_aggregate_claims(session_id,receipt,result,binding):
    """User-confirmed names/formulas over exact original grouped sums."""
    from decimal import Decimal
    from data_agent.agent.context import get_current_context
    from data_agent.agent.confirmation.models import ConfirmationRequest
    from data_agent.agent.confirmation.store import ConfirmationStore
    from data_agent.session.history import load_canonical_history
    from data_agent.config import get_config
    from .requirements import resolve_confirmation
    import json
    args=receipt["arguments"]
    if args.get("operation")!="group_aggregate" or result.get("operation")!="group_aggregate" or result.get("source_dataset")!=args.get("name"):
        return []
    loaded=ConfirmationStore(get_config().sessions_resolved,session_id).load()
    if loaded.integrity_status!="ok": return []
    ctx=get_current_context();facts=[]
    for record in loaded.records.values():
        mapping=record.resolution_params.get("measurement_mapping",{})
        if not mapping.get("dataset") or mapping.get("x_column"): continue
        try:
            candidate=ctx.workspace._publication_measurement_candidate(session_id=session_id,turn_id=record.turn_id,canonical_history=load_canonical_history(session_id),**mapping)
            if candidate is None: continue
            choice=resolve_confirmation(ConfirmationRequest.from_candidate(candidate))
            from data_agent.tools.data_transform import _transform_parameters
            params=_transform_parameters(args);ops=params.get("agg",{})
            rows=result.get("measurement_records")
            if not isinstance(rows,list) or not rows: continue
            if not mapping.get("cost_scopes"):
                if mapping["dataset"]!=args.get("name"): continue
                column=mapping["column"]
                if choice["response"]!="raw" or "sum" not in (ops.get(column) if isinstance(ops.get(column),list) else [ops.get(column)]): continue
                groups=params.get("group_by",[])
                if isinstance(groups,str): groups=[groups]
                key=column+"_sum" if isinstance(ops[column],list) else column
                values,proofs=[],[]
                for i,row in enumerate(rows):
                    _number(row[key])
                    values.append({**{group:row[group] for group in groups},column:row[key]})
                    proofs.extend(_claim(receipt,binding,["measurement_records",i,key],row[key],"原聚合值")["basis_refs"])
                claim=_claim(receipt,binding,["measurement_records",0,key],values,mapping["exact_span"],
                    limitations=["用户仅确认该业务名称对应原列；单位未知；原分组SUM不授予因果或增量解释"],
                    derivation={"operator":"confirmed_business_sum","confirmation_id":choice["confirmation_id"],"response_id":choice["response_id"],"column":column,"operand_paths":[p["result_path"] for p in proofs]})
                claim["basis_refs"]=proofs
                claim["id"]="c_"+digest(encode([receipt["id"],mapping["source_message_ref"],choice]))[7:31]
                claim["target"].update(metric=mapping["exact_span"],statistic="business_sum",source_message_ref=mapping["source_message_ref"])
                facts.append(claim)
                continue
            if choice["response"]=="unconfirmed": continue
            formula=json.loads(choice["response"])
            columns=[formula["effect_column"],*formula["cost_columns"]]
            lineage=_preserved_column_proof(session_id,receipt,binding,mapping["dataset"],columns)
            if any("sum" not in (ops.get(col) if isinstance(ops.get(col),list) else [ops.get(col)]) for col in columns): continue
            totals={col:Decimal(0) for col in columns};proofs=[];paths=[]
            for i,row in enumerate(rows):
                for col in columns:
                    key=col+"_sum" if isinstance(ops[col],list) else col
                    value=row[key];_number(value)
                    path=["measurement_records",i,key];paths.append(path)
                    totals[col]+=Decimal(str(value))
                    proofs.extend(_claim(receipt,binding,path,value,"原聚合值")["basis_refs"])
            value=totals[columns[0]]-sum((totals[col] for col in columns[1:]),Decimal(0))
            claim=_claim(receipt,binding,paths[0],format(value,"f"),mapping["exact_span"],limitations=["仅按用户所选原列合计算账面差额；单位未知；不授予增量、促销因果或外推强度"],derivation={"operator":"confirmed_sum_difference","confirmation_id":choice["confirmation_id"],"response_id":choice["response_id"],"formula":formula,"operand_paths":paths})
            claim["basis_refs"]=proofs+lineage
            claim["id"]="c_"+digest(encode([receipt["id"],paths,mapping["source_message_ref"],choice]))[7:31]
            claim["target"].update(metric=mapping["exact_span"],statistic="accounting_net",source_message_ref=mapping["source_message_ref"])
            facts.append(claim)
        except (ValueError,OSError,KeyError,TypeError,OverflowError):
            continue # Missing/changed choices do not suppress independent original facts.
    return facts
