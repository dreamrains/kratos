"""Resolve model-visible artifact references in their owning session."""
from pathlib import Path, PurePosixPath

ARTIFACT_DIRS = {"tool_outputs", "output", "charts", "reports", "analyses", "analysis_flow", "transcripts"}


def resolve_reference(reference: str, *, project: Path, sessions: Path, session_id: str = "") -> Path:
    normalized = str(reference).replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise ValueError("Path traversal is not allowed")
    project, sessions = project.resolve(), sessions.resolve()
    if parts and parts[0] == "sessions":
        if len(parts) < 3 or not session_id or parts[1] != session_id:
            raise ValueError("Artifact belongs to another session")
        parts = parts[2:]
        if parts[0] not in ARTIFACT_DIRS:
            raise ValueError("Not a readable session artifact")
        resolved = (sessions / session_id / Path(*parts)).resolve()
    elif parts and parts[0] in ARTIFACT_DIRS and session_id:
        resolved = (sessions / session_id / Path(*parts)).resolve()
    else:
        resolved = (project / reference).resolve()
        if not resolved.is_relative_to(project):
            raise ValueError("Path escapes workspace")
    if resolved.is_relative_to(sessions):
        own = (sessions / session_id).resolve() if session_id else None
        if own is None or not own.is_relative_to(sessions) or not resolved.is_relative_to(own):
            raise ValueError("Artifact belongs to another session")
        rel = resolved.relative_to(own)
        if not rel.parts or rel.parts[0] not in ARTIFACT_DIRS:
            raise ValueError("Not a readable session artifact")
    elif parts and parts[0] in ARTIFACT_DIRS and session_id:
        raise ValueError("Artifact symlink escapes session")
    return resolved
