"""MCP 客户端管理器：管理多个 MCP 服务器连接。

核心设计：项目代码是同步的，MCP SDK 是异步的。
通过后台 asyncio.EventLoop 线程桥接两者。
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Optional

from data_agent.mcp.config import MCPConfig, MCPServerConfig
from data_agent.mcp.models import MCPToolDef
from data_agent.utils.logging import get_logger

logger = get_logger("mcp")


class MCPConnection:
    """持有单个 MCP 服务器的连接状态。"""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.session: Any = None
        self.tools_cache: list[MCPToolDef] = []
        self._context_stack: Any = None
        self._failure_count: int = 0

    @property
    def is_connected(self) -> bool:
        return self.session is not None

    @property
    def is_degraded(self) -> bool:
        return self._failure_count >= 3


class MCPClientManager:
    """管理多个 MCP 服务器的连接、工具发现和调用。"""

    def __init__(self, config: MCPConfig):
        self._config = config
        self._connections: dict[str, MCPConnection] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动后台事件循环线程并连接到已启用的服务器。"""
        if not self._config.servers:
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

        for cfg in self._config.servers:
            if cfg.enabled and cfg.auto_start:
                try:
                    self._run_async(self._connect(cfg))
                    logger.info("MCP server connected", extra={"extra_data": {"server": cfg.name}})
                except Exception as e:
                    logger.warning("MCP server connection failed",
                                   extra={"extra_data": {"server": cfg.name, "error": str(e)}})

    def stop(self) -> None:
        """关闭所有连接并停止事件循环。"""
        if self._loop is None:
            return

        try:
            self._run_async(self._disconnect_all())
        except Exception:
            pass

        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None
        logger.info("MCP client manager stopped")

    def _run_event_loop(self) -> None:
        """后台线程运行 asyncio 事件循环。"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro: Any) -> Any:
        """提交协程到后台事件循环，阻塞等待结果。"""
        if self._loop is None:
            raise RuntimeError("MCPClientManager not started")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    async def _connect(self, cfg: MCPServerConfig) -> None:
        """连接到单个 MCP 服务器。"""
        conn = MCPConnection(cfg)

        try:
            from mcp.client.session import ClientSession

            if cfg.transport == "stdio":
                from mcp.client.stdio import stdio_client, StdioServerParameters

                params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args or [],
                    env=cfg.env,
                )
                read_stream, write_stream = await self._enter_stdio(params)

            elif cfg.transport == "sse":
                from mcp.client.sse import sse_client

                read_stream, write_stream = await self._enter_sse(cfg.url, cfg.headers)

            elif cfg.transport == "streamable-http":
                from mcp.client.streamable_http import streamablehttp_client

                read_stream, write_stream = await self._enter_streamable_http(cfg.url, cfg.headers)
            else:
                raise ValueError(f"Unsupported transport: {cfg.transport}")

            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()

            conn.session = session
            conn._context_stack = (read_stream, write_stream)

            # 发现工具
            tools_result = await session.list_tools()
            conn.tools_cache = [
                MCPToolDef(
                    server_name=cfg.name,
                    tool_name=t.name,
                    description=t.description or "",
                    input_schema=t.inputSchema or {"type": "object", "properties": {}},
                )
                for t in tools_result.tools
            ]

            self._connections[cfg.name] = conn

        except Exception as e:
            logger.error("Failed to connect MCP server",
                         extra={"extra_data": {"server": cfg.name, "error": str(e)}})
            raise

    async def _enter_stdio(self, params: Any) -> tuple:
        """建立 stdio 传输连接。"""
        from mcp.client.stdio import stdio_client

        cm = stdio_client(params)
        read, write = await cm.__aenter__()
        return read, write

    async def _enter_sse(self, url: str, headers: Optional[dict]) -> tuple:
        """建立 SSE 传输连接。"""
        from mcp.client.sse import sse_client

        cm = sse_client(url=url, headers=headers)
        read, write = await cm.__aenter__()
        return read, write

    async def _enter_streamable_http(self, url: str, headers: Optional[dict]) -> tuple:
        """建立 Streamable HTTP 传输连接。"""
        from mcp.client.streamable_http import streamablehttp_client

        cm = streamablehttp_client(url=url, headers=headers)
        read, write = await cm.__aenter__()
        return read, write

    async def _disconnect_all(self) -> None:
        """关闭所有 MCP 服务器连接。"""
        for name, conn in self._connections.items():
            try:
                if conn.session:
                    await conn.session.__aexit__(None, None, None)
            except Exception:
                pass
        self._connections.clear()

    def discover_tools(self) -> list[MCPToolDef]:
        """返回所有已连接服务器发现的工具。"""
        all_tools = []
        for name, conn in self._connections.items():
            if conn.is_connected and not conn.is_degraded:
                all_tools.extend(conn.tools_cache)
        return all_tools

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        """调用指定 MCP 服务器上的工具。"""
        conn = self._connections.get(server_name)
        if conn is None or not conn.is_connected:
            return json.dumps({"error": f"MCP server '{server_name}' not connected"}, ensure_ascii=False)

        if conn.is_degraded:
            return json.dumps({"error": f"MCP server '{server_name}' is degraded (too many failures)"}, ensure_ascii=False)

        try:
            result = self._run_async(self._call_tool_async(conn, tool_name, arguments))
            conn._failure_count = 0
            return result
        except Exception as e:
            conn._failure_count += 1
            logger.error("MCP tool call failed",
                         extra={"extra_data": {"server": server_name, "tool": tool_name, "error": str(e)}})
            return json.dumps({"error": f"MCP tool call failed: {str(e)}"}, ensure_ascii=False)

    async def _call_tool_async(self, conn: MCPConnection, tool_name: str, arguments: dict) -> str:
        """异步调用 MCP 工具。"""
        result = await conn.session.call_tool(tool_name, arguments)

        # 提取文本内容
        if result.content:
            texts = []
            for item in result.content:
                if hasattr(item, "text"):
                    texts.append(item.text)
                elif isinstance(item, str):
                    texts.append(item)
            return "\n".join(texts) if texts else ""

        if result.isError:
            return json.dumps({"error": "Tool returned an error"}, ensure_ascii=False)

        return ""

    def health_check(self) -> dict[str, dict]:
        """检查所有服务器的健康状态。"""
        status = {}
        for name, conn in self._connections.items():
            tool_names = [t.tool_name for t in conn.tools_cache]
            state = "connected" if conn.is_connected else "disconnected"
            if conn.is_degraded:
                state = "degraded"
            status[name] = {
                "status": state,
                "tools": ", ".join(tool_names[:5]) + (f" (+{len(tool_names) - 5})" if len(tool_names) > 5 else ""),
            }
        return status

    @property
    def connected_servers(self) -> list[str]:
        return [name for name, conn in self._connections.items() if conn.is_connected]

    # ── 运行时单服务器管理 ────────────────────────────────

    def connect_server(self, config: MCPServerConfig) -> str:
        """运行时连接单个新 MCP 服务器。"""
        if config.name in self._connections:
            return f"MCP server '{config.name}' 已存在"

        try:
            self._run_async(self._connect(config))
            logger.info("MCP server connected at runtime",
                        extra={"extra_data": {"server": config.name}})
            return f"已连接 MCP server '{config.name}'"
        except Exception as e:
            return f"连接失败: {e}"

    def disconnect_server(self, name: str) -> str:
        """运行时断开单个 MCP 服务器。"""
        conn = self._connections.get(name)
        if conn is None:
            return f"MCP server '{name}' 未连接"

        try:
            if conn.session:
                self._run_async(conn.session.__aexit__(None, None, None))
        except Exception:
            pass

        del self._connections[name]
        logger.info("MCP server disconnected at runtime",
                    extra={"extra_data": {"server": name}})
        return f"已断开 MCP server '{name}'"

    def enable_server(self, name: str) -> str:
        """启用已断开的服务器（需要重新连接）。返回提示信息。"""
        conn = self._connections.get(name)
        if conn and conn.is_connected:
            return f"MCP server '{name}' 已处于连接状态"

        return f"MCP server '{name}' 需要通过 connect_server 重新连接"

    def disable_server(self, name: str) -> str:
        """禁用服务器（断开连接但保留配置）。"""
        return self.disconnect_server(name)
