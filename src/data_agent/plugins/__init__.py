"""插件系统：通用的 Plugin 协议和管理器。"""

from data_agent.plugins.base import Plugin, PluginInfo
from data_agent.plugins.manager import PluginManager

__all__ = ["Plugin", "PluginInfo", "PluginManager"]
