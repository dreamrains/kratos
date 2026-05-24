from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from data_agent.config import get_config
from data_agent.knowledge.evidence import EvidenceStore
from data_agent.knowledge.memory import MemoryStore
from data_agent.knowledge.models import EvidenceRecord, MemoryType
from data_agent.knowledge.sqlite_store import rows_to_dicts


MEMORY_MARKERS = ("请记住", "记住", "以后默认", "下次", "默认", "remember", "default", "next time")
CORRECTION_MARKERS = ("纠正", "更正", "不是", "应该是", "修正", "correction", "correct")
METRIC_MARKERS = ("口径", "定义", "公式", "指标", "=", "等于")
STRONG_METRIC_MARKERS = ("口径", "定义", "公式", "指标")
KNOWN_DOMAINS = {"ecommerce", "game", "finance"}


@dataclass(frozen=True)
class CandidateDraft:
    text: str
    summary: str
    memory_type: MemoryType
    confidence: float
    domain: str
    tags: list[str]
    reason: str
    source_evidence_ids: list[str]
    needs_review: bool = False
    review_note: str = ""
    dedup_key: str = ""


@dataclass
class CandidateExtractionResult:
    scanned: int = 0
    created: int = 0
    skipped: int = 0
    candidates: list[str] = field(default_factory=list)


class MemoryCandidateExtractor:
    def __init__(self, root: Path | None = None, sessions_dir: Path | None = None):
        self.root = root or get_config().knowledge_dir
        self.evidence = EvidenceStore(self.root, sessions_dir=sessions_dir)
        self.memory = MemoryStore(self.root)

    def extract_for_session(self, session_id: str, max_candidates: int = 10) -> CandidateExtractionResult:
        records = self._records_for_session(session_id)
        result = CandidateExtractionResult(scanned=len(records))
        for record in records:
            for draft in self._drafts_from_record(record):
                if result.created >= max_candidates:
                    result.skipped += 1
                    continue
                if self.memory.get_by_dedup_key(draft.dedup_key):
                    result.skipped += 1
                    continue
                item = self.memory.create_candidate(
                    text=draft.text,
                    summary=draft.summary,
                    memory_type=draft.memory_type,
                    confidence=draft.confidence,
                    source_session_id=record.session_id,
                    project_id=record.project_id,
                    domain=draft.domain,
                    tags=draft.tags,
                    reason=draft.reason,
                    source_evidence_ids=draft.source_evidence_ids,
                    needs_review=draft.needs_review,
                    review_note=draft.review_note,
                    dedup_key=draft.dedup_key,
                )
                result.created += 1
                result.candidates.append(item.id)
        return result

    def _records_for_session(self, session_id: str) -> list[EvidenceRecord]:
        with self.evidence.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM evidence_records
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        return [self.evidence._record_from_row(row) for row in rows_to_dicts(rows)]

    def _drafts_from_record(self, record: EvidenceRecord) -> list[CandidateDraft]:
        if not self._is_user_record(record):
            return []

        text = (record.content or record.summary).strip()
        if not text:
            return []

        lowered = text.lower()
        has_memory = self._contains_marker(lowered, MEMORY_MARKERS)
        has_correction = self._contains_marker(lowered, CORRECTION_MARKERS)
        has_strong_metric = self._contains_marker(lowered, STRONG_METRIC_MARKERS)
        has_metric_operator = self._contains_marker(lowered, ("=", "等于"))
        has_metric = has_strong_metric or (has_metric_operator and (has_memory or has_correction))
        has_workflow = self._has_workflow_sequence(text)
        if not any((has_memory, has_correction, has_metric, has_workflow)):
            return []

        domain = self._domain_from_project_id(record.project_id)
        memory_type = MemoryType.PREFERENCE
        reason = "User expressed a memory or default preference."
        needs_review = False
        review_note = ""
        confidence = 0.7

        if has_correction:
            memory_type = MemoryType.CORRECTION
            reason = "User correction indicates a fact that should be reviewed."
            needs_review = True
            review_note = "Candidate came from correction-like language; review before confirmation."
            confidence = 0.75
        elif has_metric:
            memory_type = MemoryType.DOMAIN_FACT
            reason = "User stated an explicit metric, definition, formula, or indicator rule."
            confidence = 0.8
        elif has_workflow:
            memory_type = MemoryType.WORKFLOW_PATTERN
            reason = "User described a repeated workflow sequence."
            confidence = 0.75

        dedup_key = self._dedup_key(memory_type, domain, text)
        return [
            CandidateDraft(
                text=text,
                summary=self._summary(text),
                memory_type=memory_type,
                confidence=confidence,
                domain=domain,
                tags=["memory_candidate"],
                reason=reason,
                source_evidence_ids=[record.id],
                needs_review=needs_review,
                review_note=review_note,
                dedup_key=dedup_key,
            )
        ]

    def _dedup_key(self, memory_type: MemoryType, domain: str, text: str) -> str:
        domain_value = domain or "general"
        normalized = re.sub(r"\s+", "", text.lower())
        payload = f"{memory_type.value}\n{domain_value}\n{normalized}"
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
        return f"{memory_type.value}:{domain_value}:{digest}"

    def _contains_marker(self, text: str, markers: tuple[str, ...]) -> bool:
        return any(marker.lower() in text for marker in markers)

    def _is_user_record(self, record: EvidenceRecord) -> bool:
        return "user" in {tag.lower() for tag in record.tags}

    def _domain_from_project_id(self, project_id: str) -> str:
        candidate = project_id.strip().lower()
        if candidate in KNOWN_DOMAINS:
            return candidate
        return "general"

    def _has_workflow_sequence(self, text: str) -> bool:
        return re.search(r"先.+再", text) is not None or re.search(r"\bfirst\b.+\bthen\b", text.lower()) is not None

    def _summary(self, text: str) -> str:
        return text[:120]
