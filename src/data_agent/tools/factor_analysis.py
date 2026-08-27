"""Guarded adjusted association analysis for the existing attribution tool."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.api import OLS, add_constant
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor

from data_agent.tools._utils import get_df
from data_agent.tools.method_contract import method_receipt
from data_agent.tools.registry import ToolResult


def factor_relationships(name: str, target: str, features: list[str], unit_col: str = "", time_col: str = "") -> ToolResult:
    frame, error = get_df(name)
    if error:
        return ToolResult(summary=error)
    missing = sorted({target, *features} - set(frame.columns))
    if missing:
        return ToolResult(summary=f"列不存在: {missing}")
    excluded: dict[str, str] = {}
    y = pd.to_numeric(frame[target], errors="coerce")
    usable = []
    for feature in features:
        value = pd.to_numeric(frame[feature], errors="coerce")
        if value.nunique(dropna=True) < 2:
            excluded[feature] = "constant_or_non_numeric"
            continue
        # Exact arithmetic identity is leakage, not a useful attribution.
        for other in features:
            if other == feature:
                continue
            other_value = pd.to_numeric(frame[other], errors="coerce")
            valid = y.notna() & value.notna() & other_value.notna() & (other_value != 0)
            if valid.sum() >= 3 and np.allclose(y[valid], value[valid] / other_value[valid], rtol=1e-7, atol=1e-9):
                excluded[feature] = "mathematical_identity_with_target"
                break
        if feature not in excluded:
            usable.append(feature)
    working = pd.DataFrame({target: y, **{column: pd.to_numeric(frame[column], errors="coerce") for column in usable}}).replace([np.inf, -np.inf], np.nan).dropna()
    receipt = method_receipt(name, method="adjusted_factor_relationships", status="limited", effective_n=len(working), parameters={"target": target, "features": features, "analysis_unit": unit_col, "time_col": time_col}, limitations=["结果仅为调整后的统计关联，不识别因果效应。"], claim_ceiling="associational")
    if not usable or len(working) < len(usable) + 5:
        receipt.update(reason_code="insufficient_identifiable_data", excluded_features=excluded)
        return ToolResult(summary="没有足以稳定估计的因素模型", data=receipt)
    design = working[usable].copy()
    design = (design - design.mean()) / design.std(ddof=0)
    vifs = {column: float(variance_inflation_factor(add_constant(design).values, index + 1)) for index, column in enumerate(usable)}
    unstable = [column for column, value in vifs.items() if not np.isfinite(value) or value >= 10]
    stable = [column for column in usable if column not in unstable]
    associations = []
    for column in usable:
        coefficient, pvalue = stats.pearsonr(working[column], working[target])
        associations.append({"feature": column, "pearson_r": round(float(coefficient), 8), "p_value": round(float(pvalue), 8), "n_pairs": len(working)})
    if not stable:
        receipt.update(reason_code="multicollinearity_prevents_attribution", excluded_features=excluded, unstable_features=unstable, bivariate_associations=associations)
        return ToolResult(summary="因素高度共线；保留未调整关联，不发布稳定归因", data=receipt)
    x = add_constant(design[stable], has_constant="add")
    model = OLS((working[target] - working[target].mean()) / working[target].std(ddof=0), x).fit(cov_type="HC3")
    raw = [float(model.pvalues[column]) for column in stable]
    adjusted = multipletests(raw, method="holm")[1]
    intervals = model.conf_int()
    estimates = []
    for column, pvalue, corrected in zip(stable, raw, adjusted):
        low, high = intervals.loc[column]
        estimates.append({"feature": column, "coefficient": round(float(model.params[column]), 8), "confidence_interval_95": [round(float(low), 8), round(float(high), 8)], "p_value": round(pvalue, 8), "p_value_holm": round(float(corrected), 8), "vif": round(vifs[column], 8), "reliable": bool(corrected < 0.05 and (low > 0 or high < 0))})
    reliable = [item for item in estimates if item["reliable"]]
    receipt.update(status="supported" if reliable else "limited", reason_code="adjusted_associations_found" if reliable else "no_adjusted_association", excluded_features=excluded, unstable_features=unstable, estimates=estimates, bivariate_associations=[] if reliable else associations)
    return ToolResult(summary="已完成稳健调整因素分析" if reliable else "未发现稳定调整因素；保留描述性关联", data=receipt)
