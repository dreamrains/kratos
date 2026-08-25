from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    model_id: str = Field(alias="MODEL_ID", default="gpt-4o")
    api_base: Optional[str] = Field(alias="API_BASE", default=None)
    api_key: Optional[str] = Field(alias="API_KEY", default=None)
    max_tokens: Optional[int] = Field(alias="MAX_TOKENS", default=None)
    quality_judge_model: Optional[str] = Field(alias="QUALITY_JUDGE_MODEL", default=None)

    # Paths
    workspace_dir: Path = Field(alias="WORKSPACE_DIR", default=Path("./workspace"))
    project_dir: Optional[Path] = Field(alias="PROJECT_DIR", default=None)
    sessions_dir: Path = Field(alias="SESSIONS_DIR", default=Path("./sessions"))

    # Agent
    significance_level: float = Field(alias="SIGNIFICANCE_LEVEL", default=0.05)
    token_threshold: int = Field(alias="TOKEN_THRESHOLD", default=200_000)

    # Logging
    log_level: str = Field(alias="LOG_LEVEL", default="INFO")
    log_file: Optional[str] = Field(alias="LOG_FILE", default=None)

    # MCP / Skill
    mcp_enabled: bool = Field(alias="MCP_ENABLED", default=True)
    skill_auto_discover: bool = Field(alias="SKILL_AUTO_DISCOVER", default=True)

    @property
    def global_dir(self) -> Path:
        p = Path.home() / ".data-agent"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def global_skills_dir(self) -> Path:
        p = self.global_dir / "skills"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def global_mcp_config_path(self) -> Path:
        return self.global_dir / "mcp_servers.yaml"

    @property
    def global_settings_path(self) -> Path:
        return self.global_dir / "settings.yaml"

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("MODEL_ID cannot be empty")
        return v.strip()

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: Optional[int]) -> Optional[int]:
        # None means the output budget is provider-managed: the request omits
        # max_tokens entirely, so the effective cap follows the model default.
        if v is not None and (v < 100 or v > 128000):
            raise ValueError("MAX_TOKENS must be between 100 and 128000")
        return v

    @field_validator("token_threshold")
    @classmethod
    def validate_token_threshold(cls, v: int) -> int:
        if v < 10000:
            raise ValueError("TOKEN_THRESHOLD must be at least 10000")
        return v

    @property
    def workspace_resolved(self) -> Path:
        p = self.workspace_dir
        if self.project_dir is not None and self.workspace_dir == Path("./workspace"):
            p = self.project_dir
        if not p.is_absolute():
            p = Path.cwd() / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def project_resolved(self) -> Path:
        """Compatibility alias for the pre-release PROJECT_DIR name."""
        return self.workspace_resolved

    @property
    def data_dir(self) -> Path:
        p = self.workspace_resolved / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def inbox_dir(self) -> Path:
        p = self.workspace_resolved / "inbox"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def objects_dir(self) -> Path:
        """Legacy object storage path kept only for migration and old imports."""
        p = self.workspace_resolved / "objects"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def projects_dir(self) -> Path:
        p = self.workspace_resolved / "projects"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def knowledge_dir(self) -> Path:
        p = self.workspace_resolved / "knowledge"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sessions_resolved(self) -> Path:
        p = self.sessions_dir
        if not p.is_absolute():
            p = Path.cwd() / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def mcp_config_path(self) -> Path:
        """Legacy workspace-level MCP config path kept for migration only."""
        return self.workspace_resolved / "mcp_servers.yaml"

    @property
    def skills_dir(self) -> Path:
        """Legacy workspace-level skills path kept for migration only."""
        return self.workspace_resolved / "skills"

    @property
    def log_file_resolved(self) -> Optional[Path]:
        if self.log_file:
            return Path(self.log_file)
        return None


ENV_KEY_MAP = {
    "model_id": "MODEL_ID",
    "api_base": "API_BASE",
    "api_key": "API_KEY",
}


def persist_config_to_env(updates: dict) -> None:
    env_path = Path.cwd() / ".env"

    env_updates = {}
    for py_key, value in updates.items():
        env_name = ENV_KEY_MAP.get(py_key)
        if env_name:
            env_updates[env_name] = value

    if not env_updates:
        return

    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updated_keys: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in env_updates:
                val = env_updates[key]
                lines[i] = f"{key}={val if val is not None else ''}"
                updated_keys.add(key)

    for key, value in env_updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={value if value is not None else ''}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    global _config
    if _config is None:
        _config = AgentConfig()
    return _config


def update_runtime_config(updates: dict) -> dict:
    cfg = get_config()
    changed = {}
    for key, value in updates.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if hasattr(cfg, key):
            old = getattr(cfg, key)
            if old != value:
                setattr(cfg, key, value)
                changed[key] = value
    return changed
