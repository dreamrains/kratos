"""Agent 生命周期管理：有序的初始化和关闭流程。

参考 s_full.py global_instances (lines 544-550) 的模块级资源创建模式，
升级为有序的生命周期管理，确保资源正确初始化和清理。
"""

from __future__ import annotations

from data_agent.utils.logging import get_logger

logger = get_logger("lifecycle")


class AgentLifecycle:
    """管理 Agent 各子系统的有序启动和关闭。"""

    def __init__(self):
        self._initialized = False

    def initialize(self) -> None:
        """有序启动所有子系统。

        启动顺序:
        1. 验证配置
        2. 初始化日志
        3. 自动发现并注册原生工具
        4. 发现技能
        5. 启动 MCP 并注册 MCP 工具
        """
        if self._initialized:
            return

        from data_agent.config import get_config

        # 1. 配置验证（Pydantic 自动验证）
        cfg = get_config()
        logger.info("Configuration loaded", extra={"extra_data": {
            "model": cfg.model_id,
            "project": str(cfg.project_resolved),
        }})

        # 2. 初始化日志
        from data_agent.utils.logging import setup_logging
        setup_logging(level=cfg.log_level, log_file=cfg.log_file_resolved)

        # 3. 自动发现并注册原生工具
        from data_agent.tools import discover_tools
        discover_tools()
        from data_agent.tools.registry import registry
        logger.info("Native tools registered", extra={"extra_data": {
            "count": len(registry.tool_names),
            "tools": registry.tool_names,
        }})

        # 4. 技能发现延迟到 AgentLoop.__init__() 中执行（避免重复初始化）

        # 5. MCP 初始化在 AgentLoop.__init__() 中按需执行
        # （因为 MCP 连接需要与 loop 生命周期绑定）

        self._initialized = True
        logger.info("Agent lifecycle initialized")

    def shutdown(self) -> None:
        """有序关闭所有子系统。

        关闭顺序:
        1. 自动保存会话
        2. 关闭 MCP 连接
        3. 刷新日志
        """
        if not self._initialized:
            return

        logger.info("Agent lifecycle shutting down")

        # 关闭 MCP
        try:
            from data_agent.agent.loop import get_mcp_manager
            mcp_mgr = get_mcp_manager()
            if mcp_mgr is not None:
                mcp_mgr.stop()
        except Exception as e:
            logger.warning("MCP shutdown error", extra={"extra_data": {"error": str(e)}})

        # 刷新日志
        import logging
        logging.shutdown()

        self._initialized = False
