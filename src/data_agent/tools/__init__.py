"""Tool auto-discovery: scan and import tool modules to trigger registration."""

_DISCOVERED = False


def discover_tools():
    """Import all tool modules to trigger @registry.register decorators."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    import importlib
    import pkgutil

    import data_agent.tools as tools_pkg

    for importer, module_name, is_pkg in pkgutil.iter_modules(tools_pkg.__path__):
        if module_name.startswith("_"):
            continue
        importlib.import_module(f"data_agent.tools.{module_name}")
