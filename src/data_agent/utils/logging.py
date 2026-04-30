"""结构化日志系统，支持 JSON 格式和可配置输出。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """结构化 JSON 日志格式器。"""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_data = getattr(record, "extra_data", None)
        if extra_data:
            entry["data"] = extra_data
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """控制台友好的简洁日志格式器。"""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now().strftime("%H:%M:%S")
        extra_data = getattr(record, "extra_data", None)
        msg = f"{color}{ts} [{record.levelname}] {record.name}: {record.getMessage()}{self.RESET}"
        if extra_data:
            msg += f" {json.dumps(extra_data, ensure_ascii=False, default=str)}"
        return msg


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    json_output: bool = False,
) -> None:
    """配置 data_agent 全局日志。

    Args:
        level: 日志级别。
        log_file: 可选的日志文件路径。
        json_output: 是否使用 JSON 格式输出到文件。
    """
    root_logger = logging.getLogger("data_agent")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有 handler 防止重复
    root_logger.handlers.clear()

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)

    # 文件 handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(JSONFormatter() if json_output else ConsoleFormatter())
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取 data_agent 子模块 logger。"""
    return logging.getLogger(f"data_agent.{name}")
