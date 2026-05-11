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
    max_tokens: int = Field(alias="MAX_TOKENS", default=8000)

    # Paths
    project_dir: Path = Field(alias="PROJECT_DIR", default=Path("./project"))
    sessions_dir: Path = Field(alias="SESSIONS_DIR", default=Path("./sessions"))

    # Agent
    significance_level: float = Field(alias="SIGNIFICANCE_LEVEL", default=0.05)
    token_threshold: int = Field(alias="TOKEN_THRESHOLD", default=100_000)

    # Logging
    log_level: str = Field(alias="LOG_LEVEL", default="INFO")
    log_file: Optional[str] = Field(alias="LOG_FILE", default=None)

    # MCP / Skill
    mcp_enabled: bool = Field(alias="MCP_ENABLED", default=True)
    skill_auto_discover: bool = Field(alias="SKILL_AUTO_DISCOVER", default=True)

    # ── 全局配置目录 ──────────────────────────────────────

    @property
    def global_dir(self) -> Path:
        """全局配置目录 ~/.data-agent/，跨项目共享 skill、MCP 配置等。"""
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
    def validate_max_tokens(cls, v: int) -> int:
        if v < 100 or v > 128000:
            raise ValueError("MAX_TOKENS must be between 100 and 128000")
        return v

    @field_validator("token_threshold")
    @classmethod
    def validate_token_threshold(cls, v: int) -> int:
        if v < 10000:
            raise ValueError("TOKEN_THRESHOLD must be at least 10000")
        return v

    @property
    def project_resolved(self) -> Path:
        p = self.project_dir
        if not p.is_absolute():
            p = Path.cwd() / p
        return p

    @property
    def data_dir(self) -> Path:
        p = self.project_resolved / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def inbox_dir(self) -> Path:
        p = self.project_resolved / "inbox"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def objects_dir(self) -> Path:
        p = self.project_resolved / "objects"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def projects_dir(self) -> Path:
        """User-facing project directory alias.

        Phase 1 keeps the existing objects/ storage for compatibility while all
        new APIs expose the friendlier "project" terminology.
        """
        return self.objects_dir

    @property
    def knowledge_dir(self) -> Path:
        p = self.project_resolved / "knowledge"
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
    def workspace_resolved(self) -> Path:
        """向后兼容别名。"""
        return self.project_resolved

    @property
    def mcp_config_path(self) -> Path:
        return self.project_resolved / "mcp_servers.yaml"

    @property
    def skills_dir(self) -> Path:
        return self.project_resolved / "skills"

    @property
    def log_file_resolved(self) -> Optional[Path]:
        if self.log_file:
            return Path(self.log_file)
        return None


_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    global _config
    if _config is None:
        _config = AgentConfig()
    return _config


def update_runtime_config(updates: dict) -> dict:
    """运行时更新配置（不写入 .env）。返回更新后的字段。"""
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
