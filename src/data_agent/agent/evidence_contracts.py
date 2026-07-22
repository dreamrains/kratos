from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    return EvidenceValidationResult(True, record=normalized)


def validate_evidence_record(
    record: Any,
    *,
    current_plan_id: str | None = None,
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
    for index, measurement in enumerate(measurements):
        measurement_validation = validate_measurement(measurement, index=index)
        if not measurement_validation.ok:
            return measurement_validation
        normalized_measurements.append(measurement_validation.record)

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
