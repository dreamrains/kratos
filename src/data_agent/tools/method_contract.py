"""Shared, serialisable contract for deterministic statistical methods.

This module deliberately owns no session, planner or presentation state.  It
only gives existing tools one vocabulary for provenance, method status and the
claim boundary that downstream evidence projection can rely on.
"""

from __future__ import annotations

from typing import Any

from data_agent.session.workspace import workspace


def method_receipt(
    name: str,
    *,
    method: str,
    status: str,
    effective_n: int,
    parameters: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
    claim_ceiling: str = "descriptive",
    reason_code: str = "",
) -> dict[str, Any]:
    """Return the common, JSON-safe portion of a statistical tool result."""
    identity = workspace.get_data_identity(name)
    return {
        "method_contract": "analysis_method_result.v1",
        "method": method,
        "status": status,
        "reason_code": reason_code,
        "data_identity": identity,
        "effective_n": int(effective_n),
        "parameters": parameters or {},
        "claim_ceiling": claim_ceiling,
        "limitations": limitations or [],
    }
