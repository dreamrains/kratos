from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
import pytest

import data_agent.config as config_module
from data_agent.agent.context import AgentContext, reset_current_context, set_current_context
from data_agent.config import AgentConfig
from data_agent.file_formats import SUPPORTED_DATA_EXTENSIONS
from data_agent.session.workspace import Workspace
from data_agent.tools.data_io import _detect_format, load_data
from data_agent.web.blueprints.uploads import ALLOWED_EXTENSIONS
from scripts.testing.dependency_preflight import dependency_preflight


@pytest.fixture
def isolated_context(tmp_path, monkeypatch):
    config = AgentConfig(
        PROJECT_DIR=tmp_path / "project",
        SESSIONS_DIR=tmp_path / "sessions",
    )
    monkeypatch.setattr(config_module, "_config", config)
    context = AgentContext(session_id="format-contract", workspace=Workspace())
    token = set_current_context(context)
    try:
        yield context
    finally:
        reset_current_context(token)


def test_dependency_preflight_has_no_false_optional_format_claims():
    report = dependency_preflight()
    assert report["missing_core_imports"] == []
    assert ALLOWED_EXTENSIONS == SUPPORTED_DATA_EXTENSIONS
    for item in report["optional"].values():
        assert not item["advertised"] or item["available"]


def test_template_accept_list_matches_supported_extensions():
    root = Path(__file__).resolve().parents[1]
    html = (root / "src/data_agent/web/templates/index.html").read_text(encoding="utf-8")
    match = re.search(r'<input[^>]+accept="([^"]+)"[^>]+@change="uploadFile', html)
    assert match is not None
    assert set(match.group(1).split(",")) == SUPPORTED_DATA_EXTENSIONS
    assert ".parquet" not in html
    assert ".feather" not in html


def test_detect_format_rejects_unknown_instead_of_treating_it_as_csv():
    assert _detect_format("data.csv") == "csv"
    assert _detect_format("data.tsv") == "tsv"
    assert _detect_format("data.xlsx") == "excel"
    assert _detect_format("data.json") == "json"
    assert _detect_format("data.jsonl") == "jsonl"
    assert _detect_format("data.parquet") == ""
    assert _detect_format("data.unknown") == ""


def test_supported_text_formats_are_actually_loadable(tmp_path, isolated_context):
    csv_path = tmp_path / "sample.csv"
    tsv_path = tmp_path / "sample.tsv"
    json_path = tmp_path / "sample.json"
    jsonl_path = tmp_path / "sample.jsonl"
    frame = pd.DataFrame({"类别": ["A", "B"], "数值": [1, 2]})
    frame.to_csv(csv_path, index=False, encoding="utf-8")
    frame.to_csv(tsv_path, index=False, sep="\t", encoding="utf-8")
    frame.to_json(json_path, orient="records", force_ascii=False)
    frame.to_json(jsonl_path, orient="records", lines=True, force_ascii=False)

    for path in (csv_path, tsv_path, json_path, jsonl_path):
        result = load_data(str(path), name=path.suffix.removeprefix(".") or "data")
        assert "Error" not in result, result
