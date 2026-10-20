"""One host projection of necessary deliveries and verified receipt products.

Business declarations precede execution. Catalogue rows are rebuilt from native
claims and byte-verified artifacts, never from model completion or prose labels.
No catalogue state or second evidence ledger is persisted.
"""
from copy import deepcopy
from .contracts import ContractError, fields, text, encode, digest

CV_FOLDS_SCHEMA = {"type":"integer","anyOf":[{"const":0},{"minimum":2}]}

OPEN_KINDS = frozenset({"knowledge", "interpretation", "limitation", "conditional_action"})
QUANTITIES = frozenset({"value", "rows", "count", "sum", "mean", "std", "min", "max", "25%", "50%", "75%",
    "missing_count", "missing_pct", "unique_values", "top_values", "difference", "relative_change", "ratio_of_sums", "calendar_days"})
BUSINESS_PARAMETERS = frozenset({"formula_unit_columns","source_unit_columns","period_a", "period_b", "start_date", "end_date", "filters", "horizon", "forecast_periods", "forecast_date_col", "forecast_method", "forecast_output", "profile_compact", "readiness_intent", "diagnostic_output", "quality_output", "type_advice_output", "interpret_output", "comparison_date_col", "comparison_dimensions", "comparison_output", "comparison_formulas", "x_start", "x_end", "window_days", "chart_type", "scenario_points", "zero_values", "curve_weight_col", "curve_mature_through_col", "curve_value_scale", "curve_compare_weights", "curve_output", "correlation_method", "causal_method", "causal_output", "ab_method", "ab_design", "ab_unit", "ab_output", "unit_aggregation", "classification_method", "regression_method", "cv_folds", "model_algorithm", "model_output", "model_kind", "shap_aggregation", "shap_output", "simulation_mode", "goal_pct", "allocation_constraints", "simulation_dimension", "simulation_change_pct", "simulation_target", "simulation_dimension_value", "simulation_output", "simulation_feature_changes","funnel_mode","funnel_steps","funnel_dimension","funnel_window_hours","funnel_user_col","funnel_event_col","funnel_time_col","funnel_step_col","funnel_count_col","funnel_rate_cols","funnel_output","cohort_user_col","cohort_time_col","cohort_event_col","cohort_output","segmentation_features","segmentation_n_clusters","segmentation_output","topn_sort_by","topn_ascending","topn_n","preview_n","preview_output","topn_columns","topn_output","decomposition_dimension","decomposition_aggregation","decomposition_date_col","decomposition_output","factor_features","factor_unit_col","factor_time_col","factor_output","time_series_date_col","time_series_value_col","time_series_output","catalog_output","catalog_scope","file_scope","file_output","file_path","file_offset","file_limit","file_max_chars","file_pattern","file_sha256"})


def _bounded_text(limit=128):
    return {"type":"string", "minLength":1, "maxLength":limit, "pattern":r"\S"}


def business_scope_schema(*, required=False, measurement=False, operation=None, metadata=None):
    from .native import OPERATION_TOOLS
    names={"type":"array","minItems":1,"maxItems":16,"uniqueItems":True,"items":_bounded_text()}
    parameters={k:_bounded_text(512) for k in ("period_a","period_b","start_date","end_date","chart_type")}
    parameters.update({k:{"type":"integer","minimum":1} for k in ("horizon","forecast_periods","window_days")})
    parameters.update({k:{"type":"number"} for k in ("x_start","x_end")})
    parameters["forecast_periods"]["maximum"]=365
    parameters["comparison_formulas"]={"type":"object","maxProperties":32,"additionalProperties":{"type":"object","required":["operator","numerator","denominator"],"additionalProperties":False,"properties":{"operator":{"enum":["ratio_of_sums"]},"numerator":_bounded_text(),"denominator":_bounded_text()}}}
    parameters["catalog_output"]={"enum":["datasets","transform_history","skills","mcp_servers","mcp_health"]}
    parameters["catalog_scope"]={"const":"current_visible"}
    parameters.update({"file_scope":{"const":"current_readable"},"file_output":{"enum":["content","entries"]},
        "file_path":_bounded_text(2048),"file_pattern":_bounded_text(2048),"file_offset":{"type":"integer","minimum":0},
        "file_limit":{"type":["integer","null"],"minimum":1},"file_max_chars":{"type":"integer","minimum":1,"maximum":2000},
        "file_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"}})
    parameters["profile_compact"]={"type":"boolean"}
    parameters["readiness_intent"]={"type":"string","maxLength":512}
    parameters["interpret_output"]={"enum":["columns_classified","column_role_basis","grain_basis","theme_basis","date_observation","time_range","analysis_signals","data_shape","suggested_analyses","cross_dataset_hints"]}
    parameters["type_advice_output"]={"enum":["suggestions","observation"]}
    parameters["quality_output"]={"enum":["issues","column_diagnostics","observation","rows","total_issues"]}
    parameters["diagnostic_output"]={"enum":["shape","columns","quality","grain","grain_hint","readiness","warnings","summary","column_diagnostics","suggested_next","suggested_analyses","overall","findings","recommendations","rows","cols"]}
    parameters["comparison_date_col"]=_bounded_text()
    parameters["comparison_dimensions"]={"type":"array","uniqueItems":True,"items":_bounded_text()}
    parameters["comparison_output"]={"enum":["measurement","comparison","observation"]}
    parameters["forecast_date_col"]=_bounded_text()
    parameters["forecast_method"]={"enum":["auto","backtest"]}
    parameters["forecast_output"]={"enum":["forecast","backtest","interval","observation","date_range"]}
    parameters["curve_value_scale"]={"enum":["unknown","fraction","percentage_points"]}
    parameters["curve_compare_weights"]={"type":"boolean"}
    parameters["curve_output"]={"enum":["sensitivity","max_absolute_difference"]}
    parameters["zero_values"]={"type":"string","enum":["exclude","keep"]}
    parameters.update({key:_bounded_text() for key in ("curve_weight_col","curve_mature_through_col")})
    parameters["correlation_method"]={"type":"string","enum":["pearson","spearman","kendall"]}
    parameters["causal_method"]={"type":"string","enum":["did"]}
    parameters["causal_output"]={"type":"string","enum":["effect","confidence_interval","p_value","standard_error","cell_means","cell_counts","observations"]}
    parameters["ab_method"]={"type":"string","enum":["auto","ttest","mannwhitneyu","chi2"]}
    parameters["ab_design"]={"type":"string","enum":["paired","independent"]}
    parameters["ab_unit"]=_bounded_text()
    parameters["unit_aggregation"]={"type":"string","enum":["sum","mean"]}
    parameters["ab_output"]={"type":"string","enum":["groups","difference","test","p_value","statistic","confidence_interval","paired_sample_size","contingency"]}
    parameters["classification_method"]={"type":"string","enum":["auto","logistic","rf"]}
    parameters["regression_method"]={"type":"string","enum":["auto","linear","rf","gbrt"]}
    parameters["cv_folds"]=deepcopy(CV_FOLDS_SCHEMA)
    parameters["model_algorithm"]=_bounded_text()
    parameters["model_output"]={"type":"string","enum":["metrics","feature_importance","class_metrics","confusion_matrix","coefficients_by_class","coefficients","cv","train_size","test_size"]}
    parameters["model_kind"]={"type":"string","enum":["regression","classification"]}
    parameters["shap_aggregation"]={"type":"string","enum":["equal_weight_mean_across_classes","mean_abs_across_observations","single_model_output"]}
    parameters["shap_output"]={"type":"string","enum":["overall","per_class","observations"]}
    parameters["simulation_mode"]={"type":"string","enum":["sensitivity","sensitivity_reverse","predict","optimize"]}
    parameters["simulation_dimension"]=_bounded_text()
    parameters["simulation_dimension_value"]=_bounded_text()
    parameters["simulation_change_pct"]={"type":"number"}
    parameters["simulation_target"]={"type":"number"}
    parameters["simulation_output"]={"enum":["baseline","baseline_total","projected","impact","breakdown","target","gap","required_total_pct","feature_importance"]}
    parameters["simulation_feature_changes"]={"type":"object","minProperties":1,"additionalProperties":{"type":"number"}}
    parameters["goal_pct"]={"type":"number"}
    parameters["allocation_constraints"]={"type":"object"}
    parameters["funnel_mode"]={"enum":["steps","aggregate","rates"]}
    parameters["funnel_output"]={"enum":["steps","overall_conversion","dimension_funnels","biggest_drop"]}
    parameters["funnel_window_hours"]={"type":"integer","minimum":0}
    for key in ['funnel_steps', 'funnel_dimension', 'funnel_user_col', 'funnel_event_col', 'funnel_time_col', 'funnel_step_col', 'funnel_count_col', 'funnel_rate_cols']:parameters[key]={"type":"string","maxLength":1024}
    for key in ["cohort_user_col","cohort_time_col"]:parameters[key]=_bounded_text()
    parameters["cohort_event_col"]={"type":"string","maxLength":128}
    parameters["cohort_output"]={"enum":["cohorts","observation"]}
    parameters["synthesis_date_col"]=_bounded_text()
    parameters["synthesis_metrics"]={"type":"object","minProperties":2,"additionalProperties":_bounded_text()}
    parameters["synthesis_output"]={"enum":["aligned_data","aligned_rows","coverage","observation","missing_aligned_dates"]}
    for key in ["time_series_date_col","time_series_value_col"]:parameters[key]=_bounded_text()
    parameters["time_series_output"]={"enum":["statistics","trend","window_comparisons","change_points","autocorrelation","seasonality","observation","data_points","date_range"]}
    parameters["factor_features"]={"type":"array","uniqueItems":True,"items":_bounded_text()}
    for key in ["factor_unit_col","factor_time_col"]:parameters[key]={"type":"string","maxLength":128}
    parameters["factor_output"]={"enum":["estimates","bivariate_associations","observation","excluded_features","unstable_features","vif","unit_observation","time_observation","effective_n"]}
    parameters["decomposition_dimension"]=_bounded_text()
    parameters["decomposition_aggregation"]={"enum":["sum","mean"]}
    parameters["decomposition_date_col"]=_bounded_text()
    parameters["decomposition_output"]={"enum":["decomposition","total_change","total_change_pct","period_a","period_b","comparability","daily_normalized","observation"]}
    parameters["topn_sort_by"]=_bounded_text()
    parameters["topn_ascending"]={"type":"boolean"}
    parameters["preview_n"]={"type":"integer","minimum":1,"maximum":50}
    parameters["preview_output"]={"enum":["data","observation"]}
    parameters["topn_n"]={"type":"integer","minimum":1}
    parameters["topn_columns"]={"type":"array","minItems":1,"uniqueItems":True,"items":_bounded_text()}
    parameters["topn_output"]={"enum":["records","observation","n"]}
    parameters["segmentation_features"]={"type":"array","minItems":1,"uniqueItems":True,"items":_bounded_text()}
    parameters["segmentation_n_clusters"]={"type":"integer","minimum":1}
    parameters["segmentation_output"]={"enum":["clusters","observation","requested_n_clusters","n_clusters","total_samples"]}
    parameters["source_unit_columns"]={"type":"object","minProperties":1,"maxProperties":32,
        "description":"Explicit original metric-to-unit-column declaration, e.g. amount:currency. Host checks current source cells; no inferred currency or conversion.",
        "propertyNames":_bounded_text(),"additionalProperties":_bounded_text()}
    parameters["formula_unit_columns"]={"type":"object","minProperties":1,"maxProperties":32,"propertyNames":_bounded_text(),
        "description":"Explicit numerator/denominator original unit columns for the same ratio_of_sums formula;equal complete current labels cancel only,without conversion.",
        "additionalProperties":{"type":"object","required":["numerator","denominator"],"additionalProperties":False,
            "properties":{"numerator":_bounded_text(),"denominator":_bounded_text()}}}
    parameters["filters"]={"type":"object"}
    parameters["scenario_points"]={"type":"array","maxItems":16,"uniqueItems":True,"items":{"type":"number","exclusiveMinimum":0}}
    schema={"type":"object","additionalProperties":False,
        "required":(["datasets"] if required and not operation else [])+(["quantity"] if measurement else [])+(["operation"] if operation else []),
        "properties":{"operation":{"type":"object","additionalProperties":False,"required":["action","arguments"],"properties":{"action":{"type":"string","enum":sorted(OPERATION_TOOLS)},"arguments":{"type":"object","maxProperties":32}}},"datasets":deepcopy(names),"metrics":deepcopy(names),"hypothesis_ids":deepcopy(names),
            "quantity":{"type":"string","enum":sorted(QUANTITIES)},
            "parameters":{"type":"object","additionalProperties":False,"properties":parameters}}}
    if operation is False:schema["properties"].pop("operation")
    catalog={"required":["parameters"],"properties":{"parameters":{"required":["catalog_scope"]+(["catalog_output"] if required else [])}}}
    if metadata is False or measurement or operation:
        schema["properties"]["parameters"]["properties"].pop("catalog_scope")
        schema["properties"]["parameters"]["properties"].pop("file_scope")
    else:
        file_condition={"required":["parameters"],"properties":{"parameters":{"required":["file_scope"]}}}
        file_declaration={"required":["parameters"],"properties":{"parameters":{"required":["file_scope","file_output"],"oneOf":[
            {"required":["file_path","file_offset"],"properties":{"file_output":{"const":"content"}},"not":{"required":["file_pattern"]}},
            {"required":["file_pattern"],"properties":{"file_output":{"const":"entries"}},"not":{"anyOf":[{"required":[k]} for k in ("file_path","file_offset","file_limit","file_max_chars","file_sha256")]}}
        ]}},"not":{"anyOf":[{"required":["metrics"]},{"required":["parameters"],"properties":{"parameters":{"required":["catalog_scope"]}}}]}}
        file_declaration["properties"].update(datasets={"maxItems":0},quantity={"const":"value"})
        ordinary_condition={"anyOf":[catalog,file_condition]}
        schema["properties"]["datasets"]["minItems"]=0
        schema["allOf"]=[{"if":ordinary_condition,"then":{},"else":{"properties":{"datasets":{"minItems":1}}}}]
        if required:
            schema["required"]=[k for k in schema["required"] if k!="datasets"]
            schema["allOf"].append({"if":ordinary_condition,"then":{},"else":{"required":["datasets"]}})
        schema["allOf"].append({"if":{"required":["parameters"],"properties":{"parameters":{"required":["catalog_scope"]}}},"then":catalog})
        schema["allOf"].append({"if":file_condition,"then":file_declaration})
        schema["allOf"].append({"if":{"required":["parameters"],"properties":{"parameters":{"required":["catalog_output"],"properties":{"catalog_output":{"enum":["skills","mcp_servers","mcp_health"]}}}}},
            "then":{"properties":{"datasets":{"maxItems":0},"quantity":{"const":"value"}},"not":{"required":["metrics"]}}})
    schema.setdefault("allOf",[]).append({
        "if":{"required":["parameters"],"properties":{"parameters":{"required":["source_unit_columns"]}}},
        "then":{"required":["metrics"],"properties":{"quantity":{"not":{"enum":["rows","count","calendar_days"]}}}}})
    schema["allOf"].append({"if":{"required":["parameters"],"properties":{"parameters":{"required":["formula_unit_columns"]}}},
        "then":{"required":["metrics"],"properties":{"parameters":{"required":["comparison_formulas"]},"quantity":{"not":{"enum":["rows","count","calendar_days"]}}}}})
    return schema


def is_catalog_scope(value):
    parameters=value.get("parameters",{}) if isinstance(value,dict) else {}
    return parameters.get("catalog_scope")=="current_visible" and parameters.get("catalog_output") in {"datasets","transform_history","skills","mcp_servers","mcp_health"}


def is_file_scope(value):
    p=value.get("parameters",{}) if isinstance(value,dict) else {}
    return p.get("file_scope")=="current_readable" and p.get("file_output") in {"content","entries"}


def validate_business_scope(value, *, required=False, measurement=False, operation=None, metadata=None):
    from jsonschema import Draft7Validator
    errors=list(Draft7Validator(business_scope_schema(required=required,measurement=measurement,operation=operation,metadata=metadata)).iter_errors(value))
    if errors:
        error=errors[0]
        code="business_quantity" if list(error.path)==["quantity"] else "business_parameters" if list(error.path)[:1]==["parameters"] else "business_scope"
        raise ContractError(code, "/".join(map(str,error.path))+": "+error.message)
    units=value.get("parameters",{}).get("source_unit_columns")
    if units and (not set(units).issubset(value.get("metrics",[])) or value.get("quantity") in {"rows","count","calendar_days"}):
        raise ContractError("source_unit_scope", "源单位映射必须属于当前明确度量，不能授予行数/记录数/日数币种。")
    params=value.get("parameters",{});formula_units=params.get("formula_unit_columns",{})
    if formula_units and (not set(formula_units).issubset(value.get("metrics",[]))
            or value.get("quantity") in {"rows","count","calendar_days"} or set(formula_units)&set(units or {})
            or any(params.get("comparison_formulas",{}).get(m,{}).get("operator")!="ratio_of_sums" for m in formula_units)):
        raise ContractError("source_unit_scope", "公式单位必须显式绑定同一ratio_of_sums的两端，不能与输出单列单位重叠。")
    value=deepcopy(value)
    if "operation" in value:
        from .native import operation_spec
        value["operation"]=operation_spec(value["operation"]["action"],value["operation"]["arguments"])
    encode(value)
    return value


def _kind(claim):
    target=claim.get("target",{}); tool=target.get("tool"); path=claim["basis_refs"][0]["result_path"]
    if "business_product" in target:
        return target.get("business_product",{}).get("kind")
    key=path[0]; value=claim["value"]
    if not target.get("deliverable",True): return None
    if claim.get("derivation",{}).get("operator")=="hypothesis_relation": return "hypothesis"
    if tool=="analyze_time_series": return "series" if key in {"trend","statistics","metrics","change_points","seasonality","aligned_rows"} and len(path)==1 else "measurement" if not isinstance(value,(dict,list)) else None
    if isinstance(value,(dict,list)): return "table"
    return "measurement"


def catalogue(claims, artifacts=(), effects=()):
    """Only callers that resolved native proofs may supply these objects."""
    from data_agent.agent.context import get_current_context
    ctx=get_current_context()
    receipts={r["id"]:r for r in getattr(getattr(ctx,"analysis_state",None),"tool_receipts",[]) if r.get("id")}
    def producing_ids(ids):
        return sorted({d for rid in ids for d in receipts.get(rid,{}).get("required_delivery_ids",[])})
    rows=[]
    for claim in claims:
        kind=_kind(claim)
        if kind is None: continue
        target=claim.get("target",{}); path=claim["basis_refs"][0]["result_path"]
        product=target.get("business_product")
        parameters=product["parameters"] if product and product.get("kind") else target.get("parameters",{})
        identities={n:i for proof in claim["basis_refs"] for n,i in proof["data_identities"].items()}
        metrics={target["metric"]} if target.get("metric") else set()
        value=claim["value"]
        if product: metrics=set(product.get("metrics",[]))
        if not product and isinstance(value,list) and value and all(isinstance(r,dict) for r in value):
            metrics.update(set.intersection(*(set(r) for r in value)))
        if not product and isinstance(value,dict): metrics.update(k for k,v in value.items() if not isinstance(v,(dict,list)))
        quantity=product.get("quantity") if product else target.get("statistic")
        if quantity in {"accounting_net","business_sum"}: quantity="value"
        if claim.get("derivation",{}).get("operator")=="inclusive_calendar_days": quantity="calendar_days"
        if quantity is None:
            quantity={"diff":"difference","change_pct":"relative_change","day_count":"calendar_days", "row_count":"rows", "rows":"rows"}.get(path[-1],"value")
            if "exact_aggregates" in path and path[-1] in {"period_a","period_b","a","b"}: quantity="sum"
        declared=producing_ids(p["receipt_id"] for p in claim["basis_refs"])
        derivation=claim.get("derivation",{})
        if kind=="hypothesis" and ctx is not None and derivation.get("plan_id")== (ctx.analysis_state.analysis_plan or {}).get("id"):
            declared=sorted(set(declared) | {d["id"] for r in ctx.analysis_state.answer_requirements if r.get("lifecycle_status")=="active" for d in r.get("necessary_deliveries",[]) if d["kind"]=="hypothesis"})
        members=[claim["id"]]
        if target.get("tool")=="curve_fitting" and path==["points"]:
            members.extend(c["id"] for c in claims if c["id"]!=claim["id"] and c["basis_refs"][0]["receipt_id"]==claim["basis_refs"][0]["receipt_id"] and c["basis_refs"][0]["result_path"][:1]==["points"])
        rows.append({"id":claim["id"],"kind":kind,"claim_ids":members,"artifact_ids":[],
            "catalog_binding":deepcopy(claim["basis_refs"][0].get("catalog_binding")),
            "file_binding":deepcopy(claim["basis_refs"][0].get("file_binding")),
            "skills_binding":deepcopy(claim["basis_refs"][0].get("skills_binding")),
            "mcp_binding":deepcopy(claim["basis_refs"][0].get("mcp_binding")),
            "data_identities":deepcopy(identities),"metrics":sorted(metrics),"quantity":quantity,
            "parameters":deepcopy(parameters) if product else {k:deepcopy(v) for k,v in parameters.items() if k in BUSINESS_PARAMETERS},
            "hypothesis_ids":[target["hypothesis_id"]] if target.get("hypothesis_id") else [],
            "receipt_ids":list(dict.fromkeys(p["receipt_id"] for p in claim["basis_refs"])),
            "completion_gap":deepcopy(target.get("completion_gap")), "source_message_ref":target.get("source_message_ref"), "declared_delivery_ids":declared,
            "requires_execution_binding":any(p["tool_name"]=="run_python" for p in claim["basis_refs"])})
    for effect in effects:
        rows.append({"id":effect["id"],"kind":"operation","claim_ids":[],"artifact_ids":[],"effect_ids":[effect["id"]],
            "operation":{"action":effect["action"],"arguments":deepcopy(effect["arguments"])},
            "data_identities":deepcopy(effect["before"].get("source_data_identities",{})),"metrics":[],"quantity":None,"parameters":{},
            "hypothesis_ids":[],"receipt_ids":[effect["receipt_id"]],"completion_gap":deepcopy(effect.get("completion_gap")),"declared_delivery_ids":producing_ids([effect["receipt_id"]])})
    for artifact in artifacts:
        target=artifact.get("target",{})
        if not target.get("data_identities") or not target.get("receipt_id"): continue
        params=target.get("parameters",{})
        metrics=[params[k] for k in ("x","y","x_col","y_col","value_col","column") if isinstance(params.get(k),str) and params[k]]
        rows.append({"id":artifact["id"],"kind":"chart" if target.get("tool") in {"create_chart","plot_chart"} or artifact["type"] in {"chart","plot"} else "artifact",
            "claim_ids":[],"artifact_ids":[artifact["id"]],"data_identities":deepcopy(target["data_identities"]),
            "metrics":sorted(set(metrics)),"quantity":None,"parameters":{k:deepcopy(v) for k,v in params.items() if k in BUSINESS_PARAMETERS},
            "hypothesis_ids":[],"receipt_ids":[target["receipt_id"]],"completion_gap":deepcopy(target.get("completion_gap")),"declared_delivery_ids":producing_ids([target["receipt_id"]])})
    if len({r["id"] for r in rows})!=len(rows): raise ContractError("catalogue_identity", "交付目录身份重复。")
    return rows


def matches(delivery, row, expected, *, explicit=False):
    if delivery["kind"]!=row["kind"]: return False
    if delivery["id"] not in row["declared_delivery_ids"] and (not explicit or row.get("requires_execution_binding") or delivery["kind"] == "operation"):
        return False
    scope=delivery["scope"]
    if delivery["kind"]=="operation" and scope.get("operation")!=row.get("operation"):return False
    if not set(scope.get("metrics",[])).issubset(row["metrics"]): return False
    if "quantity" in scope and scope["quantity"]!=row["quantity"]: return False
    if not set(scope.get("hypothesis_ids",[])).issubset(row["hypothesis_ids"]): return False
    if any(row["parameters"].get(k)!=v for k,v in scope.get("parameters",{}).items()): return False
    if is_file_scope(scope):
        return delivery["kind"]=="table" and isinstance(row.get("file_binding"),dict) and not row["data_identities"] and not scope.get("datasets")
    if is_catalog_scope(scope) and scope["parameters"]["catalog_output"] in {"mcp_servers","mcp_health"}:
        return delivery["kind"]=="table" and isinstance(row.get("mcp_binding"),dict) and not row["data_identities"] and not scope.get("datasets")
    if is_catalog_scope(scope) and scope["parameters"]["catalog_output"]=="skills":
        return delivery["kind"]=="table" and isinstance(row.get("skills_binding"),dict) and not row["data_identities"] and not scope.get("datasets")
    if is_catalog_scope(scope):
        return delivery["kind"]=="table" and isinstance(row.get("catalog_binding"),dict) and row["parameters"].get("catalog_scope")=="current_visible" and all(row["data_identities"].get(n)==expected.get(n) and n in expected for n in scope.get("datasets",[]))
    sources=scope.get("datasets",[])
    if any(n not in expected for n in sources): return False
    actual=row["data_identities"]
    authorized_roots={encode(o) for n in sources for o in expected[n].get("source_origins",[])}
    for name in sources:
        identity=expected[name]
        if not any(current==identity or (identity.get("version_id") in current.get("ancestor_version_ids",[])
                and bool(identity.get("source_origins"))
                and {encode(o) for o in identity["source_origins"]}.issubset({encode(o) for o in current.get("source_origins",[])}))
                for current in actual.values()): return False
    # An actual extra source cannot borrow one authorized anchor. Derived
    # sources need replayable host ancestry; generated file names grant nothing.
    if any(name not in sources and (not i.get("source_origins")
            or not {encode(o) for o in i["source_origins"]}.issubset(authorized_roots)
            or not any(i.get("version_id")==expected[n].get("version_id") or expected[n].get("version_id") in i.get("ancestor_version_ids",[]) for n in sources))
           for name,i in actual.items()): return False
    return True


def _bound_chart_failure_targets(context, binding, arguments):
    """Resolve a failed attempt only to its current predeclared chart deliveries."""
    if context is None or not isinstance(binding, dict): return []
    producer = binding.get("producer_binding", {})
    if producer != {"session_id":context.session_id,"tool_name":"create_chart","arguments":arguments}: return []
    state=context.analysis_state; plan=state.analysis_plan or {}
    if not binding.get("plan_id") or binding["plan_id"]!=plan.get("id") or binding.get("plan_sha256")!=plan.get("plan_sha256"): return []
    step=next((s for s in plan.get("method_plan",[]) if s["step_id"]==binding.get("step_id")),None)
    if step is None or set(binding.get("requirement_ids",[]))!=set(step.get("requirement_ids",[])) or set(binding.get("required_delivery_ids",[]))!={d["id"] for d in step.get("required_deliveries",[])}: return []
    identities=binding.get("input_data_identities",{})
    if not identities or any(context.workspace.get_data_identity(n)!=i for n,i in identities.items()): return []
    targets=[]
    for req in state.answer_requirements:
        if req.get("lifecycle_status")!="active" or req["id"] not in binding["requirement_ids"]: continue
        for delivery in req.get("necessary_deliveries",[]):
            scope=delivery["scope"];names=scope.get("datasets",[])
            if (delivery["id"] not in binding["required_delivery_ids"] or delivery["kind"]!="chart"
                    or set(names)!={arguments.get("data")} or any(req.get("source_data_identities",{}).get(n)!=identities.get(n) for n in names)
                    or any(arguments.get(k)!=v for k,v in scope.get("parameters",{}).items())): continue
            targets.append((req,delivery))
    return targets


def record_chart_delivery_failure(context, binding, arguments, structured_data, *, is_error):
    """Annotate the existing goal, without a positive receipt or another ledger."""
    targets=_bound_chart_failure_targets(context,binding,arguments)
    if not targets:return
    state=context.analysis_state;before=deepcopy(state.answer_requirements)
    failure=structured_data if isinstance(structured_data,dict) else {}
    typed=(is_error and failure.get("error_type")=="chart_validation" and isinstance(failure.get("error_code"),str)
           and bool(failure["error_code"]) and isinstance(failure.get("error"),str) and bool(failure["error"]))
    for req,delivery in targets:
        if typed:
            req.setdefault("source_binding",{}).setdefault("delivery_failures",{})[delivery["id"]]={
                "tool_name":"create_chart","code":failure["error_code"],"reason":failure["error"],
                "execution_binding":deepcopy(binding),"arguments":deepcopy(arguments)}
        elif not is_error:
            req.get("source_binding",{}).get("delivery_failures",{}).pop(delivery["id"],None)
    if state.answer_requirements!=before:
        try:state.save()
        except BaseException:
            state.answer_requirements=before
            raise


def project_deliveries(requirements, claims, artifacts=(), *, effects=(), product_gaps=()):
    rows=catalogue(claims,artifacts,effects); result={}
    for req in requirements:
        if req.get("lifecycle_status")!="active": continue
        expected=req.get("source_data_identities",{})
        selected=req.get("catalogue_bindings",{})
        for delivery in req.get("necessary_deliveries",[]):
            if delivery["kind"] in OPEN_KINDS: continue
            candidates=[r for r in rows if matches(delivery,r,expected,explicit=delivery["id"] in selected) and (not r.get("source_message_ref") or r["source_message_ref"]==req["source_message_ref"])]
            if delivery["id"] not in selected:
                paths={c["id"]:c["basis_refs"][0]["result_path"] for c in claims}
                # Whole products cover their internal cells; retain a specific
                # child only when its business type/scope excludes the parent.
                candidates=[r for r in candidates if not any(other["id"]!=r["id"] and other["receipt_ids"]==r["receipt_ids"]
                    and other["id"] in paths and r["id"] in paths and len(paths[other["id"]])<len(paths[r["id"]])
                    and paths[r["id"]][:len(paths[other["id"]])]==paths[other["id"]] for other in candidates)]
            if delivery["id"] in selected:
                candidates=[r for r in candidates if r["id"] in selected[delivery["id"]]]
            from data_agent.agent.context import get_current_context
            ctx = get_current_context()
            from data_agent.agent.artifact_refs import trust_delivery_gap
            trust_gap = trust_delivery_gap(getattr(ctx, "analysis_state", None), delivery, candidates) if ctx else None
            if trust_gap:
                candidates = []
            gaps=[r["completion_gap"] for r in candidates if r["completion_gap"]]
            if trust_gap:
                gaps.append(trust_gap)
            if delivery["kind"]=="hypothesis":
                scope=delivery["scope"]
                missing=[g for g in product_gaps if g.get("hypothesis_id") and g.get("dataset") in scope["datasets"] and (not scope.get("hypothesis_ids") or g["hypothesis_id"] in scope["hypothesis_ids"])]
                gaps.extend({"status":"evidence_insufficient","reason":g["hypothesis_id"]+"："+g["reason"]} for g in missing)
            from data_agent.agent.context import get_current_context
            ctx=get_current_context()
            associated={r["id"] for r in getattr(getattr(ctx,"analysis_state",None),"tool_receipts",[]) if delivery["id"] in r.get("required_delivery_ids",[])}
            receipts={r["id"]:r for r in getattr(getattr(ctx,"analysis_state",None),"tool_receipts",[])}
            def concerns_source(gap):
                receipt=receipts.get(gap.get("receipt_id"),{})
                sources=set(receipt.get("dataset_refs",[])) | set(receipt.get("data_identities",{}))
                versions={v for identity in receipt.get("data_identities",{}).values()
                          for v in [identity.get("version_id"),*identity.get("ancestor_version_ids",[])] if v}
                required=set(delivery["scope"].get("datasets",[]))
                return not required or bool(required & sources) or any(expected.get(n,{}).get("version_id") in versions for n in required)
            invalid=[g for g in product_gaps if not candidates and g.get("receipt_id") in associated and (not g.get("delivery_ids") or delivery["id"] in g["delivery_ids"]) and concerns_source(g)]
            gaps.extend({"status":"failed" if g.get("code")=="result_contract_mismatch" else "evidence_insufficient","reason":"产物核验 ["+g.get("code","receipt_unavailable")+"]："+g["reason"]} for g in invalid)
            explicit_ids={c["id"] for c in claims if c.get("target",{}).get("business_product",{}).get("kind")}
            incompatible=[r for r in rows if r["id"] in explicit_ids and r["kind"]==delivery["kind"]
                and delivery["id"] in r["declared_delivery_ids"]
                and set(delivery["scope"].get("metrics",[])).issubset(r["metrics"])
                and ("quantity" not in delivery["scope"] or delivery["scope"]["quantity"]==r["quantity"])]
            if not candidates and incompatible and not gaps:
                gaps.append({"status":"failed","reason":"product_scope_mismatch：实际产物的来源、指标、统计量或业务参数与声明不一致；不能要求用户补数据。"})
            if not candidates and not incompatible and not invalid and delivery["kind"]=="forecast":
                if ctx is not None and any(r.get("tool_name")=="forecast" and delivery["id"] in r.get("required_delivery_ids",[]) for r in ctx.analysis_state.tool_receipts):
                    gaps.append({"status":"evidence_insufficient","reason":"没有实际预测序列："+delivery["label"]+"。"})
            chart_failure=req.get("source_binding",{}).get("delivery_failures",{}).get(delivery["id"])
            if not candidates and isinstance(chart_failure,dict) and chart_failure.get("tool_name")=="create_chart":
                valid=_bound_chart_failure_targets(ctx,chart_failure.get("execution_binding"),chart_failure.get("arguments"))
                if any(r["id"]==req["id"] and d["id"]==delivery["id"] for r,d in valid):
                    gaps.append({"status":"failed","reason":"图表失败 ["+chart_failure["code"]+"]："+chart_failure["reason"]})
            failure=req.get("source_binding",{}).get("operation_failures",{}).get(delivery["id"])
            if (not candidates and delivery["kind"]=="operation" and isinstance(failure,dict)
                    and failure.get("operation")==delivery["scope"].get("operation")):
                gaps.append({"status":"failed","reason":"操作失败 ["+failure["code"]+"]："+failure["reason"]})
            if len(gaps)>1:gaps=[{"status":"failed" if any(g["status"]=="failed" for g in gaps) else "evidence_insufficient","reason":"；".join(dict.fromkeys(g["reason"] for g in gaps))}]
            result[delivery["id"]]={"requirement_id":req["id"],"kind":delivery["kind"],"label":delivery["label"],
                "catalogue_ids":[r["id"] for r in candidates],
                "claim_ids":list(dict.fromkeys(c for r in candidates for c in r["claim_ids"])),
                "artifact_ids":list(dict.fromkeys(a for r in candidates for a in r["artifact_ids"])),
                "effect_ids":list(dict.fromkeys(e for r in candidates for e in r.get("effect_ids",[]))),
                "gap":dict(gaps[0],reason=delivery["label"]+"（"+", ".join(delivery["scope"].get("hypothesis_ids",[]))+"）："+gaps[0]["reason"]) if gaps else None if candidates else {"status":"not_computed","reason":"尚无当前同来源、指标、窗口和类型的交付："+delivery["label"]+"（"+", ".join(delivery["scope"].get("hypothesis_ids",delivery["scope"].get("datasets",[])))+"）。"}}
    return rows,result
