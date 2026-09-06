"""Conservative name hints shared by automatic profiling and type advice.

An identifier's role is independent of whether it is unique in this table.
These hints never establish a join key, analysis grain, or a currency unit.
"""
from __future__ import annotations

import re


def _tokens(name: object) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(name or ""))
    return re.findall(r"[a-z]+", text.lower())


def is_identifier_name(name: object) -> bool:
    text = str(name or "").strip()
    tokens = _tokens(text)
    return (
        bool(tokens) and tokens[-1] in {"id", "uid", "uuid", "openid", "userid", "orderid", "deviceid"}
        or text.endswith(("编号", "标识符"))
    )


def is_monetary_name(name: object) -> bool:
    if is_identifier_name(name):
        return False
    text = str(name or "")
    return (
        any(word in text for word in ("金额", "售价", "单价", "面值", "实收", "实付", "收入", "费用", "成本", "余额"))
        or bool(set(_tokens(name)) & {"price", "amount", "revenue", "income", "cost", "balance"})
    )


def is_measure_name(name: object) -> bool:
    if is_identifier_name(name):
        return False
    tokens = _tokens(name)
    return is_monetary_name(name) or str(name or "").endswith(("数", "数量", "金额", "率")) or (
        bool(tokens) and tokens[-1] in {"count", "rate", "ratio", "percent", "percentage", "sum", "mean", "average"}
    )
