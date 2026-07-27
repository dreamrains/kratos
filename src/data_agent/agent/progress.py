"""Safe live analysis-progress narration.

The analysis-candidate final answer is buffered until audit (Task 10) so the
user sees nothing live while tools run. To keep the user oriented, the agent
emits non-conclusion ``analysis_progress`` events describing *what the agent is
doing* — never what it has found. Labels are server-authored from a closed
vocabulary; arbitrary model text is rejected and numeric/claim fields
(``value``, ``p_value``, ``ranking``, ``claim``, ``reasoning``) can never appear
on the wire.

This module is the single source of truth for the vocabulary; the loop, the
chat SSE mapping, and the browser client all consume ``AnalysisProgressEvent``
instances produced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# Closed vocabulary of progress codes → Chinese narrative labels. The label is
# the *only* human-visible text on the wire — it is authored here, never by the
# model. Add a code here before emitting it from the loop.
PROGRESS_LABELS: dict[str, str] = {
    "analysis_plan_ready": "分析方案已准备",
    "analysis_step_started": "正在执行分析步骤",
    "tool_started": "正在运行分析工具",
    "tool_succeeded": "分析步骤已完成",
    "tool_recovery": "正在按约定尝试恢复",
    "completion_evaluated": "正在整理可支持的结论",
    "audit_started": "正在校验最终结论",
}

# Allowlisted ``code``/``step_id`` pairs that override the default
# ``analysis_step_started`` label with a more specific Chinese narration. Maps
# canonical analysis-step identifiers to human narration. The model cannot
# introduce new entries here — only steps the server knows about get a
# specific label, everything else falls back to the generic default.
STEP_LABELS: dict[str, str] = {
    "step_relationship": "正在评估变量关系",
    "step_grain_missingness": "正在检查颗粒度与缺失",
    "step_univariate": "正在执行单变量分析",
    "step_multivariable": "正在尝试多变量方法",
    "step_limitations": "正在整理局限说明",
}

_VALID_STATUSES = frozenset({"pending", "running", "completed", "limited"})


@dataclass(frozen=True)
class AnalysisProgressEvent:
    """A server-authored, non-conclusion progress narration event.

    Only identity/phase fields are carried — no values, p-values, rankings,
    claims, or reasoning. ``to_dict()`` is what the loop yields, the chat
    blueprint projects, and the browser renders.
    """

    code: str
    label: str
    status: Literal["pending", "running", "completed", "limited"]
    step_id: str = ""
    phase: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "type": "analysis_progress",
            "code": self.code,
            "label": self.label,
            "status": self.status,
            "step_id": self.step_id,
            "phase": self.phase,
        }


def build_analysis_progress(
    *,
    code: str,
    step_id: str = "",
    status: Literal["pending", "running", "completed", "limited"] = "running",
    phase: str = "",
) -> AnalysisProgressEvent:
    """Build a progress event from a closed vocabulary.

    Rejects unknown codes and statuses. The label is always chosen from server
    templates — arbitrary model text can never reach the payload. For
    ``analysis_step_started`` the optional ``step_id`` selects a more specific
    allowlisted label; unknown step IDs fall back to the generic default.
    """

    if code not in PROGRESS_LABELS:
        raise ValueError(f"unknown analysis_progress code: {code!r}")
    if status not in _VALID_STATUSES:
        raise ValueError(f"unknown analysis_progress status: {status!r}")
    label = PROGRESS_LABELS[code]
    if code == "analysis_step_started" and step_id in STEP_LABELS:
        label = STEP_LABELS[step_id]
    return AnalysisProgressEvent(
        code=code,
        label=label,
        status=status,
        step_id=step_id or "",
        phase=phase or "",
    )
