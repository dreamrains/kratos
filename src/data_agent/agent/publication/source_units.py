"""Source unit projection from current bound originals; no label inference or conversion."""
from copy import deepcopy
import pandas as pd
import numpy as np
from .contracts import encode


def apply_source_units(context,receipt,result,facts):
    state=context.analysis_state;rid=receipt['id'];name=receipt.get('arguments',{}).get('name')
    identity=receipt.get('data_identities',{}).get(name)
    versions={v for v in [*(identity or {}).get('ancestor_version_ids',[]),(identity or {}).get('version_id')] if v}
    # A shared execution step does not merge independent objects' unit fields.
    # Ancestor-bound scopes remain relevant and keep the existing conservative gate.
    declarations=[(req,d) for req in state.answer_requirements if req.get('lifecycle_status')=='active' and req['id'] in receipt.get('requirement_ids',[]) for d in req.get('necessary_deliveries',[]) if d['id'] in receipt.get('required_delivery_ids',[]) and any(d['scope'].get('parameters',{}).get(k) for k in ('source_unit_columns','formula_unit_columns'))
        and (name in d['scope'].get('datasets',[]) or any(req.get('source_data_identities',{}).get(n,{}).get('version_id') in versions for n in d['scope'].get('datasets',[])))]
    if not declarations:return facts
    # Keep the original execution plan as authority when a later plan replaces it.
    plan=_source_unit_plan(context,receipt)
    plan_scopes={(step['step_id'],d['id'],d['requirement_id']):d for step in plan.get('method_plan',[]) for d in step.get('required_deliveries',[])}
    valid_source=identity is not None and context.workspace._receipt_identity_matches(name,identity)
    proofs={};gaps=[]
    for req,delivery in declarations:
        scope=delivery['scope'];params=scope['parameters'];mapping={**params.get('source_unit_columns',{}),**params.get('formula_unit_columns',{})}
        for metric,column in mapping.items():
            reason=None;units=[];count=0;public_code='unit_unverified'
            if plan_scopes.get((receipt.get('step_id'),delivery['id'],req['id']))!=delivery:reason='执行前正式计划及单位声明不能核定。'
            elif set(scope.get('datasets',[]))!={name} or req.get('source_data_identities',{}).get(name)!=identity or not valid_source:reason='源单位的当前对象、版本或原权限不能核定。'
            elif not _producer_unit_scope(receipt['tool_name'],delivery,metric,result):reason='该实际生产者的源单位范围尚未评估。'
            elif isinstance(column,dict) and result.get('parameters',{}).get('metric_formulas',{}).get(metric)!=params['comparison_formulas'][metric]:reason='实际原公式与正式交付的两端绑定不一致。'
            else:
                observation=context.workspace._publication_source_unit_observation(name,identity,metric,column,receipt['tool_name'],result)
                reason=observation['reason'];units=observation['units'];count=observation['valid_rows']
                public_code=observation.get('code','unit_unverified')
            proof=dict(metric=metric,column=column,source_identity=deepcopy(identity),scope=deepcopy(scope),receipt_id=rid,valid_rows=count,units=units,verified=reason is None)
            if isinstance(column,dict):proof['formula']=deepcopy(params['comparison_formulas'][metric])
            previous=proofs.get(metric)
            if previous and previous['column']!=column:
                reason='同一度量的执行前源单位字段声明冲突。';proof['verified']=False
            proofs[metric]=proof
            if reason:gaps.append(dict(receipt_id=rid,delivery_ids=[delivery['id']],metric=metric,code='source_unit_scope',reason=reason,
                public_context={'kind':'source_unit','code':public_code,'dataset':name,'metric':metric,'units':units}))
    failed={g['metric'] for g in gaps};kept=[]
    for claim in facts:
        target=claim.get('target',{});product=target.get('business_product');metrics=set(product.get('metrics',[])) if product else {target.get('metric')}
        matched=metrics & proofs.keys()
        if not matched:kept.append(claim);continue
        if receipt['tool_name']=='contribute_decomposition' and claim['basis_refs'][0]['result_path']!=['total_change']:
            kept.append(claim);continue
        if receipt['tool_name']=='distribution_analysis' and target.get('statistic') not in {'mean','std','min','25%','50%','75%','max'}:
            kept.append(claim);continue
        if receipt['tool_name']=='analyze_time_series' and claim['basis_refs'][0]['result_path']!=['statistics']:
            kept.append(claim);continue
        # Counts and diagnostics remain independent of amount units.
        if target.get('statistic') in {'missing_count','missing_pct','unique_values','top_values','rows'}:kept.append(claim);continue
        if matched & failed:continue
        multi=bool(product and product.get('kind')=='table' and len(metrics)>1)
        if not multi and len(matched)!=1:continue
        selected={metric:deepcopy(proofs[metric]) for metric in sorted(matched)}
        mappings={key:{m:p['column'] for m,p in selected.items() if ('formula' in p)==(key=='formula_unit_columns')} for key in ('source_unit_columns','formula_unit_columns')}
        for metric,proof in selected.items():
            literal=not multi and type(claim['value']) in {int,float} and claim.get('unit') not in {'percent','无量纲'}
            proof['render_as_source_label']=literal
            if literal:claim['unit']=proof['units'][0]
            claim['limitations'].append('公式 '+metric+' 按声明两端原单位标签约分为无量纲；标签含义未作外部验证，不含换汇。' if 'formula' in proof else '源单位按声明字段 '+metric+'→'+proof['column']+' 核当前有效观测；不含换汇或字段含义的外部验证。')
        if multi:target['source_unit_proofs']=selected
        else:target['source_unit_proof']=next(iter(selected.values()))
        for key,mapping in mappings.items():
            if mapping:
                target.setdefault('parameters',{})[key]=deepcopy(mapping)
                if product:product.setdefault('parameters',{})[key]=deepcopy(mapping)
        kept.append(claim)
    if gaps and kept:kept[0]['target']['source_unit_gaps']=gaps
    return kept


def _source_unit_plan(context,receipt):
    """Read the original plan through its existing registered immutable artifact."""
    from .facts import resolve_artifact
    from data_agent.agent.analysis_plan_contracts import validate_analysis_plan_contract
    from data_agent.session.history import list_artifacts
    from data_agent.config import get_config
    import json
    def validate(plan,requirements=None):
        if not isinstance(plan,dict):return None
        check=validate_analysis_plan_contract(deepcopy(plan),answer_requirements=requirements,requirement_revision=plan.get('requirement_revision'))
        return check.plan if check.ok and check.plan.get('id')==receipt.get('plan_id') and check.plan.get('plan_sha256')==receipt.get('plan_sha256') else None
    current=context.analysis_state.analysis_plan or {}
    if current.get('id')==receipt.get('plan_id') and current.get('plan_sha256')==receipt.get('plan_sha256'):
        return validate(current,context.analysis_state.answer_requirements) or {}
    own=get_config().sessions_resolved/context.session_id;prefix='sessions/'+context.session_id+'/'
    for artifact in list_artifacts(context.session_id):
        if not isinstance(artifact,dict):continue
        reference=str(artifact.get('path','')).replace('\\','/')
        if artifact.get('type')!='analysis_plan' or not reference.startswith(prefix+'analysis_flow/') or not artifact.get('sha256'):continue
        reference=reference[len(prefix):]
        try:
            resolve_artifact(session_id=context.session_id,artifact_id=artifact['id'],path=reference,kind='analysis_plan',description=artifact.get('description','Original execution plan'),expected_sha256=artifact['sha256'])
            plan=validate(json.loads((own/reference).read_bytes()))
            if plan:return plan
        except (ValueError,OSError,KeyError,TypeError):continue
    return {}


def _validate_source_unit_proof(claim,proof):
    from .contracts import fields,ContractError
    fields(proof,{'metric','column','source_identity','scope','receipt_id','valid_rows','units','verified','render_as_source_label'},{'formula'})
    units=proof['units'];formula=proof.get('formula');column=proof['column']
    formula_column=isinstance(column,dict) and set(column)=={'numerator','denominator'} and all(isinstance(v,str) and v.strip() for v in column.values())
    if (not isinstance(units,list) or len(units)!=1 or not isinstance(units[0],str) or not units[0].strip()
            or not isinstance(proof['metric'],str) or not proof['metric'].strip()
            or (not formula_column if formula is not None else not isinstance(column,str) or not column.strip())
            or not isinstance(proof['scope'],dict) or not isinstance(proof['scope'].get('parameters'),dict)):
        raise ContractError('source_unit_proof','源单位证明字段没有绑定同一明确度量。')
    params=proof['scope']['parameters']
    if formula is not None and (not isinstance(formula,dict) or set(formula)!={'operator','numerator','denominator'} or formula['operator']!='ratio_of_sums'
            or params.get('comparison_formulas',{}).get(proof['metric'])!=formula
            or claim['target'].get('parameters',{}).get('metric_formulas',{}).get(proof['metric'])!=formula or units!=['无量纲']):
        raise ContractError('source_unit_proof','公式单位证明没有绑定同一原算式。')
    matching=[p for p in claim['basis_refs'] if p['receipt_id']==proof['receipt_id']]
    if (type(proof['render_as_source_label']) is not bool or proof['render_as_source_label'] and claim['unit']!=units[0]
            or proof['verified'] is not True or type(proof['valid_rows']) is not int or proof['valid_rows']<1
            or not matching or any(p['data_identities'].get(claim['scope']['dataset'])!=proof['source_identity'] for p in matching)
            or params.get('formula_unit_columns' if formula is not None else 'source_unit_columns',{}).get(proof['metric'])!=column):
        raise ContractError('source_unit_proof','源单位证明没有绑定同一原件/实际范围。')


def validate_source_unit_target(claim):
    from .contracts import fields,ContractError
    target=claim['target'];proof=target.get('source_unit_proof');multiple=target.get('source_unit_proofs')
    if proof is not None:_validate_source_unit_proof(claim,proof)
    if multiple is not None:
        product=target.get('business_product',{})
        if (proof is not None or not isinstance(multiple,dict) or not 1<=len(multiple)<=32
                or product.get('kind')!='table' or not set(multiple).issubset(product.get('metrics',[]))):
            raise ContractError('source_unit_proof','整表源单位证明必须逐指标绑定原生表。')
        for metric,item in multiple.items():
            _validate_source_unit_proof(claim,item)
            if item['metric']!=metric or item['render_as_source_label']:
                raise ContractError('source_unit_proof','整表源单位证明不允许改绑指标或使用整表单一标签。')
    if 'source_unit_gaps' in target:
        gaps=target['source_unit_gaps']
        if not isinstance(gaps,list) or len(gaps)>128:raise ContractError('source_unit_gap','源单位缺口格式无效。')
        for gap in gaps:
            fields(gap,{'receipt_id','delivery_ids','metric','code','reason'},{'public_context'})
            if (gap['code']!='source_unit_scope' or not isinstance(gap['delivery_ids'],list) or not gap['delivery_ids']
                    or not isinstance(gap['metric'],str) or not isinstance(gap['reason'],str)
                    or gap['receipt_id'] not in {p['receipt_id'] for p in claim['basis_refs']}):
                raise ContractError('source_unit_gap','源单位缺口未绑定原执行回执。')
            if 'public_context' in gap:
                public=gap['public_context'];fields(public,{'kind','code','dataset','metric','units'})
                if (public['kind']!='source_unit' or public['code'] not in {'unit_unverified','unit_missing','unit_mixed'}
                        or public['metric']!=gap['metric'] or not isinstance(public['units'],list)
                        or len(public['units'])>32 or any(not isinstance(u,str) or not u or len(u)>128 for u in public['units'])
                        or not any(public['dataset'] in p['data_identities'] for p in claim['basis_refs'])):
                    raise ContractError('source_unit_gap','源单位公开范围没有同一原回执身份。')


def source_unit_observation(frame,metric,column,tool,result):
    """Storage-owned observation;only bounded unit labels/counts leave storage."""
    if isinstance(column,dict):
        return _formula_unit_observation(frame,metric,column,tool,result)
    reason=None;units=[];count=0;public_code='unit_unverified'
    if frame is None or not frame.columns.is_unique or metric not in frame or column not in frame:reason='源单位字段或度量字段不存在/不唯一。'
    elif tool!='analyze_time_series' and not pd.api.types.is_numeric_dtype(frame[metric]):reason='当前度量没有原生数值聚合范围。'
    else:
        try:values=frame[metric].astype(float) if tool=='analyze_time_series' else frame[metric]
        except (ValueError,TypeError,OverflowError):return dict(reason='原时序数值转换范围不能核定。',units=[],valid_rows=0)
        mask=pd.Series(np.isfinite(values.to_numpy(dtype=float,na_value=np.nan)),index=frame.index)
        if tool=='analyze_time_series':
            date_col=result.get('parameters',{}).get('date_col')
            if date_col not in frame:return dict(reason='原时序日期范围不能核定。',units=[],valid_rows=0)
            mask &= pd.to_datetime(frame[date_col],errors='coerce').notna()
        if tool in {'compare_periods','contribute_decomposition'}:
            params=result['parameters'];dates=pd.to_datetime(frame[params['date_col']],errors='coerce');windows=pd.Series(False,index=frame.index)
            for period in ('period_a','period_b'):
                lo,hi=result[period]['range'];windows|=dates.between(pd.Timestamp(lo),pd.Timestamp(hi)+pd.Timedelta(days=1),inclusive='left')
            mask &= windows
            if tool=='contribute_decomposition':
                dimension=params.get('dimension')
                if params.get('agg_func')!='sum' or params.get('metric')!=metric or dimension not in frame:return dict(reason='当前贡献原sum差额范围不能核定。',units=[],valid_rows=0)
                mask &= frame[dimension].notna()
            if metric in params.get('metric_formulas',{}):reason='分组或公式复合度量的源单位运算尚未评估，不能借简单金额合同完成。'
        values=frame.loc[mask,column].tolist();count=len(values)
        if not reason:
            if not values:reason='没有可核单位的有效度量观测。'
            elif any(not isinstance(v,str) or not v.strip() for v in values):reason='有效度量观测存在缺失或非文本源单位。';public_code='unit_missing'
            elif any(len(v)>128 for v in values):reason='源单位标签超过有界呈现长度，未截断或归并。'
            else:
                units=sorted(set(values))
                if len(units)>32:reason='源单位种类超过有界核定范围。';units=[]
                elif len(units)!=1:reason='混合源单位：'+encode(units)+'；未执行换汇，金额不可相加比较。';public_code='unit_mixed'
    observation=dict(reason=reason,units=units,valid_rows=count)
    if reason:observation['code']=public_code
    return observation


def _formula_unit_observation(frame,metric,columns,tool,result):
    """Only the current native ratio's complete equal labels may cancel."""
    formula=result.get('parameters',{}).get('metric_formulas',{}).get(metric)
    failed=dict(reason='当前原ratio_of_sums两端单位不能核定。',units=[],valid_rows=0)
    if tool!='compare_periods' or not isinstance(formula,dict) or formula.get('operator')!='ratio_of_sums' or set(columns)!={'numerator','denominator'}:return failed
    # A copy removes only the composite-output marker; original operand/window checks are shared.
    native=dict(result,parameters=dict(result['parameters'],metric_formulas={}));observations=[]
    for side in ('numerator','denominator'):
        obs=source_unit_observation(frame,formula[side],columns[side],tool,native)
        if obs['reason']:return obs
        observations.append(obs)
    if observations[0]['units']!=observations[1]['units']:
        return dict(reason='分子分母原单位标签不同，未执行单位代数或换汇。',units=[],valid_rows=min(o['valid_rows'] for o in observations))
    # Native ratio completeness/zero-denominator gates still own every numeric result.
    dates=pd.to_datetime(frame[result['parameters']['date_col']],errors='coerce');mask=pd.Series(False,index=frame.index)
    for period in ('period_a','period_b'):
        lo,hi=result[period]['range'];mask |= dates.between(pd.Timestamp(lo),pd.Timestamp(hi)+pd.Timedelta(days=1),inclusive='left')
    for side in ('numerator','denominator'):mask &= np.isfinite(frame[formula[side]].to_numpy(dtype=float,na_value=np.nan))
    count=int(mask.sum())
    return dict(reason=None if count else '没有两端均有效的原观测。',units=['无量纲'] if count else [],valid_rows=count)


def _contribution_unit_scope(delivery,metric,result):
    """125 signs only the original sum difference,never the decomposition table."""
    scope=delivery['scope'];declared=scope.get('parameters',{});actual=result.get('parameters',{})
    pairs={'dimension':'decomposition_dimension','date_col':'decomposition_date_col','agg_func':'decomposition_aggregation','period_a':'period_a','period_b':'period_b'}
    return (delivery['kind']=='measurement' and scope.get('quantity')=='difference'
        and declared.get('decomposition_output')=='total_change' and actual.get('agg_func')=='sum' and actual.get('metric')==metric
        and all(k in actual and b in declared and actual[k]==declared[b] for k,b in pairs.items()))


def _producer_unit_scope(tool,delivery,metric,result):
    """Only approved native outputs may carry the bound physical source label."""
    if tool in {'describe_dataset','compare_periods'}:return True
    if tool=='contribute_decomposition':return _contribution_unit_scope(delivery,metric,result)
    scope=delivery['scope'];declared=scope.get('parameters',{})
    if tool=='distribution_analysis':
        return delivery['kind']=='measurement' and scope.get('quantity') in {'mean','std','min','25%','50%','75%','max'} and metric in result
    if tool=='analyze_time_series':
        actual=result.get('parameters',{})
        return (delivery['kind']=='table' and declared.get('time_series_output')=='statistics' and actual.get('value_col')==metric
            and declared.get('time_series_date_col')==actual.get('date_col') and declared.get('time_series_value_col')==actual.get('value_col'))
    return False
