"""PluginManager：管理插件的生命周期和工具注册。"""

from __future__ import annotations

from typing import Any, Optional

from data_agent.plugins.base import Plugin, PluginInfo
from data_agent.tools.registry import registry
from data_agent.utils.logging import get_logger

logger = get_logger("plugins")


class PluginManager:
    """管理 Plugin 实例的注册、启停和工具路由。"""

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._tool_to_plugin: dict[str, str] = {}  # tool_name -> plugin_name
        self._enabled: dict[str, bool] = {}

    def register_plugin(self, plugin: Plugin, auto_start: bool = True) -> None:
        """注册插件并可选自动启动。"""
        self._plugins[plugin.name] = plugin
        self._enabled[plugin.name] = auto_start

        if auto_start:
            try:
                plugin.start()
                self._register_tools(plugin)
                logger.info("Plugin registered and started",
                            extra={"extra_data": {"plugin": plugin.name}})
            except Exception as e:
                logger.error("Plugin start failed",
                             extra={"extra_data": {"plugin": plugin.name, "error": str(e)}})

    def unregister_plugin(self, name: str) -> None:
        """注销插件：停止并移除工具注册。"""
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return

        try:
            self._unregister_tools(name)
            plugin.stop()
        except Exception as e:
            logger.warning("Plugin stop error",
                           extra={"extra_data": {"plugin": name, "error": str(e)}})

        self._enabled.pop(name, None)
        logger.info("Plugin unregistered", extra={"extra_data": {"plugin": name}})

    def enable(self, name: str) -> str:
        """启用已注册但已停止的插件。"""
        plugin = self._plugins.get(name)
        if plugin is None:
            return f"插件 '{name}' 未注册"

        if self._enabled.get(name, False):
            return f"插件 '{name}' 已在运行"

        try:
            plugin.start()
            self._register_tools(plugin)
            self._enabled[name] = True
            return f"已启用插件 '{name}'"
        except Exception as e:
            return f"启用失败: {e}"

    def disable(self, name: str) -> str:
        """禁用插件：停止但不移除注册。"""
        plugin = self._plugins.get(name)
        if plugin is None:
            return f"插件 '{name}' 未注册"

        if not self._enabled.get(name, False):
            return f"插件 '{name}' 已处于禁用状态"

        try:
            self._unregister_tools(name)
            plugin.stop()
            self._enabled[name] = False
            return f"已禁用插件 '{name}'"
        except Exception as e:
            return f"禁用失败: {e}"

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """路由工具调用到对应的插件。"""
        plugin_name = self._tool_to_plugin.get(tool_name)
        if plugin_name is None:
            return f'{{"error": "Tool \'{tool_name}\' not found in any plugin"}}'

        plugin = self._plugins.get(plugin_name)
        if plugin is None or not self._enabled.get(plugin_name, False):
            return f'{{"error": "Plugin \'{plugin_name}\' is not enabled"}}'

        return plugin.call_tool(tool_name, arguments)

    def list_plugins(self) -> list[PluginInfo]:
        """列出所有插件的状态信息。"""
        result = []
        for name, plugin in self._plugins.items():
            tools = []
            try:
                tools = plugin.discover_tools()
            except Exception:
                pass

            enabled = self._enabled.get(name, False)
            status = "running" if enabled else "stopped"

            result.append(PluginInfo(
                name=name,
                status=status,
                tool_count=len(tools),
            ))
        return result

    def _register_tools(self, plugin: Plugin) -> None:
        """将插件的工具注册到全局 registry。"""
        tools = plugin.discover_tools()
        for tool_def in tools:
            tool_name = tool_def.get("name", "")
            if not tool_name:
                continue

            # 使用前缀避免冲突
            prefixed_name = f"{plugin.name}__{tool_name}"

            self._tool_to_plugin[prefixed_name] = plugin.name
            # 也注册无前缀版本（如果无冲突）
            self._tool_to_plugin[tool_name] = plugin.name

            # 闭包捕获 tool_name 和 plugin.name
            def _make_caller(tn, pn):
                def caller(**kwargs):
                    full = f"{pn}__{tn}"
                    target = full if full in self._tool_to_plugin else tn
                    return self.call_tool(target, kwargs)
                return caller

            registry.add(
                name=prefixed_name,
                description=tool_def.get("description", ""),
                func=_make_caller(tool_name, plugin.name),
                parameters=tool_def.get("parameters", {"type": "object", "properties": {}}),
                origin=plugin.name,
            )

    def _unregister_tools(self, plugin_name: str) -> None:
        """从全局 registry 移除插件的所有工具。"""
        to_remove = [tn for tn, pn in self._tool_to_plugin.items() if pn == plugin_name]
        for tool_name in to_remove:
            del self._tool_to_plugin[tool_name]
            # registry 的 _tools 是 dict，直接删除
            registry._tools.pop(tool_name, None)
