"""Data Agent V2 fact-driven runtime contracts.

The V2 package is intentionally isolated from the legacy analysis state,
requirements, evidence, task, and publication authorities.  Slice 1 grows
from these contracts through vertical, end-to-end integrations.
"""

from data_agent.v2.answer import compile_answer
from data_agent.v2.projection import project_run

__all__ = ["compile_answer", "project_run"]
