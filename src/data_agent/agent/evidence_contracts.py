from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from data_agent.agent.analysis_execution import StepBindingResult


CANONICAL_EVIDENCE_FIELDS = (
    "plan_id",
    "step_id",
    "claim_key",
    "claim",
    "dataset",
    "dataset_contract_id",
    "method",
    "tool_calls",
    "result_summary",
    "sample_size",
    "limitations",
    "confidence",
    "evidence_requirement",
    "measurements",
)

MEASUREMENT_FIELDS = (
    "metric",
    "definition",
    "value",
    "unit",
    "grain",
    "population_scope",
    "time_scope",
    "method",
    "denominator",
    "limitations",
)

NORMALIZED_EVIDENCE_TEXT_FIELDS = (
    "plan_id",
    "step_id",
    "claim_key",
    "dataset",
    "dataset_contract_id",
    "method",
    "confidence",
    "evidence_requirement",
)

NORMALIZED_MEASUREMENT_TEXT_FIELDS = (
    "metric",
    "definition",
    "unit",
    "grain",
    "population_scope",
    "time_scope",
    "method",
    "denominator",
)

EVIDENCE_RECORD_CONTRACT_VERSION = "evidence_record.v2"
COMPUTATION_REF_CONTRACT_VERSION = "computation_ref.v1"
TOOL_OUTPUT_CONTRACT_VERSION = "tool_output.v1"
MEASUREMENT_IDENTITY_CONTRACT_VERSION = "measurement_identity.v1"
MEASUREMENT_PROJECTION_ORIGIN = "structured_computation_projector.v1"

MEASUREMENT_IDENTITY_REQUIRED_FIELDS = (
    "contract_version",
    "measurement_key",
    "metric_key",
    "metric_label",
    "metric_aliases",
    "claim_key",
    "computation_ref_id",
    "plan_id",
    "plan_version",
    "step_id",
    "requirement_ids",
    "dataset_versions",
    "time_scope",
    "population_scope",
    "value",
    "unit",
    "direction",
    "allowed_claim_class",
)

_SAFE_MODEL_EVIDENCE_FIELDS = frozenset({
    *CANONICAL_EVIDENCE_FIELDS,
    "source_tool_call_ids",
    "requirement_ids",
    "statistical_support",
    "time_scope",
    "calculation_method",
    "method_detail",
    "confidence_reason",
})
_SAFE_MODEL_REQUIREMENT_FIELDS = frozenset({
    "assumptions",
    "confidence_reason",
    "limitations",
    "time_scope",
})
_SUPPORT_BY_REQUIREMENT = {
    "autocorrelation_awareness": "autocorrelation_awareness",
    "denominator": "denominator",
    "effective_sample_size": "effective_sample_size",
    "estimand": "estimand",
    "missing_intervals": "missing_intervals",
    "missingness": "missingness",
    "multiplicity_handling": "multiplicity_handling",
    "period_comparability": "period_comparability",
    "period_definition": "period_definition",
    "periods": "periods",
    "sample_adequacy": "sample_adequacy",
    "seasonality_estimability": "seasonality_estimability",
    "sample_size": "effective_sample_size",
    "effect": "effect_estimate",
    "effect_estimate": "effect_estimate",
    "effect_size": "effect_estimate",
    "metric_delta": "effect_estimate",
    "confidence_interval": "confidence_interval",
    "significance": "test",
    "correlation": "correlation",
    "assumptions": "assumptions",
    "time_frequency": "time_frequency",
    "trend": "trend",
    "trend_statistics": "trend_statistics",
    "window_comparability": "window_comparability",
}
_GENERIC_AUTHORITATIVE_SUPPORT_FIELDS = frozenset({
    "autocorrelation_awareness",
    "denominator",
    "estimand",
    "missing_intervals",
    "missingness",
    "multiplicity_handling",
    "period_comparability",
    "period_definition",
    "periods",
    "sample_adequacy",
    "seasonality_estimability",
    "time_frequency",
    "trend",
    "trend_statistics",
    "window_comparability",
})
_MATERIAL_NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<sign>[+-]?)(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*(?P<unit>%|percent|pct|CNY|RMB|USD|EUR|GBP|JPY|HKD|¥|\$|元|"
    r"observations?|rows?|records?|counts?|items?|users?)?",
    re.IGNORECASE,
)
_DATE_NUMBER_RE = re.compile(
    r"\b(?:19|20)\d{2}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b"
)
_CAUSAL_CLAIM_RE = re.compile(
    r"\b(?:caus(?:e|ed|es|al|ally)|led\s+to|due\s+to|attributable\s+to)\b|"
    r"导致|造成|归因于|使.{0,20}(?:增加|下降|提高|降低)",
    re.IGNORECASE,
)
_PREDICTION_CLAIM_RE = re.compile(
    r"\b(?:forecast(?:s|ed|ing)?|predict(?:s|ed|ing|ion|ive)?)\b|"
    r"预测|预报|预估|预计",
    re.IGNORECASE,
)
_CORRELATION_CLAIM_RE = re.compile(
    r"\b(?:correlat(?:e|ed|es|ion|ional)|associat(?:e|ed|es|ion))\b|"
    r"相关|关联",
    re.IGNORECASE,
)
_NAMED_METHOD_CLAIM_RULES = (
    ("mannwhitneyu", re.compile(
        r"\bmann[\s-]*whitney(?:\s+u)?\b|曼恩?[\s-]*惠特尼(?:\s*U)?|秩和(?:检验|测试)",
        re.IGNORECASE,
    )),
    ("welch", re.compile(
        r"\bwelch(?:'s)?(?:\s+t(?:[\s-]*test)?)?\b|韦尔奇(?:\s*t)?(?:检验|测试)?",
        re.IGNORECASE,
    )),
    ("ttest", re.compile(r"\bt[\s-]*test\b|\bt\s*(?:检验|测试)", re.IGNORECASE)),
    ("chi2", re.compile(
        r"\bchi[\s-]*(?:square|squared|2)\b|卡方(?:检验|测试)?",
        re.IGNORECASE,
    )),
    ("pearson", re.compile(r"\bpearson(?:'s)?\b|皮尔逊", re.IGNORECASE)),
    ("spearman", re.compile(r"\bspearman(?:'s)?\b|斯皮尔曼", re.IGNORECASE)),
    ("kendall", re.compile(r"\bkendall(?:'s)?\b|肯德尔", re.IGNORECASE)),
    ("regression", re.compile(r"\bregression\b|回归", re.IGNORECASE)),
)
_TEST_WORD_RE = re.compile(r"\btest\b|检验|测试", re.IGNORECASE)
_MODEL_ASSERTION_RE = re.compile(r"\bmodel\b(?!-)|模型", re.IGNORECASE)
_ENGLISH_TEST_MODIFIER_RE = re.compile(
    r"\b(?P<modifier>[A-Za-z][A-Za-z0-9'-]*)[\s-]+test\b",
    re.IGNORECASE,
)
_CHINESE_TEST_MODIFIER_RE = re.compile(r"(?P<modifier>[\u4e00-\u9fff]{1,8})(?:检验|测试)")
_ENGLISH_MODEL_MODIFIER_RE = re.compile(
    r"\b(?P<modifier>[A-Za-z][A-Za-z0-9'-]*)\s+model\b",
    re.IGNORECASE,
)
_CHINESE_MODEL_MODIFIER_RE = re.compile(r"(?P<modifier>[\u4e00-\u9fff]{1,8})模型")
_METHOD_QUALIFIER_RE = re.compile(
    r"\b(?P<modifier>(?:two\s+)?independent\s+samples?|paired\s+samples?|"
    r"equal[\s-]+variance|unequal[\s-]+variance|"
    r"[A-Za-z][A-Za-z0-9'’-]*)\s+"
    r"(?P<method>t[\s-]*test|mann[\s-]*whitney(?:\s+u)?(?:\s+test)?|"
    r"chi[\s-]*(?:square|squared|2)(?:\s+test)?)\b",
    re.IGNORECASE,
)
_CHINESE_METHOD_QUALIFIER_RE = re.compile(
    r"(?P<modifier>[\u4e00-\u9fff]{1,12})\s*"
    r"(?P<method>t\s*(?:检验|测试))",
    re.IGNORECASE,
)
_MIXED_TTEST_QUALIFIER_RE = re.compile(
    r"\b(?P<modifier>(?:two\s+)?independent\s+samples?|paired\s+samples?|"
    r"equal[\s-]+variance|unequal[\s-]+variance|"
    r"[A-Za-z][A-Za-z0-9'’-]*)\s+"
    r"(?P<method>t\s*(?:检验|测试))",
    re.IGNORECASE,
)
_GENERIC_TEST_MODIFIERS = frozenset({
    "a", "an", "the", "this", "that", "statistical", "hypothesis",
    "significance", "inferential", "two-sided", "one-sided",
})
_GENERIC_MODEL_MODIFIERS = frozenset({
    "a", "an", "the", "this", "that", "forecast", "forecasting",
    "prediction", "predictive", "classification", "regression",
})
_TEST_METHOD_CUE_RE = re.compile(
    r"^\s*(?::|=|found\b|showed\b|indicated\b|reported\b|returned\b|"
    r"yielded\b|result(?:s)?\b|statistic\b|p[\s-]*value\b|was\s+(?:run|performed)\b)",
    re.IGNORECASE,
)
_TEST_CONTEXT_CUE_RE = re.compile(
    r"(?:\busing\b|\bperformed\b|\bran\b|\bconducted\b|\bstatistical\b|"
    r"\bhypothesis\b)\s*$",
    re.IGNORECASE,
)
_NON_METHOD_TEST_NOUN_RE = re.compile(
    r"^\s+(?:dataset|data|fixture|sample|case|file|suite)\b",
    re.IGNORECASE,
)
_ENGLISH_NEGATION_RE = re.compile(
    r"(?:\bno\b|\bnot\b|\bwithout\b|\bnever\b|\bneither\b)"
    r"(?:\s+[A-Za-z][A-Za-z0-9'’-]*){0,3}\s*$",
    re.IGNORECASE,
)
_CHINESE_NEGATION_RE = re.compile(r"(?:未|没有|并未|不是|并非|不|无)[^，,；;。.!?！？]{0,8}$")
_METHOD_QUALIFIER_ALIASES = {
    "paired": "paired",
    "student": "student",
    "unpaired": "independent",
    "independent": "independent",
    "independent sample": "independent",
    "independent samples": "independent",
    "two independent sample": "independent",
    "two independent samples": "independent",
    "independent-sample": "independent",
    "independent-samples": "independent",
    "two-sample": "independent",
    "two-samples": "independent",
    "welch": "welch",
    "equal variance": "student",
    "equal-variance": "student",
    "unequal variance": "welch",
    "unequal-variance": "welch",
    "配对": "paired",
    "配对样本": "paired",
    "成对": "paired",
    "成对样本": "paired",
    "独立": "independent",
    "独立样本": "independent",
    "两独立样本": "independent",
    "两个独立样本": "independent",
    "等方差": "student",
    "方差齐": "student",
    "异方差": "welch",
    "不等方差": "welch",
    "方差不齐": "welch",
    "非配对": "independent",
    "非成对": "independent",
}
_CHINESE_NEGATION_EXEMPT_SUFFIXES = (
    "不等方差", "方差不齐", "非配对", "非成对", "非参数",
)


def _is_negated_claim_span(text: str, start: int) -> bool:
    clause_start = max(text.rfind(mark, 0, start) for mark in ";；。.!?！？,，\n") + 1
    prefix = text[clause_start:start]
    stripped_prefix = prefix.rstrip()
    for suffix in _CHINESE_NEGATION_EXEMPT_SUFFIXES:
        if stripped_prefix.endswith(suffix):
            before_term = stripped_prefix[:-len(suffix)]
            return bool(
                _ENGLISH_NEGATION_RE.search(before_term)
                or _CHINESE_NEGATION_RE.search(before_term)
            )
    return bool(_ENGLISH_NEGATION_RE.search(prefix) or _CHINESE_NEGATION_RE.search(prefix))


def _positive_matches(pattern: re.Pattern[str], text: str) -> list[re.Match[str]]:
    return [match for match in pattern.finditer(text) if not _is_negated_claim_span(text, match.start())]


def _explicit_test_spans(
    claim_text: str,
    named_method_spans: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    spans = list(named_method_spans)
    english_modifiers = list(_ENGLISH_TEST_MODIFIER_RE.finditer(claim_text))
    chinese_modifiers = list(_CHINESE_TEST_MODIFIER_RE.finditer(claim_text))
    for match in _positive_matches(_TEST_WORD_RE, claim_text):
        suffix = claim_text[match.end():match.end() + 40]
        if _NON_METHOD_TEST_NOUN_RE.match(suffix) or suffix.startswith(("数据", "数据集", "样本", "用例")):
            continue
        modifier_match = next(
            (item for item in english_modifiers if item.end() == match.end()),
            None,
        )
        chinese_match = next(
            (item for item in chinese_modifiers if item.end() == match.end()),
            None,
        )
        prefix = claim_text[max(0, match.start() - 40):match.start()]
        modifier_is_method_like = bool(
            modifier_match
            and modifier_match.group("modifier").casefold() not in _GENERIC_TEST_MODIFIERS
        ) or bool(
            chinese_match
            and not chinese_match.group("modifier").endswith(("该", "此"))
        )
        chinese_cue = bool(
            re.match(r"^\s*(?:结果|显示|表明|发现|得到|为|：|:)", suffix)
            or re.search(r"(?:采用|进行|执行|通过)\s*$", prefix)
        )
        if (
            modifier_is_method_like
            or _TEST_METHOD_CUE_RE.match(suffix)
            or _TEST_CONTEXT_CUE_RE.search(prefix)
            or chinese_cue
        ):
            spans.append(match.span())
    return spans


def _unsupported_claim_semantics(
    claim_text: str,
    *,
    capability_ids: set[str],
    tool_names: set[str],
    method_tokens: set[str],
) -> str:
    trusted_identities = " ".join(sorted(capability_ids | tool_names)).casefold()
    prediction_supported = any(
        token in trusted_identities
        for token in ("forecast", "prediction", "classification", "regression")
    )
    if _positive_matches(_CAUSAL_CLAIM_RE, claim_text) and "causal" not in trusted_identities:
        return "causal"
    if _positive_matches(_PREDICTION_CLAIM_RE, claim_text) and not prediction_supported:
        return "prediction"
    if _positive_matches(_CORRELATION_CLAIM_RE, claim_text) and "correlation" not in trusted_identities:
        return "correlation"
    method_spans: list[tuple[int, int]] = []
    for method_name, pattern in _NAMED_METHOD_CLAIM_RULES:
        matches = _positive_matches(pattern, claim_text)
        method_spans.extend(match.span() for match in matches)
        if matches and method_name not in method_tokens:
            return method_name

    def overlaps_named_method(span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in method_spans)

    qualifier_matches = (
        _positive_matches(_METHOD_QUALIFIER_RE, claim_text)
        + _positive_matches(_CHINESE_METHOD_QUALIFIER_RE, claim_text)
        + _positive_matches(_MIXED_TTEST_QUALIFIER_RE, claim_text)
    )
    for match in qualifier_matches:
        if not overlaps_named_method(match.span("method")):
            continue
        modifier = " ".join(
            match.group("modifier").casefold().replace("’", "'").split()
        )
        if modifier.endswith("'s"):
            modifier = modifier[:-2]
        if modifier in _GENERIC_TEST_MODIFIERS:
            continue
        canonical_modifier = _METHOD_QUALIFIER_ALIASES.get(modifier)
        if canonical_modifier is None and re.search(r"[\u4e00-\u9fff]", modifier):
            modifier_without_particle = modifier.removesuffix("的")
            chinese_aliases = (
                (alias, canonical)
                for alias, canonical in _METHOD_QUALIFIER_ALIASES.items()
                if re.search(r"[\u4e00-\u9fff]", alias)
            )
            canonical_modifier = next((
                canonical
                for alias, canonical in sorted(
                    chinese_aliases,
                    key=lambda item: len(item[0]),
                    reverse=True,
                )
                if modifier_without_particle.endswith(alias)
            ), None)
        if canonical_modifier is None:
            return f"unknown_method_qualifier:{modifier}"
        if canonical_modifier not in method_tokens:
            return f"unsupported_method_qualifier:{canonical_modifier}"

    test_spans = _explicit_test_spans(claim_text, method_spans)
    if test_spans:
        for match in _ENGLISH_TEST_MODIFIER_RE.finditer(claim_text):
            if not any(
                match.start() < end and start < match.end()
                for start, end in test_spans
            ):
                continue
            if overlaps_named_method(match.span()):
                continue
            modifier = match.group("modifier").casefold()
            if modifier == "ab" and "ab_test" in trusted_identities:
                continue
            if modifier not in _GENERIC_TEST_MODIFIERS:
                return f"unknown_test_method:{modifier}"
        for match in _CHINESE_TEST_MODIFIER_RE.finditer(claim_text):
            if not any(
                match.start() < end and start < match.end()
                for start, end in test_spans
            ):
                continue
            if overlaps_named_method(match.span()):
                continue
            modifier = match.group("modifier")
            if not modifier.endswith(("统计", "假设", "显著性", "该", "此")):
                return f"unknown_test_method:{modifier}"
        if not method_tokens:
            return "unbound_test_method"

    model_matches = _positive_matches(_MODEL_ASSERTION_RE, claim_text)
    if model_matches:
        if not prediction_supported:
            return "model"
        for match in _ENGLISH_MODEL_MODIFIER_RE.finditer(claim_text):
            if _is_negated_claim_span(claim_text, match.start()):
                continue
            modifier = match.group("modifier").casefold()
            if modifier not in _GENERIC_MODEL_MODIFIERS and modifier not in method_tokens:
                return f"unknown_model_method:{modifier}"
        for match in _CHINESE_MODEL_MODIFIER_RE.finditer(claim_text):
            if _is_negated_claim_span(claim_text, match.start()):
                continue
            modifier = match.group("modifier")
            if not modifier.endswith(("预测", "预报", "分类", "回归", "该", "此")):
                return f"unknown_model_method:{modifier}"
    return ""


@dataclass
class EvidenceValidationResult:
    ok: bool
    record: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _slug(value: Any) -> str:
    text = _text(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def evidence_id_for(plan_id: Any, step_id: Any, claim_key: Any) -> str:
    return f"ev_{_slug(plan_id)}_{_slug(step_id)}_{_slug(claim_key)}"


def evidence_v2_id_for(
    plan_id: Any,
    step_id: Any,
    claim_key: Any,
    *,
    requirement_ids: Any = None,
    computation_refs: Any = None,
) -> str:
    ref_identities = []
    for ref in computation_refs if isinstance(computation_refs, list) else []:
        if not isinstance(ref, dict):
            continue
        ref_identities.append([
            str(ref.get("turn_id") or ""),
            str(ref.get("tool_call_id") or ""),
            str(ref.get("output_digest") or ""),
        ])
    payload = [
        "" if plan_id is None else str(plan_id),
        "" if step_id is None else str(step_id),
        "" if claim_key is None else str(claim_key),
        sorted({str(item) for item in requirement_ids or [] if str(item)}),
        sorted(ref_identities),
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "evidence_" + hashlib.sha256(encoded).hexdigest()


def _error(error_type: str, message: str, **details: Any) -> EvidenceValidationResult:
    return EvidenceValidationResult(False, error_type=error_type, message=message, details=details)


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_value(item) for item in value), key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _canonical_identity_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _json_value(value[key])
        for key in sorted(value)
        if key != "measurement_key"
    }


def measurement_key_for(identity: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_identity_payload(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "m_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def computation_ref_key(ref: Mapping[str, Any]) -> str:
    dataset_versions = ref.get("dataset_versions")
    if (
        isinstance(dataset_versions, list)
        and all(isinstance(item, str) for item in dataset_versions)
    ):
        dataset_versions = sorted(dataset_versions)
    payload = {
        key: (
            dataset_versions
            if key == "dataset_versions"
            else ref.get(key)
        )
        for key in (
            "session_id",
            "turn_id",
            "tool_call_id",
            "tool_name",
            "output_digest",
            "plan_digest",
            "step_digest",
            "dataset_versions",
        )
    }
    encoded = json.dumps(
        _json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "cr_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def validate_measurement_identity(identity: Any) -> EvidenceValidationResult:
    if not isinstance(identity, dict):
        return _error(
            "invalid_measurement_identity",
            "Measurement identity must be an object.",
        )
    missing = [
        field
        for field in MEASUREMENT_IDENTITY_REQUIRED_FIELDS
        if field not in identity
    ]
    if missing:
        return _error(
            "missing_measurement_identity_fields",
            "Measurement identity is incomplete.",
            missing=missing,
        )
    if identity.get("contract_version") != MEASUREMENT_IDENTITY_CONTRACT_VERSION:
        return _error(
            "invalid_measurement_identity_version",
            "Measurement identity contract version is invalid.",
        )
    aliases = identity.get("metric_aliases")
    if not isinstance(aliases, list) or any(
        not isinstance(item, str) or not item.strip() for item in aliases
    ):
        return _error(
            "invalid_metric_aliases",
            "Metric aliases must be a list of non-empty trusted labels.",
        )
    for field in (
        "metric_key",
        "metric_label",
        "claim_key",
        "computation_ref_id",
        "plan_id",
        "plan_version",
        "step_id",
        "time_scope",
        "population_scope",
        "allowed_claim_class",
    ):
        if not isinstance(identity.get(field), str) or not identity[field].strip():
            return _error(
                "invalid_measurement_identity_field",
                f"Measurement identity {field} must be a non-empty string.",
                field=field,
            )
    for field in ("requirement_ids", "dataset_versions"):
        values = identity.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or values != sorted(set(values))
        ):
            return _error(
                "invalid_measurement_identity_field",
                f"Measurement identity {field} must be sorted unique strings.",
                field=field,
            )
    value = identity.get("value")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return _error(
            "invalid_measurement_identity_field",
            "Measurement identity value must be a finite number.",
            field="value",
        )
    for field in ("unit", "direction"):
        if not isinstance(identity.get(field), str):
            return _error(
                "invalid_measurement_identity_field",
                f"Measurement identity {field} must be a string.",
                field=field,
            )
    expected = measurement_key_for(identity)
    if identity.get("measurement_key") != expected:
        return _error(
            "measurement_key_mismatch",
            "Measurement key does not match its canonical identity.",
            expected=expected,
        )
    return EvidenceValidationResult(True, record=dict(identity))


def computation_digest(value: Any) -> str:
    encoded = json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


_RUNTIME_SEMANTIC_KEYS = frozenset({
    "created_at",
    "updated_at",
    "status",
    "evidence_ids",
    "satisfied_evidence_requirements",
    "satisfied_claim_keys",
    "satisfied_analysis_requirement_ids",
    "completed_at",
    "completed_by",
})


def _semantic_projection(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _semantic_projection(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _RUNTIME_SEMANTIC_KEYS
        }
    if isinstance(value, list):
        return [_semantic_projection(item) for item in value]
    return _json_value(value)


def analysis_plan_semantic_digest(plan: Any) -> str:
    """Hash plan meaning while excluding mutable execution/satisfaction state."""
    return computation_digest(_semantic_projection(plan if isinstance(plan, dict) else {}))


def analysis_step_semantic_digest(step: Any) -> str:
    """Hash step meaning while excluding mutable execution/satisfaction state."""
    return computation_digest(_semantic_projection(step if isinstance(step, dict) else {}))


def persist_computation_output(
    *,
    sessions_root: Path,
    session_id: str,
    turn_id: str,
    plan_id: str,
    step_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    output: dict[str, Any],
    dataset_versions: list[str],
    success: bool,
    plan_digest: str = "",
    step_digest: str = "",
    capability_id: str = "",
    evidence_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Persist the full result and return a compact, server-owned reference."""
    from data_agent.tools._utils import sanitize_filename

    session_text = str(session_id or "").strip()
    if not session_text:
        raise ValueError("session_id is required for computation provenance")
    root = Path(sessions_root).resolve()
    output_dir = (root / session_text / "tool_outputs").resolve()
    if not output_dir.is_relative_to(root):
        raise ValueError("session_id resolves outside the sessions root")
    call_text = str(tool_call_id or "tool_call")
    safe_call_id = sanitize_filename(call_text)
    artifact_identity = json.dumps(
        [str(turn_id or ""), call_text],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    call_suffix = hashlib.sha256(artifact_identity.encode("utf-8")).hexdigest()[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{safe_call_id}_{call_suffix}_computation.json"
    envelope = {
        "contract_version": TOOL_OUTPUT_CONTRACT_VERSION,
        "session_id": str(session_id),
        "turn_id": str(turn_id),
        "plan_id": str(plan_id),
        "plan_digest": str(plan_digest or ""),
        "step_id": str(step_id),
        "step_digest": str(step_digest or ""),
        "tool_call_id": str(tool_call_id),
        "tool_name": str(tool_name),
        "capability_id": str(capability_id or ""),
        "evidence_fields": [str(item) for item in (evidence_fields or []) if str(item)],
        "arguments": _json_value(arguments),
        "dataset_versions": sorted({str(item) for item in dataset_versions if str(item)}),
        "success": bool(success),
        "output": _json_value(output),
    }
    if isinstance(envelope["output"], dict) and not isinstance(envelope["output"].get("data"), dict):
        summary = envelope["output"].get("summary")
        if isinstance(summary, str):
            try:
                parsed_summary = json.loads(summary)
            except json.JSONDecodeError:
                parsed_summary = None
            if isinstance(parsed_summary, dict):
                envelope["output"]["data"] = parsed_summary
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    output_data = envelope["output"].get("data") if isinstance(envelope["output"], dict) else None
    structured_checked_fields = sorted(
        field_name
        for field_name in envelope["evidence_fields"]
        if (
            isinstance(output_data, dict)
            and field_name in output_data
            and not _missing(output_data.get(field_name))
            and _structured_field_valid(field_name, output_data.get(field_name))
        )
    )
    return {
        "contract_version": COMPUTATION_REF_CONTRACT_VERSION,
        "session_id": session_text,
        "tool_call_id": str(tool_call_id),
        "tool_name": str(tool_name),
        "capability_id": str(capability_id or ""),
        "arguments_digest": computation_digest(envelope["arguments"]),
        "output_digest": computation_digest(envelope["output"]),
        "artifact_path": str(path),
        "dataset_versions": list(envelope["dataset_versions"]),
        "turn_id": str(turn_id),
        "plan_id": str(plan_id),
        "plan_digest": str(plan_digest or ""),
        "step_id": str(step_id),
        "step_digest": str(step_digest or ""),
        "success": bool(success),
        "structured_checked_fields": structured_checked_fields,
        "verification_level": "structured_checked" if structured_checked_fields else "traceable",
    }


def _resolve_artifact_path(
    path_value: Any,
    sessions_root: Path,
    *,
    session_id: str,
) -> Path | None:
    value = str(path_value or "").strip()
    if not value:
        return None
    root = Path(sessions_root).resolve()
    session_root = (root / str(session_id or "")).resolve()
    output_root = (session_root / "tool_outputs").resolve()
    if not session_id or not session_root.is_relative_to(root) or not output_root.is_relative_to(session_root):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = root.parent / path
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(output_root):
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in {float("inf"), float("-inf")}


def _normalize_unit(value: Any) -> str:
    unit = _text(value).casefold()
    aliases = {
        "%": "percent",
        "pct": "percent",
        "rmb": "cny",
        "¥": "cny",
        "元": "cny",
        "$": "usd",
        "observation": "observations",
        "row": "observations",
        "rows": "observations",
        "record": "observations",
        "records": "observations",
        "count": "observations",
        "counts": "observations",
    }
    return aliases.get(unit, unit)


def _text_number_tokens(
    value: Any,
    *,
    material_only: bool,
) -> list[tuple[float, bool, bool, str]]:
    if not isinstance(value, str):
        return []
    text = _DATE_NUMBER_RE.sub(" ", value)
    tokens: list[tuple[float, bool, bool, str]] = []
    for match in _MATERIAL_NUMBER_RE.finditer(text):
        raw_number = match.group("number")
        unit = _normalize_unit(match.group("unit"))
        number = float(f"{match.group('sign')}{raw_number}")
        is_percent = unit == "percent"
        explicit_sign = bool(match.group("sign"))
        tokens.append((number, is_percent, explicit_sign, unit))
    return tokens


def _numeric_values(value: Any) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)) and _finite_number(value):
        return [float(value)]
    if isinstance(value, str):
        return [item[0] for item in _text_number_tokens(value, material_only=False)]
    if isinstance(value, dict):
        numbers: list[float] = []
        for item in value.values():
            numbers.extend(_numeric_values(item))
        return numbers
    if isinstance(value, (list, tuple, set)):
        numbers = []
        for item in value:
            numbers.extend(_numeric_values(item))
        return numbers
    return []


def _units_compatible(unit: str, allowed_units: frozenset[str]) -> bool:
    if not unit:
        return True
    if unit in allowed_units:
        return True
    return unit == "percent" and "ratio" in allowed_units


def _token_binding_match(
    number: float,
    bindings: list[tuple[float, frozenset[str]]],
    *,
    is_percent: bool = False,
    explicit_sign: bool = True,
    unit: str = "",
) -> tuple[bool, bool]:
    candidates = [number]
    if is_percent:
        candidates.append(number / 100.0)
    number_matched = False
    for candidate in candidates:
        for authoritative, allowed_units in bindings:
            direct_match = math.isclose(
                candidate, authoritative, rel_tol=1e-9, abs_tol=1e-9
            )
            magnitude_match = not explicit_sign and math.isclose(
                abs(candidate), abs(authoritative), rel_tol=1e-9, abs_tol=1e-9
            )
            if not direct_match and not magnitude_match:
                continue
            number_matched = True
            if _units_compatible(unit, allowed_units):
                return True, True
    return False, number_matched


def _effect_unit(authoritative_support: dict[str, Any]) -> str:
    effect = authoritative_support.get("effect_estimate")
    if isinstance(effect, dict):
        unit = _normalize_unit(effect.get("unit"))
        if unit:
            return unit
    return "unspecified"


def _support_bindings_for_requirement(
    requirement_name: str,
    authoritative_support: dict[str, Any],
) -> list[tuple[float, frozenset[str]]]:
    name = _text(requirement_name)
    if name == "sample_size":
        sample = authoritative_support.get("effective_sample_size")
        total = sample.get("total") if isinstance(sample, dict) else None
        return (
            [(float(total), frozenset({"observations"}))]
            if _finite_number(total)
            else []
        )
    if name in {"effect", "effect_estimate", "effect_size", "metric_delta"}:
        effect = authoritative_support.get("effect_estimate")
        value = effect.get("value") if isinstance(effect, dict) else None
        unit = _effect_unit(authoritative_support)
        allowed = {unit}
        if unit == "ratio":
            allowed.add("percent")
        if unit == "unspecified":
            allowed.update({"", "unitless", "value"})
        return [(float(value), frozenset(allowed))] if _finite_number(value) else []
    if name == "confidence_interval":
        interval = authoritative_support.get("confidence_interval")
        if not isinstance(interval, dict):
            return []
        bound_unit = _normalize_unit(interval.get("unit")) or _effect_unit(authoritative_support)
        if bound_unit == "unspecified":
            bound_units = frozenset({"", "unspecified", "unitless", "value"})
        else:
            bound_units = frozenset({bound_unit})
        bindings = []
        if _finite_number(interval.get("level")):
            bindings.append((float(interval["level"]), frozenset({"ratio", "percent"})))
        for field_name in ("lower", "upper"):
            if _finite_number(interval.get(field_name)):
                bindings.append((float(interval[field_name]), bound_units))
        return bindings
    if name == "significance":
        test = authoritative_support.get("test")
        p_value = test.get("p_value") if isinstance(test, dict) else None
        return (
            [(float(p_value), frozenset({"ratio", "percent", "p_value"}))]
            if _finite_number(p_value)
            else []
        )
    if name == "correlation":
        values = authoritative_support.get("correlation")
        items = values if isinstance(values, list) else [values]
        return [
            (float(item["correlation"]), frozenset({"ratio", "coefficient", "unitless"}))
            for item in items
            if isinstance(item, dict) and _finite_number(item.get("correlation"))
        ]
    return []


def _text_bindings(value: Any) -> list[tuple[float, frozenset[str]]]:
    bindings = []
    for number, is_percent, _explicit_sign, unit in _text_number_tokens(
        value,
        material_only=False,
    ):
        canonical = number / 100.0 if is_percent else number
        allowed = frozenset({"ratio", "percent"}) if is_percent else frozenset({unit})
        bindings.append((canonical, allowed))
    return bindings


def _display_unit(unit: str) -> str:
    return unit.upper() if unit in {"cny", "usd", "eur", "gbp", "jpy", "hkd"} else unit


def _projected_measurement_unit(
    value: Any,
    requirement_name: str,
    authoritative_support: dict[str, Any],
) -> str:
    if not _finite_number(value):
        return "unspecified"
    number = float(value)
    for authoritative, allowed_units in _support_bindings_for_requirement(
        requirement_name,
        authoritative_support,
    ):
        if not math.isclose(number, authoritative, rel_tol=1e-9, abs_tol=1e-9):
            continue
        preferred = next((
            item
            for item in (
                "cny", "usd", "eur", "gbp", "jpy", "hkd", "currency",
                "observations", "ratio", "coefficient", "p_value", "unspecified",
            )
            if item in allowed_units
        ), "unitless")
        return _display_unit(preferred)
    return "unspecified"


def _material_numeric_mismatch(
    record: dict[str, Any],
    *,
    authoritative_support: dict[str, Any],
    authoritative_summary_bindings: list[tuple[float, frozenset[str]]],
    evidence_requirement: str,
) -> EvidenceValidationResult | None:
    support_bindings = _support_bindings_for_requirement(
        evidence_requirement,
        authoritative_support,
    )
    for field_name, comparison_bindings in (
        ("claim", support_bindings),
        ("result_summary", authoritative_summary_bindings + support_bindings),
    ):
        for number, is_percent, explicit_sign, unit in _text_number_tokens(
            record.get(field_name),
            material_only=True,
        ):
            matched, number_matched = _token_binding_match(
                number,
                comparison_bindings,
                is_percent=is_percent,
                explicit_sign=explicit_sign,
                unit=unit,
            )
            if not matched:
                error_type = "evidence_unit_mismatch" if number_matched and unit else "numeric_evidence_mismatch"
                return _error(
                    error_type,
                    "EvidenceRecord material value does not match its authoritative requirement field and unit.",
                    field=field_name,
                    value=number,
                    unit=unit,
                )

    measurements = record.get("measurements")
    if isinstance(measurements, list):
        for index, measurement in enumerate(measurements):
            if not isinstance(measurement, dict):
                continue
            value = measurement.get("value")
            measurement_unit = _normalize_unit(measurement.get("unit"))
            tokens: list[tuple[float, bool, bool, str]] = []
            if _finite_number(value):
                tokens = [(float(value), False, True, measurement_unit)]
            elif isinstance(value, str):
                full_match = _MATERIAL_NUMBER_RE.fullmatch(value.strip())
                if full_match:
                    tokens = _text_number_tokens(value, material_only=False)
            for number, is_percent, explicit_sign, token_unit in tokens:
                unit = token_unit or measurement_unit
                matched, number_matched = _token_binding_match(
                    number,
                    support_bindings,
                    is_percent=is_percent,
                    explicit_sign=explicit_sign,
                    unit=unit,
                )
                if not matched:
                    error_type = "evidence_unit_mismatch" if number_matched and unit else "numeric_evidence_mismatch"
                    return _error(
                        error_type,
                        "EvidenceRecord measurement does not match its authoritative requirement field and unit.",
                        field=f"measurements[{index}].value",
                        value=number,
                        unit=unit,
                    )
    return None


def _structured_field_valid(field_name: str, value: Any) -> bool:
    if field_name == "effective_sample_size":
        if not isinstance(value, dict) or not _finite_number(value.get("total")):
            return False
        if float(value["total"]) <= 0:
            return False
        groups = value.get("groups")
        return groups is None or (
            isinstance(groups, dict)
            and bool(groups)
            and all(_finite_number(item) and float(item) > 0 for item in groups.values())
        )
    if field_name in {"effect_estimate", "effect_size"}:
        return (
            isinstance(value, dict)
            and _finite_number(value.get("value"))
            and bool(_text(value.get("metric")))
        )
    if field_name == "confidence_interval":
        if not isinstance(value, dict) or not all(
            _finite_number(value.get(item)) for item in ("level", "lower", "upper")
        ):
            return False
        return 0 < float(value["level"]) < 1 and float(value["lower"]) <= float(value["upper"])
    if field_name in {"test", "significance"} and isinstance(value, dict) and "p_value" in value:
        return _finite_number(value["p_value"]) and 0 <= float(value["p_value"]) <= 1
    if field_name == "p_value":
        return _finite_number(value) and 0 <= float(value) <= 1
    if field_name == "correlation":
        values = value if isinstance(value, list) else [value]
        return bool(values) and all(
            isinstance(item, dict)
            and _finite_number(item.get("correlation"))
            and -1 <= float(item["correlation"]) <= 1
            for item in values
        )
    if field_name == "assumptions":
        return isinstance(value, list) and bool(value) and all(
            isinstance(item, dict)
            and bool(_text(item.get("name")))
            and _text(item.get("status")) in {"assumed", "disclosed", "passed", "failed"}
            and bool(_text(item.get("reason")))
            for item in value
        )
    if field_name == "time_frequency":
        return _text(value) in {
            "daily", "business_daily", "weekly", "monthly", "quarterly", "yearly",
            "irregular", "not_estimable",
        }
    if field_name == "missing_intervals":
        return (
            isinstance(value, dict)
            and _finite_number(value.get("count"))
            and float(value["count"]) >= 0
            and bool(_text(value.get("frequency")))
        )
    if field_name == "missingness":
        return isinstance(value, dict) and bool(value) and all(
            isinstance(item, dict)
            and _finite_number(item.get("missing_count"))
            and float(item["missing_count"]) >= 0
            and _finite_number(item.get("missing_rate"))
            and 0 <= float(item["missing_rate"]) <= 1
            for item in value.values()
        )
    if field_name == "denominator":
        return isinstance(value, dict) and bool(value) and all(
            _finite_number(item) and float(item) >= 0
            for item in value.values()
        )
    if field_name == "estimand":
        return (
            isinstance(value, dict)
            and bool(_text(value.get("metric")))
            and bool(_text(value.get("aggregation")))
            and bool(_text(value.get("contrast")))
        )
    if field_name in {"period_definition", "periods"}:
        return isinstance(value, dict) and all(
            isinstance(value.get(name), list)
            and len(value[name]) == 2
            and all(bool(_text(item)) for item in value[name])
            for name in ("period_a", "period_b")
        )
    if field_name in {"period_comparability", "window_comparability"}:
        return (
            isinstance(value, dict)
            and _text(value.get("status")) in {
                "comparable", "comparable_with_adjustment", "not_comparable",
            }
            and isinstance(value.get("warnings", []), list)
        )
    if field_name == "sample_adequacy":
        return (
            isinstance(value, dict)
            and _text(value.get("status")) in {
                "adequate", "adequate_with_limits", "inadequate",
                "insufficient", "not_estimable",
            }
            and bool(_text(value.get("design")))
            and bool(_text(value.get("reason")))
        )
    if field_name == "autocorrelation_awareness":
        if not isinstance(value, dict):
            return False
        status = _text(value.get("status"))
        if status == "assessed":
            return (
                _finite_number(value.get("lag_1"))
                and -1 <= float(value["lag_1"]) <= 1
                and bool(_text(value.get("effective_sample_size_method")))
            )
        return status == "not_estimable" and bool(_text(value.get("reason")))
    if field_name == "seasonality_estimability":
        return (
            isinstance(value, dict)
            and _text(value.get("period")).casefold() in {
                "annual", "quarterly", "monthly", "weekly",
            }
            and _text(value.get("status")) in {
                "estimable", "estimable_with_limits", "not_estimable",
            }
            and _finite_number(value.get("minimum_complete_cycles"))
            and float(value["minimum_complete_cycles"]) > 0
            and _finite_number(value.get("complete_cycles"))
            and float(value["complete_cycles"]) >= 0
            and bool(_text(value.get("reason")))
        )
    if field_name == "multiplicity_handling":
        return (
            isinstance(value, dict)
            and _text(value.get("strategy")) in {
                "bonferroni", "holm", "benjamini_hochberg", "exploratory_label",
            }
            and _finite_number(value.get("comparison_count"))
            and float(value["comparison_count"]) > 1
            and _text(value.get("status")) in {"exploratory", "adjusted"}
        )
    if field_name in {"trend", "trend_statistics"}:
        return (
            isinstance(value, dict)
            and _finite_number(value.get("slope"))
            and _finite_number(value.get("r_squared"))
            and 0 <= float(value["r_squared"]) <= 1
        )
    return False


def _current_dataset_version_ids(workspace: Any) -> set[str]:
    try:
        version_ids = workspace.active_dataset_version_ids()
        if isinstance(version_ids, list):
            return {str(item) for item in version_ids if str(item)}
        datasets = workspace.list_datasets()
    except Exception:
        return set()
    if not isinstance(datasets, dict):
        return set()
    return {
        str(info.get("dataset_id"))
        for info in datasets.values()
        if isinstance(info, dict) and str(info.get("dataset_id") or "")
    }


def hydrate_computation_ref(
    ref: dict[str, Any],
    *,
    sessions_root: Path,
    current_session_id: str | None = None,
) -> dict[str, Any]:
    """Hydrate and hash-check a compact computation reference after restart."""
    if not isinstance(ref, dict):
        raise ValueError("computation ref must be an object")
    if ref.get("contract_version") != COMPUTATION_REF_CONTRACT_VERSION:
        raise ValueError("computation ref contract is invalid")
    ref_session_id = _text(ref.get("session_id"))
    expected_session_id = _text(current_session_id) or ref_session_id
    if not ref_session_id or ref_session_id != expected_session_id:
        raise ValueError("computation ref belongs to another session")
    artifact_path = _resolve_artifact_path(
        ref.get("artifact_path"),
        Path(sessions_root),
        session_id=expected_session_id,
    )
    if artifact_path is None or not artifact_path.is_file():
        raise ValueError("computation artifact is unavailable")
    try:
        envelope = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("computation artifact is invalid") from exc
    if not isinstance(envelope, dict) or envelope.get("contract_version") != TOOL_OUTPUT_CONTRACT_VERSION:
        raise ValueError("computation artifact is invalid")
    if any(
        _text(envelope.get(field_name)) != _text(ref.get(field_name))
        for field_name in (
            "session_id", "tool_call_id", "tool_name", "turn_id", "plan_id",
            "plan_digest", "step_id", "step_digest",
        )
    ):
        raise ValueError("computation artifact identity changed")
    if bool(envelope.get("success")) != bool(ref.get("success")):
        raise ValueError("computation success status changed")
    checked_fields = sorted(str(item) for item in ref.get("structured_checked_fields") or [])
    declared_fields = sorted(str(item) for item in envelope.get("evidence_fields") or [])
    if any(field_name not in declared_fields for field_name in checked_fields):
        raise ValueError("computation structured fields changed")
    if sorted(str(item) for item in envelope.get("dataset_versions") or []) != sorted(
        str(item) for item in ref.get("dataset_versions") or []
    ):
        raise ValueError("computation dataset versions changed")
    if computation_digest(envelope.get("arguments")) != ref.get("arguments_digest"):
        raise ValueError("computation arguments digest changed")
    if computation_digest(envelope.get("output")) != ref.get("output_digest"):
        raise ValueError("computation output digest changed")
    output = envelope.get("output")
    if not isinstance(output, dict):
        raise ValueError("computation output is invalid")
    return output


def _required_statistical_support(requirements: list[dict[str, Any]]) -> set[str]:
    return {
        support_name
        for requirement in requirements
        if (support_name := _SUPPORT_BY_REQUIREMENT.get(_text(requirement.get("name"))))
    }


def _statistical_support_matches_output(
    support: dict[str, Any],
    output_data: dict[str, Any],
) -> bool:
    comparable_fields = (
        "effective_sample_size",
        "effect_estimate",
        "confidence_interval",
        "test",
        "correlation",
        "assumptions",
        *sorted(_GENERIC_AUTHORITATIVE_SUPPORT_FIELDS),
    )
    return all(
        field_name not in support
        or field_name not in output_data
        or computation_digest(support[field_name]) == computation_digest(output_data[field_name])
        for field_name in comparable_fields
    )


def _independently_recompute_native_ab_test(
    *,
    envelope: dict[str, Any],
    ref: dict[str, Any],
    workspace: Any,
    statistical_support: dict[str, Any],
) -> dict[str, Any]:
    """Recompute the shipped two-group test from its exact dataset version."""
    if str(envelope.get("tool_name") or "") != "ab_test":
        return {}
    version_ids = [str(item) for item in ref.get("dataset_versions") or [] if str(item)]
    if len(version_ids) != 1:
        return {}
    try:
        frame = workspace.get_dataset_version(version_ids[0])
    except Exception:
        return {}
    if frame is None:
        return {}
    arguments = envelope.get("arguments")
    output = envelope.get("output")
    output_data = output.get("data") if isinstance(output, dict) else None
    if not isinstance(arguments, dict) or not isinstance(output_data, dict):
        return {}
    group_col = str(arguments.get("group_col") or "")
    metric_col = str(arguments.get("metric_col") or "")
    if group_col not in frame.columns or metric_col not in frame.columns:
        return {}
    groups = frame[group_col].dropna().unique()
    if len(groups) < 2:
        return {}
    try:
        left = frame.loc[frame[group_col] == groups[0], metric_col].dropna().astype(float)
        right = frame.loc[frame[group_col] == groups[1], metric_col].dropna().astype(float)
    except (TypeError, ValueError):
        return {}
    if len(left) < 2 or len(right) < 2:
        return {}

    from scipy import stats as sp_stats
    import warnings

    method = str(output_data.get("method") or "")
    if method == "ttest":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            _, levene_p = sp_stats.levene(left.to_numpy(), right.to_numpy())
            statistic, p_value = sp_stats.ttest_ind(
                left.to_numpy(),
                right.to_numpy(),
                equal_var=bool(math.isfinite(float(levene_p)) and levene_p > 0.05),
            )
    elif method == "mannwhitneyu":
        statistic, p_value = sp_stats.mannwhitneyu(
            left.to_numpy(),
            right.to_numpy(),
            alternative="two-sided",
        )
    else:
        return {}

    group_counts = {str(groups[0]): len(left), str(groups[1]): len(right)}
    difference_value = round(float(right.mean() - left.mean()), 4)
    effect_value = round(float(right.mean() - left.mean()), 8)
    expected_test = {
        "statistic": round(float(statistic), 4),
        "p_value": round(float(p_value), 6),
        "significant": bool(p_value < 0.05),
    }
    output_groups = output_data.get("groups")
    output_counts = {
        str(name): int(value.get("n"))
        for name, value in (output_groups or {}).items()
        if isinstance(value, dict) and _finite_number(value.get("n"))
    } if isinstance(output_groups, dict) else {}
    output_difference = output_data.get("difference")
    if (
        output_counts != group_counts
        or not isinstance(output_difference, dict)
        or not _finite_number(output_difference.get("absolute"))
        or abs(float(output_difference["absolute"]) - difference_value) > 1e-9
        or computation_digest(output_data.get("test")) != computation_digest(expected_test)
    ):
        return {}

    expected_sample = {"total": len(left) + len(right), "groups": group_counts}
    if method == "mannwhitneyu":
        effect_value = round(
            float(1 - (2 * float(statistic) / (len(left) * len(right)))),
            8,
        )
        effect_metric = "rank_biserial_correlation"
    else:
        effect_metric = "mean_difference"
    expected_effect = {"value": effect_value, "metric": effect_metric}
    support_sample = statistical_support.get("effective_sample_size")
    support_effect = statistical_support.get("effect_estimate")
    support_test = statistical_support.get("test")
    if computation_digest(support_sample) != computation_digest(expected_sample):
        return {}
    if not isinstance(support_effect, dict) or not _finite_number(support_effect.get("value")):
        return {}
    if (
        abs(float(support_effect["value"]) - effect_value) > 1e-9
        or str(support_effect.get("metric") or "") != effect_metric
    ):
        return {}
    if computation_digest(support_test) != computation_digest(expected_test):
        return {}
    return {
        "effective_sample_size": expected_sample,
        "effect_estimate": expected_effect,
        "test": expected_test,
    }


def _independently_recompute_group_mean(
    *,
    envelope: dict[str, Any],
    ref: dict[str, Any],
    workspace: Any,
    statistical_support: dict[str, Any],
) -> list[str]:
    """Recompute the small supported core estimand from the exact version frame."""
    if str(envelope.get("capability_id") or "") != "analysis.group_mean_difference":
        return []
    output = envelope.get("output")
    output_data = output.get("data") if isinstance(output, dict) else None
    if not isinstance(output_data, dict):
        return []
    spec = output_data.get("recomputation_spec")
    if not isinstance(spec, dict) or spec.get("operation") != "group_mean_difference":
        return []
    version_ids = [str(item) for item in ref.get("dataset_versions") or [] if str(item)]
    if len(version_ids) != 1:
        return []
    try:
        frame = workspace.get_dataset_version(version_ids[0])
    except Exception:
        return []
    if frame is None:
        return []
    group_col = str(spec.get("group_column") or "")
    metric_col = str(spec.get("metric_column") or "")
    if group_col not in frame.columns or metric_col not in frame.columns:
        return []
    left_group = spec.get("left_group")
    right_group = spec.get("right_group")
    try:
        left = frame.loc[frame[group_col] == left_group, metric_col].dropna().astype(float)
        right = frame.loc[frame[group_col] == right_group, metric_col].dropna().astype(float)
    except (TypeError, ValueError):
        return []
    if left.empty or right.empty:
        return []
    effect = float(left.mean() - right.mean())
    support_effect = statistical_support.get("effect_estimate")
    support_sample = statistical_support.get("effective_sample_size")
    if not isinstance(support_effect, dict) or not isinstance(support_sample, dict):
        return []
    try:
        reported_effect = float(support_effect.get("value"))
        reported_total = int(support_sample.get("total"))
        reported_groups = dict(support_sample.get("groups") or {})
    except (TypeError, ValueError):
        return []
    expected_groups = {str(left_group): len(left), str(right_group): len(right)}
    normalized_groups = {str(key): int(value) for key, value in reported_groups.items()}
    if abs(reported_effect - effect) > 1e-9:
        return []
    if reported_total != len(left) + len(right) or normalized_groups != expected_groups:
        return []
    return ["effective_sample_size", "effect_estimate"]


def bind_evidence_to_computations(
    record: Any,
    *,
    computation_refs: list[dict[str, Any]],
    sessions_root: Path,
    current_session_id: str,
    current_turn_id: str,
    current_plan: dict[str, Any],
    workspace: Any,
) -> EvidenceValidationResult:
    """Resolve LLM-supplied call IDs into verified server-owned references."""
    if not isinstance(record, dict):
        return _error("invalid_evidence", "EvidenceRecord must be a JSON object.")
    if "computation_refs" in record or "verification_level" in record:
        return _error(
            "authoritative_provenance_fields_forbidden",
            "EvidenceRecord computation refs and verification levels are server-owned.",
        )
    if any(
        isinstance(measurement, dict)
        and any(
            field_name in measurement
            for field_name in (
                "identity",
                "identity_status",
                "projection_origin",
            )
        )
        for measurement in record.get("measurements") or []
    ):
        return _error(
            "authoritative_measurement_identity_forbidden",
            "Measurement identity is server-owned and cannot be supplied by the model.",
        )
    source_ids = record.get("source_tool_call_ids")
    if not isinstance(source_ids, list) or not source_ids or any(
        not isinstance(item, str) or not item.strip() for item in source_ids
    ):
        return _error(
            "missing_source_tool_call_ids",
            "EvidenceRecord v2 requires non-empty source_tool_call_ids.",
        )
    plan_id = _text(record.get("plan_id"))
    step_id = _text(record.get("step_id"))
    canonical_plan_id = _text(current_plan.get("id")) if isinstance(current_plan, dict) else ""
    if not canonical_plan_id or plan_id != canonical_plan_id:
        return _error(
            "evidence_outside_current_plan",
            "EvidenceRecord plan_id does not match the current analysis plan.",
            current_plan_id=canonical_plan_id,
            record_plan_id=plan_id,
        )
    current_plan_digest = analysis_plan_semantic_digest(current_plan)

    step_requirements = []
    current_step: dict[str, Any] | None = None
    if isinstance(current_plan, dict):
        for candidate in current_plan.get("method_plan") or []:
            if isinstance(candidate, dict) and str(candidate.get("step_id") or "").strip() == step_id:
                current_step = candidate
                break
        grouped = current_plan.get("analysis_requirements")
        if isinstance(grouped, dict) and isinstance(grouped.get(step_id), list):
            step_requirements = [item for item in grouped[step_id] if isinstance(item, dict)]
    if current_step is None:
        return _error(
            "evidence_step_outside_current_plan",
            "EvidenceRecord step_id is not part of the current analysis plan.",
        )
    current_step_digest = analysis_step_semantic_digest(current_step)
    dataset = _text(record.get("dataset"))
    step_datasets = {_text(item) for item in current_step.get("dataset_inputs") or [] if _text(item)}
    if dataset not in step_datasets:
        return _error(
            "evidence_dataset_outside_current_step",
            "EvidenceRecord dataset is not an input to the current plan step.",
        )
    dataset_contract_id = _text(record.get("dataset_contract_id"))
    step_contract_ids = {
        _text(item) for item in current_step.get("dataset_contract_ids") or [] if _text(item)
    }
    if dataset_contract_id not in step_contract_ids:
        return _error(
            "evidence_contract_outside_current_step",
            "EvidenceRecord dataset contract is not bound to the current plan step.",
        )
    claim_key = _text(record.get("claim_key"))
    required_claim_keys = {
        _text(item) for item in current_step.get("required_claim_keys") or [] if _text(item)
    }
    if claim_key not in required_claim_keys:
        return _error(
            "evidence_claim_outside_current_step",
            "EvidenceRecord claim_key is not required by the current plan step.",
        )
    expected_requirement_ids = {
        _text(item.get("id")) for item in step_requirements if _text(item.get("id"))
    }
    requirement_ids = record.get("requirement_ids")
    if not isinstance(requirement_ids, list) or any(
        not isinstance(item, str) or not item.strip() for item in requirement_ids
    ):
        return _error(
            "invalid_requirement_ids",
            "EvidenceRecord v2 requires canonical requirement_ids.",
        )
    provided_requirement_ids = {_text(item) for item in requirement_ids}
    if not provided_requirement_ids or provided_requirement_ids - expected_requirement_ids:
        return _error(
            "invalid_requirement_ids",
            "EvidenceRecord requirement_ids must be a non-empty canonical subset of the current plan step.",
            expected=sorted(expected_requirement_ids),
            provided=sorted(provided_requirement_ids),
        )
    selected_requirements = [
        item
        for item in step_requirements
        if _text(item.get("id")) in provided_requirement_ids
    ]
    selected_requirement_names = {
        _text(item.get("name")) for item in selected_requirements if _text(item.get("name"))
    }
    evidence_requirement = _text(record.get("evidence_requirement"))
    if evidence_requirement not in selected_requirement_names:
        return _error(
            "invalid_evidence_requirement",
            "EvidenceRecord evidence_requirement must name one of its declared canonical requirements.",
            selected=sorted(selected_requirement_names),
            provided=evidence_requirement,
        )

    statistical_support = record.get("statistical_support")
    required_support = _required_statistical_support(selected_requirements)
    if required_support:
        if not isinstance(statistical_support, dict):
            return _error(
                "missing_statistical_support",
                "EvidenceRecord is missing structured statistical_support.",
                required=sorted(required_support),
            )
        missing_support = sorted(
            field_name
            for field_name in required_support
            if field_name not in statistical_support or _missing(statistical_support.get(field_name))
        )
        if missing_support:
            return _error(
                "missing_statistical_support",
                "EvidenceRecord is missing required statistical support fields.",
                missing=missing_support,
            )

    refs = [item for item in computation_refs if isinstance(item, dict)]
    resolved_refs: list[dict[str, Any]] = []
    authoritative_support_fields: set[str] = set()
    authoritative_support: dict[str, Any] = {}
    authoritative_summary_bindings: list[tuple[float, frozenset[str]]] = []
    independently_recomputed_fields: set[str] = set()
    server_capability_ids: set[str] = set()
    server_tool_names: set[str] = set()
    server_method_labels: set[str] = set()
    server_method_tokens: set[str] = set()
    current_versions = _current_dataset_version_ids(workspace)
    for source_id in dict.fromkeys(item.strip() for item in source_ids):
        candidates = [item for item in refs if _text(item.get("tool_call_id")) == source_id]
        if not candidates:
            return _error(
                "unknown_source_tool_call_id",
                f"Unknown source tool call: {source_id}",
                tool_call_id=source_id,
            )
        current_turn = [
            item for item in candidates
            if _text(item.get("turn_id")) == _text(current_turn_id)
        ]
        if not current_turn:
            return _error(
                "computation_outside_current_turn",
                "EvidenceRecord source tool call is outside the current turn.",
                tool_call_id=source_id,
            )
        ref = current_turn[-1]
        if _text(ref.get("session_id")) != _text(current_session_id):
            return _error(
                "computation_outside_current_session",
                "EvidenceRecord source tool call belongs to another session.",
                tool_call_id=source_id,
            )
        if not bool(ref.get("success")):
            return _error(
                "unsuccessful_computation_ref",
                "EvidenceRecord cannot cite an unsuccessful tool call.",
                tool_call_id=source_id,
            )
        if _text(ref.get("plan_id")) != plan_id:
            return _error("computation_outside_current_plan", "Computation ref belongs to another plan.")
        if ref.get("plan_digest") != current_plan_digest or ref.get("step_digest") != current_step_digest:
            return _error(
                "computation_outside_current_plan_revision",
                "Computation ref belongs to a different semantic revision of the current plan.",
                ref_plan_digest=ref.get("plan_digest"),
                current_plan_digest=current_plan_digest,
                ref_step_digest=ref.get("step_digest"),
                current_step_digest=current_step_digest,
            )
        if _text(ref.get("step_id")) != step_id:
            return _error("computation_outside_current_step", "Computation ref belongs to another plan step.")
        ref_versions = {
            _text(item) for item in ref.get("dataset_versions", []) if _text(item)
        }
        if ref_versions and not ref_versions <= current_versions:
            return _error(
                "stale_computation_dataset_version",
                "Computation ref uses a dataset version that is no longer active.",
                stale_dataset_versions=sorted(ref_versions - current_versions),
            )
        artifact_path = _resolve_artifact_path(
            ref.get("artifact_path"),
            Path(sessions_root),
            session_id=_text(current_session_id),
        )
        if artifact_path is None or not artifact_path.is_file():
            return _error("computation_artifact_unavailable", "Computation artifact is unavailable.")
        try:
            envelope = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return _error("computation_artifact_invalid", "Computation artifact is invalid.")
        if not isinstance(envelope, dict) or envelope.get("contract_version") != TOOL_OUTPUT_CONTRACT_VERSION:
            return _error("computation_artifact_invalid", "Computation artifact is invalid.")
        if any(
            _text(envelope.get(field_name)) != _text(ref.get(field_name))
            for field_name in (
                "session_id", "tool_call_id", "tool_name", "turn_id", "plan_id",
                "plan_digest", "step_id", "step_digest",
            )
        ):
            return _error("computation_artifact_identity_mismatch", "Computation artifact identity changed.")
        if bool(envelope.get("success")) != bool(ref.get("success")):
            return _error("computation_artifact_identity_mismatch", "Computation success status changed.")
        if sorted(str(item) for item in envelope.get("dataset_versions") or []) != sorted(ref_versions):
            return _error("computation_artifact_identity_mismatch", "Computation dataset versions changed.")
        try:
            active_info = workspace.get_active_version_info(dataset)
        except Exception:
            active_info = None
        active_dataset_id = str((active_info or {}).get("dataset_id") or "")
        if not active_dataset_id or active_dataset_id not in ref_versions:
            return _error(
                "computation_dataset_not_bound",
                "Computation ref is not bound to the EvidenceRecord dataset version.",
                dataset=dataset,
            )
        if computation_digest(envelope.get("arguments")) != ref.get("arguments_digest"):
            return _error("computation_arguments_digest_mismatch", "Computation arguments digest changed.")
        if computation_digest(envelope.get("output")) != ref.get("output_digest"):
            return _error("computation_output_digest_mismatch", "Computation output digest changed.")
        output = envelope.get("output")
        if isinstance(output, dict):
            authoritative_summary_bindings.extend(_text_bindings(output.get("summary")))
        output_data = output.get("data") if isinstance(output, dict) else None
        capability_id = _text(envelope.get("capability_id") or ref.get("capability_id"))
        if capability_id:
            server_capability_ids.add(capability_id)
            server_method_labels.add(capability_id)
        tool_name = _text(envelope.get("tool_name") or ref.get("tool_name"))
        if tool_name:
            server_tool_names.add(tool_name)
        checked_fields = {
            str(item) for item in ref.get("structured_checked_fields") or [] if str(item)
        }
        declared_fields = {
            str(item) for item in envelope.get("evidence_fields") or [] if str(item)
        }
        verified_output = {}
        if isinstance(output_data, dict):
            for field_name in checked_fields:
                if (
                    field_name not in declared_fields
                    or field_name not in output_data
                    or not _structured_field_valid(field_name, output_data.get(field_name))
                ):
                    return _error(
                        "computation_artifact_identity_mismatch",
                        "Computation structured field validation changed.",
                    )
                verified_output[field_name] = output_data[field_name]
        if (
            isinstance(statistical_support, dict)
            and verified_output
            and not _statistical_support_matches_output(statistical_support, verified_output)
        ):
            return _error(
                "statistical_support_mismatch",
                "EvidenceRecord statistical support differs from the authoritative tool output.",
                tool_call_id=source_id,
            )
        for field_name, value in verified_output.items():
            if (
                field_name in authoritative_support
                and computation_digest(authoritative_support[field_name]) != computation_digest(value)
            ):
                return _error(
                    "conflicting_authoritative_support",
                    "Computation refs disagree on authoritative statistical support.",
                    field=field_name,
                )
            authoritative_support[field_name] = value
            authoritative_support_fields.add(field_name)
        resolved_ref = dict(ref)
        recomputed_fields = _independently_recompute_group_mean(
            envelope=envelope,
            ref=ref,
            workspace=workspace,
            statistical_support=(statistical_support if isinstance(statistical_support, dict) else {}),
        )
        recomputed_support = _independently_recompute_native_ab_test(
            envelope=envelope,
            ref=ref,
            workspace=workspace,
            statistical_support=(statistical_support if isinstance(statistical_support, dict) else {}),
        )
        if recomputed_support:
            recomputed_fields = sorted(recomputed_support)
            for field_name, value in recomputed_support.items():
                if (
                    field_name in authoritative_support
                    and computation_digest(authoritative_support[field_name]) != computation_digest(value)
                ):
                    return _error(
                        "conflicting_authoritative_support",
                        "Computation refs disagree on independently recomputed support.",
                        field=field_name,
                    )
                authoritative_support[field_name] = value
                authoritative_support_fields.add(field_name)
            if tool_name == "ab_test" and isinstance(output_data, dict):
                executed_method = _text(output_data.get("method")).casefold()
                if executed_method in {"ttest", "mannwhitneyu", "chi2"}:
                    server_method_tokens.add(executed_method)
                if executed_method == "ttest":
                    server_method_tokens.add("independent")
                    levene = output_data.get("levene_test")
                    if isinstance(levene, dict) and levene.get("equal_variance") is False:
                        server_method_tokens.add("welch")
                    elif isinstance(levene, dict) and levene.get("equal_variance") is True:
                        server_method_tokens.add("student")
        elif recomputed_fields and isinstance(statistical_support, dict):
            for field_name in recomputed_fields:
                if field_name in statistical_support:
                    authoritative_support[field_name] = statistical_support[field_name]
                    authoritative_support_fields.add(field_name)
        if recomputed_fields:
            resolved_ref["verification_level"] = "independently_recomputed"
            resolved_ref["independently_recomputed_fields"] = recomputed_fields
            independently_recomputed_fields.update(recomputed_fields)
        resolved_refs.append(resolved_ref)

    claim_text = " ".join((
        _text(record.get("claim")),
        _text(record.get("result_summary")),
    ))
    trusted_identities = " ".join(sorted(server_capability_ids | server_tool_names)).casefold()
    if "regression" in trusted_identities:
        server_method_tokens.add("regression")
    unsupported_semantics = _unsupported_claim_semantics(
        claim_text,
        capability_ids=server_capability_ids,
        tool_names=server_tool_names,
        method_tokens=server_method_tokens,
    )
    if unsupported_semantics:
        return _error(
            "unsupported_claim_semantics",
            "EvidenceRecord claim semantics are not supported by the bound computation.",
            unsupported_semantics=unsupported_semantics,
        )
    for ref in resolved_refs:
        tool_name = _text(ref.get("tool_name"))
        if tool_name and not _text(ref.get("capability_id")):
            server_method_labels.add(tool_name)
    server_method = ", ".join(sorted(server_method_labels)) or "server-bound computation"

    normalized = {
        field_name: record[field_name]
        for field_name in _SAFE_MODEL_EVIDENCE_FIELDS
        if field_name in record
    }
    normalized["contract_version"] = EVIDENCE_RECORD_CONTRACT_VERSION
    normalized["source_tool_call_ids"] = [item["tool_call_id"] for item in resolved_refs]
    normalized["requirement_ids"] = sorted(provided_requirement_ids)
    normalized["computation_refs"] = resolved_refs
    normalized["provenance_status"] = "bound"
    disclosed_assumptions = []
    if isinstance(statistical_support, dict) and "assumptions" not in authoritative_support:
        assumptions = statistical_support.get("assumptions")
        if isinstance(assumptions, list):
            if any(
                isinstance(item, dict)
                and _text(item.get("status")) in {"passed", "satisfied", "success", "successful"}
                for item in assumptions
            ):
                return _error(
                    "unverified_assumption_check",
                    "Model-authored assumptions cannot claim a passed check.",
                )
            disclosed_assumptions = assumptions
    normalized_support = dict(authoritative_support)
    if disclosed_assumptions:
        normalized_support["assumptions"] = disclosed_assumptions
        normalized["assumptions"] = disclosed_assumptions
    if normalized_support:
        normalized["statistical_support"] = normalized_support
    else:
        normalized.pop("statistical_support", None)
    authoritative_requirement_fields: set[str] = set()
    if "effective_sample_size" in authoritative_support:
        normalized["effective_sample_size"] = authoritative_support["effective_sample_size"]
        effective_sample = authoritative_support["effective_sample_size"]
        authoritative_total = (
            effective_sample.get("total") if isinstance(effective_sample, dict) else None
        )
        supplied_sample_size = record.get("sample_size")
        if (
            _finite_number(supplied_sample_size)
            and _finite_number(authoritative_total)
            and not math.isclose(
                float(supplied_sample_size),
                float(authoritative_total),
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
        ):
            return _error(
                "numeric_evidence_mismatch",
                "EvidenceRecord sample_size differs from authoritative statistical support.",
                field="sample_size",
                value=float(supplied_sample_size),
            )
        if _finite_number(authoritative_total):
            normalized["sample_size"] = authoritative_total
            authoritative_requirement_fields.update({"sample_size", "effective_sample_size"})
    if "effect_estimate" in authoritative_support:
        normalized["effect_estimate"] = authoritative_support["effect_estimate"]
        normalized["effect_size"] = authoritative_support["effect_estimate"]
        normalized["metric_delta"] = authoritative_support["effect_estimate"]
        authoritative_requirement_fields.update({
            "effect",
            "effect_estimate",
            "effect_size",
            "metric_delta",
        })
    if "confidence_interval" in authoritative_support:
        normalized["confidence_interval"] = authoritative_support["confidence_interval"]
        authoritative_requirement_fields.add("confidence_interval")
    if "test" in authoritative_support:
        normalized["test"] = authoritative_support["test"]
        normalized["significance"] = authoritative_support["test"]
        authoritative_requirement_fields.update({"test", "significance"})
    if "correlation" in authoritative_support:
        normalized["correlation"] = authoritative_support["correlation"]
        authoritative_requirement_fields.add("correlation")
    if "assumptions" in authoritative_support:
        normalized["assumptions"] = authoritative_support["assumptions"]
        normalized["assumption_checks"] = authoritative_support["assumptions"]
        authoritative_requirement_fields.update({"assumptions", "assumption_checks"})
    for field_name in sorted(_GENERIC_AUTHORITATIVE_SUPPORT_FIELDS):
        if field_name not in authoritative_support:
            continue
        normalized[field_name] = authoritative_support[field_name]
        authoritative_requirement_fields.add(field_name)

    numeric_mismatch = _material_numeric_mismatch(
        record,
        authoritative_support=authoritative_support,
        authoritative_summary_bindings=authoritative_summary_bindings,
        evidence_requirement=evidence_requirement,
    )
    if numeric_mismatch is not None:
        return numeric_mismatch
    normalized["tool_calls"] = [
        {
            "name": _text(ref.get("tool_name")),
            "capability_id": _text(ref.get("capability_id")),
            "tool_call_id": _text(ref.get("tool_call_id")),
        }
        for ref in resolved_refs
    ]
    normalized["method"] = server_method
    normalized["calculation_method"] = server_method
    normalized["method_detail"] = "Server-bound computation output with verified provenance."
    projected_measurements = []
    for measurement in record.get("measurements") or []:
        projected = dict(measurement)
        projected["method"] = server_method
        projected["unit"] = _projected_measurement_unit(
            projected.get("value"),
            evidence_requirement,
            authoritative_support,
        )
        projected_measurements.append(projected)
    normalized["measurements"] = projected_measurements
    authoritative_requirement_fields.update({
        "calculation_method",
        "method",
        "method_detail",
    })
    from data_agent.agent.analysis_requirements import evaluate_requirement_satisfaction

    evaluation_record = dict(normalized)
    for requirement in selected_requirements:
        for field_name in requirement.get("required_evidence_fields") or []:
            field_text = _text(field_name)
            if (
                field_text not in authoritative_requirement_fields
                and field_text not in _SAFE_MODEL_REQUIREMENT_FIELDS
            ):
                evaluation_record.pop(field_text, None)
    evaluated = evaluate_requirement_satisfaction(selected_requirements, [evaluation_record])
    unmet_requirement_ids = sorted(
        item["id"]
        for item in evaluated
        if item.get("status") not in {"satisfied", "not_applicable"}
    )
    if unmet_requirement_ids:
        return _error(
            "unsatisfied_analysis_requirements",
            "EvidenceRecord does not satisfy its declared analysis requirements.",
            requirement_ids=unmet_requirement_ids,
        )
    levels = {str(item.get("verification_level") or "traceable") for item in resolved_refs}
    structured_support_bound = required_support <= authoritative_support_fields
    if (
        structured_support_bound
        and required_support
        and required_support <= independently_recomputed_fields
        and levels == {"independently_recomputed"}
    ):
        normalized["verification_level"] = "independently_recomputed"
    elif structured_support_bound and levels <= {"structured_checked", "independently_recomputed"}:
        normalized["verification_level"] = "structured_checked"
    else:
        normalized["verification_level"] = "traceable"
    return EvidenceValidationResult(True, record=normalized)


def validate_measurement(
    measurement: Any,
    *,
    index: int = 0,
    require_identity: bool = False,
) -> EvidenceValidationResult:
    if not isinstance(measurement, dict):
        return _error(
            "invalid_measurement",
            "Each Stage 3C0B measurement must be an object.",
            index=index,
        )

    missing_measurement_fields = [
        field_name
        for field_name in MEASUREMENT_FIELDS
        if field_name not in measurement or _missing(measurement.get(field_name))
    ]
    if missing_measurement_fields:
        return _error(
            "missing_measurement_fields",
            "Stage 3C0B measurement is missing required fields.",
            index=index,
            missing=missing_measurement_fields,
        )

    normalized = dict(measurement)
    for field_name in NORMALIZED_MEASUREMENT_TEXT_FIELDS:
        if field_name in normalized:
            normalized[field_name] = _text(normalized[field_name])
    if "identity" not in normalized:
        if require_identity:
            return _error(
                "missing_measurement_identity",
                "A server-projected measurement identity is required.",
                index=index,
            )
        return EvidenceValidationResult(True, record=normalized)

    identity_validation = validate_measurement_identity(normalized["identity"])
    if not identity_validation.ok:
        return identity_validation
    identity = identity_validation.record
    measurement_metric = _text(normalized.get("metric"))
    identity_metric = identity.get("metric_key")
    if (
        identity_metric != measurement_metric
        and not identity_metric.startswith(measurement_metric + "::")
    ):
        return _error(
            "measurement_identity_material_mismatch",
            "Measurement metric does not match its identity metric key.",
            index=index,
            field="metric_key",
            identity_value=identity_metric,
            measurement_value=measurement_metric,
        )
    material_fields = {
        "value": normalized.get("value"),
        "unit": _text(normalized.get("unit")),
        "direction": _text(normalized.get("direction")),
        "time_scope": _text(normalized.get("time_scope")),
        "population_scope": _text(normalized.get("population_scope")),
    }
    for field_name, expected in material_fields.items():
        if identity.get(field_name) != expected:
            return _error(
                "measurement_identity_material_mismatch",
                "Measurement identity disagrees with its enclosing measurement.",
                index=index,
                field=field_name,
                identity_value=identity.get(field_name),
                measurement_value=expected,
            )
    normalized["identity"] = identity
    return EvidenceValidationResult(True, record=normalized)


def _validate_measurement_identity_provenance(
    identity: dict[str, Any],
    *,
    record: dict[str, Any],
    computation_refs: list[dict[str, Any]],
    index: int,
) -> EvidenceValidationResult:
    expected_record_fields = {
        "claim_key": _text(record.get("claim_key")),
        "plan_id": _text(record.get("plan_id")),
        "step_id": _text(record.get("step_id")),
        "allowed_claim_class": _text(record.get("allowed_claim_class")),
    }
    for field_name, expected in expected_record_fields.items():
        if identity.get(field_name) != expected:
            return _error(
                "measurement_identity_provenance_mismatch",
                "Measurement identity disagrees with its enclosing evidence record.",
                index=index,
                field=field_name,
            )

    for field_name in ("requirement_ids", "dataset_versions"):
        values = record.get(field_name)
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or len(values) != len(set(values))
            or identity.get(field_name) != sorted(values)
        ):
            return _error(
                "measurement_identity_provenance_mismatch",
                "Measurement identity scope disagrees with its evidence record.",
                index=index,
                field=field_name,
            )

    matching_refs = [
        ref
        for ref in computation_refs
        if computation_ref_key(ref) == identity.get("computation_ref_id")
    ]
    if len(matching_refs) != 1:
        return _error(
            "measurement_identity_provenance_mismatch",
            "Measurement identity does not resolve to exactly one bound computation.",
            index=index,
            field="computation_ref_id",
        )
    ref = matching_refs[0]
    ref_scope = ref.get("dataset_versions")
    ref_requirements = ref.get("requirement_ids")
    if (
        not isinstance(ref_scope, list)
        or any(not isinstance(item, str) or not item.strip() for item in ref_scope)
        or len(ref_scope) != len(set(ref_scope))
        or sorted(ref_scope) != identity["dataset_versions"]
        or not isinstance(ref_requirements, list)
        or any(
            not isinstance(item, str) or not item.strip()
            for item in ref_requirements
        )
        or len(ref_requirements) != len(set(ref_requirements))
        or sorted(ref_requirements) != identity["requirement_ids"]
        or _text(ref.get("claim_key")) != identity["claim_key"]
        or _text(ref.get("plan_id")) != identity["plan_id"]
        or _text(ref.get("step_id")) != identity["step_id"]
        or _text(ref.get("plan_digest")) != identity["plan_version"]
    ):
        return _error(
            "measurement_identity_provenance_mismatch",
            "Measurement identity disagrees with its bound computation.",
            index=index,
        )
    return EvidenceValidationResult(True, record=identity)


def validate_evidence_record(
    record: Any,
    *,
    current_plan_id: str | None = None,
    require_measurement_identity: bool = False,
) -> EvidenceValidationResult:
    if not isinstance(record, dict):
        return _error("invalid_evidence", "EvidenceRecord must be a JSON object.")

    plan_id = _text(record.get("plan_id"))
    current_plan = _text(current_plan_id)
    if not current_plan or plan_id != current_plan:
        return _error(
            "evidence_outside_current_plan",
            "EvidenceRecord plan_id does not match the current analysis plan.",
            current_plan_id=current_plan,
            record_plan_id=plan_id,
        )

    if "measurements" not in record or _missing(record.get("measurements")):
        return _error(
            "missing_measurements",
            "Stage 3C0B EvidenceRecord requires non-empty canonical measurements.",
            has_legacy_metrics=bool(record.get("metrics")),
        )

    missing = [
        field_name
        for field_name in CANONICAL_EVIDENCE_FIELDS
        if field_name not in record or _missing(record.get(field_name))
    ]
    if missing:
        return _error(
            "missing_canonical_fields",
            "Stage 3C0B EvidenceRecord is missing canonical fields.",
            missing=missing,
        )

    if record.get("contract_version") == EVIDENCE_RECORD_CONTRACT_VERSION:
        v2_required = (
            "source_tool_call_ids",
            "requirement_ids",
            "computation_refs",
            "provenance_status",
            "verification_level",
        )
        missing_v2 = [
            field_name
            for field_name in v2_required
            if field_name not in record or _missing(record.get(field_name))
        ]
        if missing_v2:
            return _error(
                "missing_evidence_v2_fields",
                "EvidenceRecord v2 is missing bound provenance or assurance fields.",
                missing=missing_v2,
            )
        if record.get("provenance_status") != "bound":
            return _error("invalid_provenance_status", "EvidenceRecord v2 provenance must be server-bound.")
        if record.get("verification_level") not in {
            "traceable",
            "structured_checked",
            "independently_recomputed",
        }:
            return _error("invalid_verification_level", "EvidenceRecord v2 verification level is invalid.")
        refs = record.get("computation_refs")
        if not isinstance(refs, list) or any(
            not isinstance(ref, dict)
            or ref.get("contract_version") != COMPUTATION_REF_CONTRACT_VERSION
            for ref in refs
        ):
            return _error("invalid_computation_refs", "EvidenceRecord v2 computation refs are invalid.")

    measurements = record.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        return _error(
            "missing_measurements",
            "Stage 3C0B EvidenceRecord requires a non-empty measurements list.",
        )

    normalized_measurements = []
    identity_count = 0
    for index, measurement in enumerate(measurements):
        projection_fields_present = (
            isinstance(measurement, dict)
            and (
                "identity_status" in measurement
                or "projection_origin" in measurement
            )
        )
        if projection_fields_present and not (
            measurement.get("identity_status") == "metric_identity_missing"
            and measurement.get("projection_origin")
            == MEASUREMENT_PROJECTION_ORIGIN
        ):
            return _error(
                "invalid_measurement_projection_origin",
                "Unbound measurement origin is not server-projector owned.",
                index=index,
            )
        identity_exempt = (
            isinstance(measurement, dict)
            and (
                (
                    measurement.get("identity_status")
                    == "metric_identity_missing"
                    and measurement.get("projection_origin")
                    == MEASUREMENT_PROJECTION_ORIGIN
                )
                or _text(measurement.get("metric")) == "structured_computation"
            )
        )
        measurement_validation = validate_measurement(
            measurement,
            index=index,
            require_identity=(
                require_measurement_identity and not identity_exempt
            ),
        )
        if not measurement_validation.ok:
            return measurement_validation
        normalized_measurement = measurement_validation.record
        identity = normalized_measurement.get("identity")
        if isinstance(identity, dict):
            identity_count += 1
            provenance_validation = _validate_measurement_identity_provenance(
                identity,
                record=record,
                computation_refs=(
                    record.get("computation_refs")
                    if isinstance(record.get("computation_refs"), list)
                    else []
                ),
                index=index,
            )
            if not provenance_validation.ok:
                return provenance_validation
        normalized_measurements.append(normalized_measurement)
    if require_measurement_identity and identity_count == 0:
        return _error(
            "missing_measurement_identity",
            "Server-projected evidence requires at least one measurement identity.",
        )

    normalized = dict(record)
    for field_name in NORMALIZED_EVIDENCE_TEXT_FIELDS:
        if field_name in normalized:
            normalized[field_name] = _text(normalized[field_name])
    normalized["measurements"] = normalized_measurements
    if normalized.get("contract_version") == EVIDENCE_RECORD_CONTRACT_VERSION:
        normalized["id"] = evidence_v2_id_for(
            normalized.get("plan_id"),
            normalized.get("step_id"),
            normalized.get("claim_key"),
            requirement_ids=normalized.get("requirement_ids"),
            computation_refs=normalized.get("computation_refs"),
        )
    else:
        normalized["id"] = evidence_id_for(
            normalized.get("plan_id"),
            normalized.get("step_id"),
            normalized.get("claim_key"),
        )
    return EvidenceValidationResult(True, record=normalized)


def validate_stage3c0b_measurement(
    measurement: Any,
    *,
    index: int = 0,
) -> EvidenceValidationResult:
    """Read-only compatibility alias for the canonical validator."""
    return validate_measurement(measurement, index=index)


def validate_stage3c0b_evidence(
    record: Any,
    *,
    current_plan_id: str | None = None,
) -> EvidenceValidationResult:
    """Read-only compatibility alias for the canonical validator."""
    return validate_evidence_record(record, current_plan_id=current_plan_id)


# ---------------------------------------------------------------------------
# Automatic structured-computation evidence projection (Task 9).
#
# Successful structured computations auto-project ``evidence_record.v2``
# evidence without the model calling ``record_evidence_record``. The model
# is no longer the bookkeeper for evidence that the server can derive from
# a successful, exactly-bound, structured computation. Ineligible paths
# stay computation-only and emit a bounded diagnostic instead.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceProjectionResult:
    """Outcome of an automatic structured-computation evidence projection."""

    projected: bool
    record: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    diagnostics: tuple[dict[str, Any], ...] = ()


_EMPTY_CATALOG_HEADER = (
    "可用证据：0 条。请基于现有计算诊断说明局限，不要重新运行工具来制造证据。"
)


def _capability_evidence_fields(capability: Any) -> list[str]:
    if not isinstance(capability, dict):
        return []
    raw = capability.get("evidence_fields")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str) and item]


def _step_for_id(plan: Any, step_id: str) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    method_plan = plan.get("method_plan")
    if not isinstance(method_plan, list):
        return {}
    for raw_step in method_plan:
        if isinstance(raw_step, dict) and _text(raw_step.get("step_id")) == step_id:
            return raw_step
    return {}


def _step_dataset_inputs(plan: Any, step_id: str) -> list[str]:
    step = _step_for_id(plan, step_id)
    raw = step.get("dataset_inputs")
    if not isinstance(raw, list):
        return []
    return [_text(item) for item in raw if _text(item)]


def _active_dataset_versions_for_step(
    dataset_contracts: Any, step_datasets: Sequence[str]
) -> set[str]:
    if not isinstance(dataset_contracts, list):
        return set()
    step_set = {_text(item) for item in step_datasets if _text(item)}
    versions: set[str] = set()
    for contract in dataset_contracts:
        if not isinstance(contract, dict):
            continue
        if step_set and _text(contract.get("dataset")) not in step_set:
            continue
        version = _text(contract.get("dataset_id") or contract.get("dataset_version_id"))
        if version:
            versions.add(version)
    return versions


def _evidence_requirement_name(
    plan: Any, step_id: str, requirement_ids: Sequence[str]
) -> str:
    if not isinstance(plan, dict):
        return ""
    grouped = plan.get("analysis_requirements")
    candidates: list[dict[str, Any]] = []
    if isinstance(grouped, dict):
        bucket = grouped.get(step_id)
        if isinstance(bucket, list):
            candidates = [item for item in bucket if isinstance(item, dict)]
    selected_ids = {_text(item) for item in requirement_ids if _text(item)}
    for requirement in candidates:
        if selected_ids and _text(requirement.get("id")) in selected_ids:
            name = _text(requirement.get("name"))
            if name:
                return name
    if selected_ids:
        return sorted(selected_ids)[0]
    return ""


def _claim_neutral_summary(
    *,
    capability: dict[str, Any],
    output_data: dict[str, Any],
) -> str:
    """Build a claim-neutral summary string from declared structured fields.

    The summary reports *what* the tool computed without framing it as a
    material claim. Model prose is never parsed into evidence.
    """

    cap_id = _text(capability.get("capability_id")) if isinstance(capability, dict) else ""
    parts: list[str] = []
    for field_name in _capability_evidence_fields(capability):
        value = _resolve_dotted_evidence_field(output_data, field_name)
        if value is None:
            continue
        rendered = _render_structured_value(value)
        if rendered:
            parts.append(f"{field_name}={rendered}")
    body = "; ".join(parts)
    if body:
        return f"Server-projected {cap_id} structured output: {body}."
    return f"Server-projected {cap_id} structured output."


def _resolve_dotted_evidence_field(payload: Any, field: str) -> Any:
    """Resolve a dotted evidence field through nested mappings/lists.

    Mirrors the resolver semantics of ``validate_capability_output`` (Task 7)
    so the projection sees the same values the capability check sees.
    """

    if not isinstance(payload, dict):
        return None
    segments = field.split(".")
    value: Any = payload
    for index, segment in enumerate(segments):
        if isinstance(value, dict):
            if segment not in value:
                return None
            value = value[segment]
        elif isinstance(value, list):
            tail = ".".join(segments[index:])
            for item in value:
                if isinstance(item, dict):
                    resolved = _resolve_dotted_evidence_field(item, tail)
                    if resolved is not None:
                        return resolved
            return None
        else:
            return None
    return value


def _render_structured_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and _finite_number(value):
        return str(value)
    if isinstance(value, str):
        text = " ".join(value.split())
        return text[:60]
    if isinstance(value, list):
        if not value:
            return ""
        if isinstance(value[0], dict):
            return f"list<{len(value)}>"
        rendered = [_render_structured_value(item) for item in value[:3]]
        return ",".join(item for item in rendered if item)
    return ""


_METRIC_CONTEXT_FIELDS = (
    "metric",
    "target",
    "feature",
    "dimension",
    "column",
    "label",
    "name",
    "term",
)


def _structured_metric_identity(
    *,
    declared_field: str,
    item: dict[str, Any] | None,
) -> tuple[str, str, list[str]] | None:
    tail = declared_field.rsplit(".", 1)[-1].replace("_", " ").strip()
    if item is None:
        label = declared_field.replace(".", " ").replace("_", " ").strip()
        return declared_field, label, [label]

    context: list[str] = []
    metric_context: list[str] = []
    variable_context: list[str] = []
    if isinstance(item, dict):
        variables = item.get("variables")
        if isinstance(variables, list):
            variable_context = [
                _text(value) for value in variables if _text(value)
            ]
            context.extend(variable_context)
            metric_context.extend(variable_context)
        else:
            for key in ("var1", "var2"):
                value = _text(item.get(key))
                if value:
                    variable_context.append(value)
                    context.append(value)
                    metric_context.append(f"{key}={value}")
        for key in _METRIC_CONTEXT_FIELDS:
            value = _text(item.get(key))
            if value:
                context.append(value)
                metric_context.append(f"{key}={value}")
        segment_value = item.get("value")
        if isinstance(segment_value, str) and _text(segment_value):
            context.append(_text(segment_value))
            metric_context.append(f"value={_text(segment_value)}")
    if not context:
        return None
    metric_key = declared_field
    metric_key += "::" + "|".join(metric_context)
    label = " ".join([*context, tail]).strip()
    aliases = [label]
    if len(variable_context) == 2:
        aliases.append(" ".join([
            variable_context[1],
            variable_context[0],
            *context[len(variable_context):],
            tail,
        ]).strip())
    return metric_key, label, list(dict.fromkeys(aliases))


def _attach_projected_measurement_identity(
    measurement: dict[str, Any],
    *,
    declared_field: str,
    item: dict[str, Any] | None,
    computation_ref: dict[str, Any],
    binding: StepBindingResult,
    plan: dict[str, Any],
    plan_id: str,
    allowed_claim_class: str,
) -> None:
    projected_unit = (
        _text(item.get("unit"))
        if isinstance(item, dict)
        else ""
    )
    if projected_unit:
        measurement["unit"] = projected_unit
    metric_identity = _structured_metric_identity(
        declared_field=declared_field,
        item=item,
    )
    if metric_identity is None:
        projected_definition = (
            _text(item.get("definition"))
            if isinstance(item, dict)
            else ""
        )
        if projected_definition:
            measurement["definition"] = projected_definition
        measurement["identity_status"] = "metric_identity_missing"
        measurement["projection_origin"] = MEASUREMENT_PROJECTION_ORIGIN
        return
    metric_key, metric_label, metric_aliases = metric_identity
    identity = {
        "contract_version": MEASUREMENT_IDENTITY_CONTRACT_VERSION,
        "metric_key": metric_key,
        "metric_label": metric_label,
        "metric_aliases": metric_aliases,
        "claim_key": binding.claim_key,
        "computation_ref_id": computation_ref_key(computation_ref),
        "plan_id": plan_id,
        "plan_version": analysis_plan_semantic_digest(plan),
        "step_id": binding.step_id,
        "requirement_ids": sorted(binding.requirement_ids),
        "dataset_versions": sorted(
            computation_ref.get("dataset_versions") or []
        ),
        "time_scope": _text(measurement.get("time_scope")),
        "population_scope": _text(measurement.get("population_scope")),
        "value": measurement.get("value"),
        "unit": _text(measurement.get("unit")),
        "direction": _text(measurement.get("direction")),
        "allowed_claim_class": _text(allowed_claim_class),
    }
    identity["measurement_key"] = measurement_key_for(identity)
    measurement["identity"] = identity


def _projected_measurements_from_output(
    *,
    capability: dict[str, Any],
    output_data: dict[str, Any],
    method_label: str,
    computation_ref: dict[str, Any],
    binding: StepBindingResult,
    plan: dict[str, Any],
    plan_id: str,
    allowed_claim_class: str,
) -> list[dict[str, Any]]:
    """Build claim-neutral canonical measurements from structured output.

    Each structured numeric field contributes one measurement. ``pairs.x``
    style declarations contribute one measurement per list record so a
    multi-pair correlation result yields one measurement per pair without
    becoming a material claim. ``run_python`` is never upgraded, so this
    helper is never called for free-form python output.
    """

    base_limitation = ["Server-projected structured computation; no model-authored interpretation."]
    measurements: list[dict[str, Any]] = []
    for field in _capability_evidence_fields(capability):
        head = field.split(".", 1)[0]
        tail = field.split(".", 1)[1] if "." in field else ""
        if tail:
            container = output_data.get(head) if isinstance(output_data, dict) else None
            if isinstance(container, list):
                for item in container:
                    if not isinstance(item, dict):
                        continue
                    value = _resolve_dotted_evidence_field(item, tail)
                    if not _finite_number(value):
                        continue
                    measurement = _claim_neutral_measurement(
                        metric=field,
                        value=float(value),
                        method_label=method_label,
                        limitation=base_limitation,
                    )
                    _attach_projected_measurement_identity(
                        measurement,
                        declared_field=field,
                        item=item,
                        computation_ref=computation_ref,
                        binding=binding,
                        plan=plan,
                        plan_id=plan_id,
                        allowed_claim_class=allowed_claim_class,
                    )
                    measurements.append(measurement)
                continue
        value = _resolve_dotted_evidence_field(output_data, field)
        if _finite_number(value):
            measurement = _claim_neutral_measurement(
                metric=field,
                value=float(value),
                method_label=method_label,
                limitation=base_limitation,
            )
            _attach_projected_measurement_identity(
                measurement,
                declared_field=field,
                item=None,
                computation_ref=computation_ref,
                binding=binding,
                plan=plan,
                plan_id=plan_id,
                allowed_claim_class=allowed_claim_class,
            )
            measurements.append(measurement)
    if not measurements:
        measurements.append(_claim_neutral_measurement(
            metric="structured_computation",
            value=0.0,
            method_label=method_label,
            limitation=base_limitation,
        ))
    return measurements


def _claim_neutral_measurement(
    *,
    metric: str,
    value: float,
    method_label: str,
    limitation: list[str],
) -> dict[str, Any]:
    return {
        "metric": metric,
        "definition": "Server-projected structured computation field.",
        "value": value,
        "unit": "value",
        "direction": "",
        "grain": "structured_field",
        "population_scope": "as computed by tool",
        "time_scope": "as computed by tool",
        "method": method_label,
        "denominator": "not_applicable",
        "limitations": list(limitation),
    }


def _build_projected_record(
    *,
    computation_ref: dict[str, Any],
    binding: StepBindingResult,
    plan: dict[str, Any],
    capability: dict[str, Any] | None,
    dataset_contracts: list[dict[str, Any]],
    output_data: dict[str, Any],
    plan_id: str,
) -> dict[str, Any]:
    tool_name = _text(computation_ref.get("tool_name"))
    cap_id = _text((capability or {}).get("capability_id")) if isinstance(capability, dict) else ""
    method_label = ", ".join(item for item in (cap_id, tool_name) if item) or "server-bound computation"
    step = _step_for_id(plan, binding.step_id)
    step_dataset_name = ""
    step_dataset_inputs_raw = step.get("dataset_inputs") if isinstance(step, dict) else None
    if isinstance(step_dataset_inputs_raw, list) and step_dataset_inputs_raw:
        step_dataset_name = _text(step_dataset_inputs_raw[0])
    if not step_dataset_name:
        # Fall back to the first contract's dataset (only when contracts provided).
        if isinstance(dataset_contracts, list) and dataset_contracts:
            first = dataset_contracts[0]
            if isinstance(first, dict):
                step_dataset_name = _text(first.get("dataset"))

    dataset_contract_id = ""
    step_contract_ids = step.get("dataset_contract_ids") if isinstance(step, dict) else None
    if isinstance(step_contract_ids, list) and step_contract_ids:
        dataset_contract_id = _text(step_contract_ids[0])
    if not dataset_contract_id and isinstance(dataset_contracts, list):
        for contract in dataset_contracts:
            if isinstance(contract, dict) and _text(contract.get("dataset")) == step_dataset_name:
                dataset_contract_id = _text(
                    contract.get("id")
                    or contract.get("contract_id")
                    or contract.get("dataset_id")
                )
                if dataset_contract_id:
                    break

    requirement_ids = list(binding.requirement_ids)
    evidence_requirement = _evidence_requirement_name(plan, binding.step_id, requirement_ids)

    sample_size_value: Any = _resolve_sample_size(output_data)

    confidence = "medium"
    if isinstance(capability, dict):
        risk = _text(capability.get("risk_level"))
        if risk == "high":
            confidence = "low"
        elif risk == "low":
            confidence = "high"

    allowed_claim_class = (
        output_data.get("allowed_claim_class")
        if isinstance(output_data, dict)
        else None
    )
    if not _text(allowed_claim_class) and cap_id == "data.profile":
        allowed_claim_class = "descriptive"
    measurements = _projected_measurements_from_output(
        capability=capability if isinstance(capability, dict) else {},
        output_data=output_data,
        method_label=method_label,
        computation_ref=computation_ref,
        binding=binding,
        plan=plan,
        plan_id=plan_id,
        allowed_claim_class=_text(allowed_claim_class),
    )
    result_summary = _claim_neutral_summary(
        capability=capability if isinstance(capability, dict) else {},
        output_data=output_data,
    )
    semantic_fields = _project_requirement_semantics(
        capability_id=cap_id,
        output_data=output_data,
    )

    record: dict[str, Any] = {
        "plan_id": plan_id,
        "step_id": binding.step_id,
        "claim_key": binding.claim_key,
        "claim": (
            f"Server-projected structured computation evidence for "
            f"{binding.claim_key} from {method_label}."
        ),
        "dataset": step_dataset_name,
        "dataset_contract_id": dataset_contract_id,
        "method": method_label,
        "tool_calls": [
            {
                "name": tool_name,
                "capability_id": cap_id,
                "tool_call_id": _text(computation_ref.get("tool_call_id")),
            }
        ],
        "result_summary": result_summary,
        "limitations": ["Server-projected from structured computation; no model-authored interpretation."],
        "time_scope": "as computed by tool",
        "calculation_method": method_label,
        "method_detail": "Server-bound computation output with verified provenance.",
        "confidence": confidence,
        "evidence_requirement": evidence_requirement or binding.claim_key,
        "measurements": measurements,
        "contract_version": EVIDENCE_RECORD_CONTRACT_VERSION,
        "source_tool_call_ids": [_text(computation_ref.get("tool_call_id"))],
        "requirement_ids": requirement_ids,
        "dataset_versions": list(computation_ref.get("dataset_versions") or []),
        "computation_refs": [dict(computation_ref)],
        "provenance_status": "bound",
        "verification_level": _text(computation_ref.get("verification_level")) or "structured_checked",
        **semantic_fields,
    }
    if sample_size_value is not None:
        record["sample_size"] = sample_size_value
    if _text(allowed_claim_class):
        record["allowed_claim_class"] = _text(allowed_claim_class)
    return record


def _project_requirement_semantics(
    *,
    capability_id: str,
    output_data: dict[str, Any],
) -> dict[str, Any]:
    """Map trusted structured outputs onto canonical requirement fields."""

    semantics: dict[str, Any] = {}
    limitations = output_data.get("limitations")
    if isinstance(limitations, list) and any(_text(item) for item in limitations):
        semantics["limitations"] = [
            _text(item) for item in limitations if _text(item)
        ]

    if capability_id == "data.profile":
        grain = _text(output_data.get("grain"))
        if grain:
            semantics["grain_definition"] = {
                "grain": grain,
                "detail": _text(output_data.get("grain_hint")),
            }
        columns = output_data.get("columns")
        if isinstance(columns, list):
            semantics["missingness_assessment"] = {
                "status": "assessed",
                "columns": [
                    _text(item.get("name"))
                    for item in columns
                    if isinstance(item, dict)
                    and _text(item.get("name"))
                ],
            }
        return semantics

    if capability_id == "analysis.correlation":
        pairs = output_data.get("pairs")
        if isinstance(pairs, list) and pairs:
            semantics["univariate_association"] = {
                "status": "available",
                "measurement_fields": ["pairs.correlation"],
                "pairs": [
                    {
                        "var1": _text(item.get("var1")),
                        "var2": _text(item.get("var2")),
                    }
                    for item in pairs
                    if isinstance(item, dict)
                    and _text(item.get("var1"))
                    and _text(item.get("var2"))
                ],
            }
            if any(
                _finite_number(item.get("effective_sample_size"))
                for item in pairs
                if isinstance(item, dict)
            ):
                semantics["effective_sample_size"] = {
                    "status": "available",
                    "measurement_fields": ["pairs.effective_sample_size"],
                }
        assumptions = [
            {
                key: _text(item.get(key))
                for key in ("name", "status", "reason", "method")
                if _text(item.get(key))
            }
            for item in list(output_data.get("assumptions") or [])
            if isinstance(item, dict)
            and _text(item.get("name"))
            and _text(item.get("status"))
        ]
        if assumptions:
            semantics["assumption_checks"] = [
                item for item in assumptions if item
            ]
        return semantics

    if capability_id == "analysis.factor_relationship":
        assumptions = [
            item
            for item in list(output_data.get("assumptions") or [])
            if isinstance(item, dict)
        ]
        if assumptions:
            semantics["assumption_checks"] = assumptions
        effective_n = output_data.get("effective_sample_size")
        if _finite_number(effective_n):
            semantics["effective_sample_size"] = {
                "status": "available",
                "measurement_fields": ["effective_sample_size"],
            }
            semantics["grain_definition"] = {
                "grain": "complete_case_model_row",
            }
        target = _text(output_data.get("target_col"))
        if target:
            semantics["target_definition"] = {"target": target}
        semantics["missingness_assessment"] = {
            "status": "assessed",
            "features_requested": list(output_data.get("features_requested") or []),
            "features_included": list(output_data.get("features_included") or []),
            "excluded_features": list(output_data.get("excluded_features") or []),
        }
        coefficients = output_data.get("coefficients")
        if isinstance(coefficients, list) and coefficients:
            terms = [
                _text(item.get("term"))
                for item in coefficients
                if isinstance(item, dict) and _text(item.get("term"))
            ]
            semantics["effect_size_or_predictive_contribution"] = {
                "status": "available",
                "terms": terms,
                "measurement_fields": [
                    "coefficients.estimate",
                    "coefficients.confidence_interval",
                    "coefficients.p_value",
                    "coefficients.adjusted_p_value",
                ],
            }
            semantics["multivariable_adjustment"] = {
                "method": _text(output_data.get("method")),
                "covariance": _text(output_data.get("covariance")),
                "terms": terms,
                "measurement_fields": ["coefficients.estimate"],
            }
        correction = _text(output_data.get("correction_method"))
        if correction:
            semantics["multiplicity_control"] = {
                "method": correction,
                "measurement_fields": ["coefficients.adjusted_p_value"],
            }
        collinearity = output_data.get("collinearity")
        if isinstance(collinearity, dict) and collinearity:
            semantics["collinearity_assessment"] = {
                key: value
                for key, value in {
                    "status": _text(collinearity.get("status")),
                    "method": _text(collinearity.get("method")),
                    "high_vif_terms": [
                        _text(item)
                        for item in collinearity.get("high_vif_terms") or []
                        if _text(item)
                    ],
                }.items()
                if value != "" and value != []
            }
        time_dependence = output_data.get("time_dependence")
        if isinstance(time_dependence, dict) and time_dependence:
            semantics["time_dependence_assessment"] = {
                key: value
                for key, value in {
                    "status": _text(time_dependence.get("status")),
                    "reason": _text(time_dependence.get("reason")),
                    "covariance": _text(time_dependence.get("covariance")),
                    "ordered_time_column": _text(
                        time_dependence.get("ordered_time_column")
                    ),
                }.items()
                if value
            }
        semantics["stability_or_validation"] = {
            "status": (
                "available"
                if _finite_number(output_data.get("r_squared"))
                else "not_reported"
            ),
            "method": _text(output_data.get("method")),
        }
        if semantics.get("limitations"):
            semantics["limitations_and_alternatives"] = list(
                semantics["limitations"]
            )
        return semantics

    if capability_id == "analysis.dimension_decomposition":
        decomposition = [
            item
            for item in list(output_data.get("decomposition") or [])
            if isinstance(item, dict) and _text(item.get("value"))
        ]
        dimension = _text(output_data.get("dimension"))
        if decomposition and dimension:
            labels = [_text(item.get("value")) for item in decomposition]
            semantics["segment_coverage"] = {
                "status": "observed",
                "dimension": dimension,
                "segments": labels,
                "measurement_fields": ["decomposition.contribution"],
            }
            candidates = [
                _text(item)
                for item in [
                    *(output_data.get("top_positive") or []),
                    *(output_data.get("top_negative") or []),
                ]
                if _text(item)
            ]
            if candidates:
                semantics["opportunity_candidates"] = {
                    "status": "hypothesis_only",
                    "claim_class": "exploratory",
                    "basis": "observed_dimension_contribution",
                    "dimension": dimension,
                    "candidates": list(dict.fromkeys(candidates)),
                    "measurement_fields": ["decomposition.contribution"],
                    "causal_authorization": "none",
                }
    return semantics


def _resolve_sample_size(output_data: Any) -> float:
    """Best-effort extraction of a sample size from structured output.

    The canonical schema requires a non-empty ``sample_size`` field. Tools
    that expose ``effective_sample_size.total`` (top-level or nested in a
    pairs list) supply the value directly; otherwise we fall back to ``0``
    so the validator accepts the record without manufacturing a fabricated
    number. ``0`` is the explicit "no claimed sample size" sentinel.
    """

    if isinstance(output_data, dict):
        ess = output_data.get("effective_sample_size")
        if isinstance(ess, dict) and _finite_number(ess.get("total")):
            return float(ess["total"])
        pairs = output_data.get("pairs")
        if isinstance(pairs, list):
            for pair in pairs:
                if isinstance(pair, dict) and _finite_number(pair.get("effective_sample_size")):
                    return float(pair["effective_sample_size"])
    return 0.0


def project_structured_computation_evidence(
    *,
    computation_ref: dict[str, Any],
    binding: StepBindingResult,
    plan: dict[str, Any],
    capability: dict[str, Any] | None,
    dataset_contracts: list[dict[str, Any]],
    current_session_id: str,
    current_turn_id: str,
    sessions_root: Path,
) -> EvidenceProjectionResult:
    """Project an eligible structured computation into ``evidence_record.v2``.

    The early-return order is fixed by the Task 9 contract:

    1. ``computation_failed`` when the ref's success flag is False;
    2. ``ambiguous_analysis_step`` (or the binding's error code) when the
       step binding did not succeed;
    3. ``unstructured_tool`` for ``run_python`` or capability-less tools
       (``run_python`` is never upgraded);
    4. stale identity/revision reasons when the ref does not match the current
       session, turn, semantic plan, or step;
    5. ``invalid_dataset_versions`` or ``stale_dataset_version`` when the
       ref's exact dataset-version scope is malformed or no longer current;
    6. ``invalid_requirement_ids`` when the binding contains malformed
       requirement identity;
    7. ``missing_declared_field`` when ``validate_capability_output`` reports
       missing declared evidence fields in the real tool output;
    8. ``missing_claim_identity`` when the binding does not surface a claim
       key and at least one canonical requirement id;
    9. the validated ``evidence_record.v2`` record otherwise.

    The success branch builds a CLAIM-NEUTRAL summary from the declared
    structured fields, sets the maximum allowed claim class from capability
    output when present, and calls the existing ``validate_evidence_record``
    before returning. It never parses model prose into evidence.
    """

    if not isinstance(computation_ref, dict):
        return EvidenceProjectionResult(
            projected=False, reason="computation_failed",
            diagnostics=({"error_type": "invalid_ref"},),
        )
    if not bool(computation_ref.get("success")):
        return EvidenceProjectionResult(projected=False, reason="computation_failed")
    if not getattr(binding, "ok", False):
        return EvidenceProjectionResult(
            projected=False,
            reason=_text(getattr(binding, "error_type", "")) or "ambiguous_analysis_step",
        )
    tool_name = _text(computation_ref.get("tool_name"))
    if tool_name == "run_python":
        return EvidenceProjectionResult(projected=False, reason="unstructured_tool")
    declared_fields = _capability_evidence_fields(capability)
    if not declared_fields or not _text(
        (capability or {}).get("capability_id") if isinstance(capability, dict) else ""
    ):
        return EvidenceProjectionResult(projected=False, reason="unstructured_tool")

    ref_session = _text(computation_ref.get("session_id"))
    if ref_session != _text(current_session_id):
        return EvidenceProjectionResult(projected=False, reason="stale_session_identity")
    ref_turn = _text(computation_ref.get("turn_id"))
    if ref_turn != _text(current_turn_id):
        return EvidenceProjectionResult(projected=False, reason="stale_turn_identity")
    plan_id = _text(plan.get("id")) if isinstance(plan, dict) else ""
    ref_plan = _text(computation_ref.get("plan_id"))
    if not plan_id or ref_plan != plan_id:
        return EvidenceProjectionResult(projected=False, reason="stale_plan_identity")
    current_plan_digest = analysis_plan_semantic_digest(plan)
    if computation_ref.get("plan_digest") != current_plan_digest:
        return EvidenceProjectionResult(
            projected=False,
            reason="stale_plan_revision",
            diagnostics=({
                "ref_plan_digest": computation_ref.get("plan_digest"),
                "current_plan_digest": current_plan_digest,
            },),
        )
    ref_step = _text(computation_ref.get("step_id"))
    binding_step = _text(getattr(binding, "step_id", ""))
    if not binding_step or ref_step != binding_step:
        return EvidenceProjectionResult(projected=False, reason="stale_step_identity")
    current_step = _step_for_id(plan, binding_step)
    current_step_digest = analysis_step_semantic_digest(current_step)
    if computation_ref.get("step_digest") != current_step_digest:
        return EvidenceProjectionResult(
            projected=False,
            reason="stale_plan_revision",
            diagnostics=({
                "ref_step_digest": computation_ref.get("step_digest"),
                "current_step_digest": current_step_digest,
            },),
        )

    raw_versions = computation_ref.get("dataset_versions")
    if (
        not isinstance(raw_versions, list)
        or not raw_versions
        or any(
            not isinstance(item, str) or not item.strip()
            for item in raw_versions
        )
        or len(raw_versions) != len(set(raw_versions))
    ):
        return EvidenceProjectionResult(
            projected=False,
            reason="invalid_dataset_versions",
        )
    step_datasets = _step_dataset_inputs(plan, binding_step)
    active_versions = _active_dataset_versions_for_step(dataset_contracts, step_datasets)
    if not active_versions and isinstance(dataset_contracts, list):
        # Fall back to ALL active contracts when the plan step is silent.
        active_versions = _active_dataset_versions_for_step(dataset_contracts, [])
    ref_versions = set(raw_versions)
    if active_versions and ref_versions != active_versions:
        return EvidenceProjectionResult(
            projected=False,
            reason="stale_dataset_version",
            diagnostics=(
                {"ref_versions": sorted(ref_versions), "active_versions": sorted(active_versions)},
            ),
        )

    try:
        output = hydrate_computation_ref(
            computation_ref,
            sessions_root=Path(sessions_root),
            current_session_id=current_session_id,
        )
    except Exception as exc:
        return EvidenceProjectionResult(
            projected=False,
            reason="computation_artifact_unavailable",
            diagnostics=({"error": str(exc)},),
        )
    if not isinstance(output, dict):
        return EvidenceProjectionResult(
            projected=False,
            reason="computation_artifact_unavailable",
        )
    output_data = output.get("data")
    if not isinstance(output_data, dict):
        output_data = {}
    missing_fields = _capability_check_missing_fields(capability, output_data)
    if missing_fields:
        return EvidenceProjectionResult(
            projected=False,
            reason="missing_declared_field",
            diagnostics=({"missing": list(missing_fields)},),
        )

    binding_claim_raw = getattr(binding, "claim_key", "")
    binding_claim = (
        binding_claim_raw.strip()
        if isinstance(binding_claim_raw, str)
        else ""
    )
    binding_requirements = getattr(binding, "requirement_ids", ())
    if (
        not isinstance(binding_requirements, (list, tuple))
        or not binding_requirements
        or any(
            not isinstance(item, str) or not item.strip()
            for item in binding_requirements
        )
        or len(binding_requirements) != len(set(binding_requirements))
    ):
        return EvidenceProjectionResult(
            projected=False,
            reason="invalid_requirement_ids",
        )
    if not binding_claim or not binding_requirements:
        return EvidenceProjectionResult(
            projected=False, reason="missing_claim_identity",
        )

    record = _build_projected_record(
        computation_ref=computation_ref,
        binding=binding,
        plan=plan,
        capability=capability,
        dataset_contracts=dataset_contracts,
        output_data=output_data,
        plan_id=plan_id,
    )
    validation = validate_evidence_record(
        record,
        current_plan_id=plan_id,
        require_measurement_identity=True,
    )
    if not validation.ok:
        return EvidenceProjectionResult(
            projected=False,
            reason="evidence_validation_failed",
            diagnostics=(
                {
                    "error_type": validation.error_type,
                    "message": validation.message,
                    "details": dict(validation.details),
                },
            ),
        )
    return EvidenceProjectionResult(projected=True, record=validation.record)


def _capability_check_missing_fields(
    capability: dict[str, Any] | None, payload: dict[str, Any]
) -> list[str]:
    """Delegate to the shared capability-output validator (Task 7).

    Reusing the existing validator avoids forking the field-presence
    contract between capability truthfulness and evidence projection.
    """

    from data_agent.tools.registry import validate_capability_output

    return list(validate_capability_output(capability, payload))


def _format_measurement_value(measurement: dict[str, Any]) -> str:
    value = measurement.get("value")
    unit = _text(measurement.get("unit"))
    if _finite_number(value):
        rendered = f"{float(value):g}"
    else:
        rendered = _text(value)[:24]
    if unit and unit not in {"value", "unitless"}:
        return f"{rendered} {unit}".strip()
    return rendered


def _format_unbound_measurement_for_catalog(measurement: dict[str, Any]) -> str:
    metric = _text(measurement.get("metric"))
    rendered = _format_measurement_value(measurement)
    return f"{metric}={rendered}" if metric else rendered


def build_bounded_evidence_catalog(
    evidence_records: Sequence[dict[str, Any]],
    *,
    max_records: int = 12,
    max_chars: int = 6000,
) -> str:
    """Build a bounded, deterministic catalog of current-plan evidence.

    Records are sorted by ``(step_order, evidence_id)`` and rendered as one
    compact line per measurement entry. Duplicate ``(evidence_id,
    measurement_key)`` references are emitted once, in first-seen order.
    ``max_records`` bounds emitted entries and ``max_chars`` bounds the whole
    catalog, including its header. An empty catalog still returns the
    canonical header so the synthesis policy always injects a catalog block
    (and never triggers a tool ritual to manufacture evidence).
    """

    if not isinstance(evidence_records, list):
        evidence_records = list(evidence_records or [])

    def _sort_key(record: dict[str, Any]) -> tuple[Any, str]:
        order = record.get("step_order")
        if isinstance(order, bool) or not isinstance(order, (int, float)):
            order = 0
        return (order, _text(record.get("id")))

    def _format_line(
        record: dict[str, Any],
    ) -> list[tuple[tuple[str, str] | None, str]]:
        claim_class = (
            _text(record.get("allowed_claim_class"))
            or _text(record.get("claim_class"))
            or _text(record.get("claim_type"))
        )
        dataset_versions = record.get("dataset_versions")
        if isinstance(dataset_versions, list):
            version_text = ",".join(
                _text(item) for item in dataset_versions if _text(item)
            )
        elif isinstance(record.get("dataset_versions"), str):
            version_text = _text(record.get("dataset_versions"))
        else:
            version_text = _text(record.get("dataset_id"))
        limitations = record.get("limitations")
        if isinstance(limitations, list):
            limitation_text = "; ".join(_text(item) for item in limitations if _text(item))
        else:
            limitation_text = _text(limitations)
        record_id = _text(record.get("id"))
        common_parts = [f"id={record_id}"]
        if claim_class:
            common_parts.append(f"claim_class={claim_class}")
        if version_text:
            common_parts.append(f"dataset_versions={version_text}")
        if _text(record.get("verification_level")):
            common_parts.append(
                f"verification_level={_text(record.get('verification_level'))}"
            )
        if limitation_text:
            common_parts.append(f"limitations={limitation_text}")

        measurements = record.get("measurements")
        if not isinstance(measurements, list) or not measurements:
            return [(None, "- " + " | ".join([
                *common_parts,
                f"claim_key={_text(record.get('claim_key'))}",
            ]))]

        catalog_lines: list[tuple[tuple[str, str] | None, str]] = []
        for measurement in measurements:
            if not isinstance(measurement, dict):
                continue
            identity = measurement.get("identity")
            try:
                validation = validate_measurement_identity(identity)
            except Exception:
                validation = None
            if record_id and validation is not None and validation.ok:
                validated_identity = validation.record
                measurement_key = _text(validated_identity.get("measurement_key"))
                parts = [
                    *common_parts,
                    f"measurement_key={measurement_key}",
                    f"metric_key={_text(validated_identity.get('metric_key'))}",
                    f"metric_label={_text(validated_identity.get('metric_label'))}",
                    f"claim_key={_text(validated_identity.get('claim_key'))}",
                    f"value={_format_measurement_value(measurement)}",
                ]
                reference: tuple[str, str] | None = (record_id, measurement_key)
            else:
                parts = [
                    *common_parts,
                    f"claim_key={_text(record.get('claim_key'))}",
                    "unbound_measurement="
                    f"{_format_unbound_measurement_for_catalog(measurement)}",
                ]
                reference = None
            catalog_lines.append((reference, "- " + " | ".join(parts)))
        return catalog_lines or [(None, "- " + " | ".join([
            *common_parts,
            f"claim_key={_text(record.get('claim_key'))}",
        ]))]

    sorted_records = sorted(evidence_records, key=_sort_key)
    candidates: list[str] = []
    seen_references: set[tuple[str, str]] = set()
    for record in sorted_records:
        if not isinstance(record, dict):
            continue
        for reference, line in _format_line(record):
            if reference is not None:
                if reference in seen_references:
                    continue
                seen_references.add(reference)
            candidates.append(line)

    header = (
        f"可用证据测量：{len(candidates)} 条。请基于现有计算诊断说明局限，"
        "不要重新运行工具来制造证据。"
    )
    limit = max(0, int(max_chars))
    if len(header) > limit:
        return header[:limit]

    lines: list[str] = [header]
    used_chars = len(header)
    max_entries = max(0, int(max_records))
    for line in candidates[:max_entries]:
        if used_chars + 1 + len(line) > limit:
            break
        lines.append(line)
        used_chars += 1 + len(line)
    return "\n".join(lines)
