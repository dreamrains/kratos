from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KnowledgeStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class KnowledgeSource(str, Enum):
    USER = "user"
    MEMORY_PROMOTION = "memory_promotion"
    IMPORT = "import"


class MemoryStatus(str, Enum):
    OBSERVED = "observed"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    DOMAIN_FACT = "domain_fact"
    WORKFLOW_PATTERN = "workflow_pattern"
    CORRECTION = "correction"
    TOOL_USAGE = "tool_usage"
    SKILL_CANDIDATE = "skill_candidate"


class EvidenceKind(str, Enum):
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    ANALYSIS_RESULT = "analysis_result"
    USER_CORRECTION = "user_correction"
    REPORT = "report"


class ConflictSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    REVIEW = "review"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class KnowledgeItem:
    id: str
    title: str
    domain: str
    path: str
    summary: str
    status: KnowledgeStatus
    tags: list[str] = field(default_factory=list)
    source: KnowledgeSource = KnowledgeSource.USER
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    deprecated_at: str = ""
    supersedes: str = ""
    superseded_by: str = ""
    content: str = ""


@dataclass(frozen=True)
class MemoryItem:
    id: str
    type: MemoryType
    text: str
    summary: str
    status: MemoryStatus
    confidence: float
    source_session_id: str = ""
    source_message_ids: list[str] = field(default_factory=list)
    source_tool_call_ids: list[str] = field(default_factory=list)
    project_id: str = ""
    domain: str = "general"
    tags: list[str] = field(default_factory=list)
    last_used_at: str = ""
    hit_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    promotion_target: str = "none"


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    session_id: str
    project_id: str
    kind: EvidenceKind
    content_ref: str
    summary: str
    created_at: str
    tags: list[str] = field(default_factory=list)
    embedding_ref: str = ""
    content: str = ""


@dataclass(frozen=True)
class ConflictRecord:
    severity: ConflictSeverity
    claim: str
    conflicting_claim: str
    sources: list[str]
    impact: str


@dataclass
class RetrievedContext:
    knowledge_items: list[KnowledgeItem] = field(default_factory=list)
    memory_items: list[MemoryItem] = field(default_factory=list)
    evidence_items: list[EvidenceRecord] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
