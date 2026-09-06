"""Deterministic dependency and advertised-capability preflight."""

from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path

from data_agent.file_formats import SUPPORTED_DATA_EXTENSIONS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"

CORE_IMPORTS = (
    "flask",
    "jinja2",
    "litellm",
    "numpy",
    "openpyxl",
    "pandas",
    "plotly",
    "pydantic",
    "scipy",
    "sklearn",
    "sqlalchemy",
    "statsmodels",
)


def _declared_dependencies(path: Path = PYPROJECT_PATH) -> tuple[str, ...]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    values = raw.get("project", {}).get("dependencies", [])
    return tuple(str(value) for value in values)


def dependency_preflight() -> dict:
    imports = {name: importlib.util.find_spec(name) is not None for name in CORE_IMPORTS}
    declared = _declared_dependencies()
    parquet_engines = {
        "pyarrow": importlib.util.find_spec("pyarrow") is not None,
        "fastparquet": importlib.util.find_spec("fastparquet") is not None,
    }
    pyarrow_declared = any(value.lower().startswith("pyarrow") for value in declared)
    parquet_available = any(parquet_engines.values())
    return {
        "contract_version": "dependency_preflight.v1",
        "core_imports": imports,
        "missing_core_imports": sorted(name for name, available in imports.items() if not available),
        "optional": {
            "parquet": {
                "available": parquet_available,
                "engines": parquet_engines,
                "pyarrow_declared": pyarrow_declared,
                "advertised": ".parquet" in SUPPORTED_DATA_EXTENSIONS,
            },
            "feather": {
                "available": parquet_engines["pyarrow"],
                "pyarrow_declared": pyarrow_declared,
                "advertised": ".feather" in SUPPORTED_DATA_EXTENSIONS,
            },
        },
        "supported_extensions": sorted(SUPPORTED_DATA_EXTENSIONS),
    }


def main() -> int:
    report = dependency_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["missing_core_imports"]:
        return 1
    if any(
        item["advertised"] and not item["available"]
        for item in report["optional"].values()
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
