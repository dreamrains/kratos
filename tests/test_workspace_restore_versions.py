import json

import pandas as pd
from pandas.testing import assert_frame_equal

from data_agent.agent.analysis_state import AnalysisSessionState
from data_agent.agent.context import AgentContext, use_agent_context
from data_agent.agent.data_lineage import frame_fingerprint
from data_agent.agent.loop import AgentLoop
from data_agent.session.task_manager import TaskManager
from data_agent.session.workspace import Workspace


def _session_environment(tmp_path, monkeypatch, session_id="restore-session"):
    import data_agent.agent.analysis_state as analysis_state_module
    import data_agent.session.history as history
    import data_agent.session.task_manager as task_manager_module

    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(history, "_session_dir", lambda _session_id: session_dir)
    monkeypatch.setattr(
        task_manager_module,
        "task_manager",
        TaskManager(tasks_dir=tmp_path / "tasks"),
    )
    monkeypatch.setattr(
        analysis_state_module,
        "load_analysis_state",
        lambda loaded_session_id, _project_name=None: AnalysisSessionState(
            session_id=loaded_session_id
        ),
    )
    return session_dir


def _persist_two_versions(session_id, source_path=""):
    store = Workspace()
    raw = pd.DataFrame({"amount": [1, 2]})
    fingerprint = frame_fingerprint(raw)
    raw_info = store.register_raw_snapshot("orders", raw, fingerprint)
    first = store.promote_analysis_copy(
        "orders", raw, raw_info["dataset_id"], {"id": "prepare"}
    )
    active = pd.DataFrame({"amount": [10, 20]})
    second = store.promote_analysis_copy(
        "orders",
        active,
        raw_info["dataset_id"],
        {
            "id": "confirmed_change",
            "parent_dataset_id": first["dataset_id"],
            "raw_dataset_id": raw_info["dataset_id"],
            "source_fingerprint": fingerprint,
        },
    )
    if source_path:
        store.set_metadata("orders", "_source_path", source_path)
        store.set_metadata("orders", "_source_fmt", "csv")
    store.save_meta(session_id)
    store.persist_dataset(session_id, "orders")
    return raw, active, raw_info, second


def _new_loop(monkeypatch, session_id="restore-session"):
    return AgentLoop(client=object(), session_id=session_id)


def _overwrite_backup(path, frame):
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=True)
    else:
        frame.to_pickle(path)


def test_restore_targets_loop_owned_workspace_not_ambient_context(tmp_path, monkeypatch):
    _session_environment(tmp_path, monkeypatch)
    raw, active, _, second = _persist_two_versions("restore-session")
    loop = _new_loop(monkeypatch)
    ambient_store = Workspace()
    ambient = AgentContext(session_id="ambient", workspace=ambient_store)

    with use_agent_context(ambient):
        loop._restore_workspace()

    assert ambient_store.get("orders") is None
    assert_frame_equal(loop.context.workspace.get("orders"), active)
    assert loop.context.workspace.get_active_version_info("orders")["dataset_id"] == second["dataset_id"]
    assert_frame_equal(
        loop.context.workspace.get_raw_snapshot(second["raw_dataset_id"]),
        raw,
    )


def test_source_drift_prefers_matching_persisted_raw_and_restores_v2(tmp_path, monkeypatch):
    session_dir = _session_environment(tmp_path, monkeypatch)
    source = tmp_path / "orders.csv"
    pd.DataFrame({"amount": [1, 2]}).to_csv(source, index=False)
    raw, active, _, second = _persist_two_versions(
        "restore-session", source_path=str(source)
    )
    pd.DataFrame({"amount": [999, 1000]}).to_csv(source, index=False)
    loop = _new_loop(monkeypatch)

    loop._restore_workspace()

    restored = loop.context.workspace
    restored_info = restored.get_active_version_info("orders")
    assert restored_info["dataset_id"] == second["dataset_id"]
    assert restored_info["version"] == 2
    assert_frame_equal(restored.get("orders"), active)
    assert_frame_equal(restored.get_raw_snapshot(restored_info["raw_dataset_id"]), raw)
    assert restored.get_metadata("orders", "source_changed_since_save") is True

    third = restored.promote_analysis_copy(
        "orders",
        pd.DataFrame({"amount": [30, 40]}),
        restored_info["raw_dataset_id"],
        {"id": "next", "parent_dataset_id": restored_info["dataset_id"]},
    )
    assert third["version"] == 3
    assert "_v3_" in third["dataset_id"]
    assert session_dir.exists()


def test_source_drift_without_matching_raw_reprepares_and_rejects_old_active(
    tmp_path,
    monkeypatch,
):
    session_dir = _session_environment(tmp_path, monkeypatch)
    source = tmp_path / "orders.csv"
    pd.DataFrame({"amount": [1, 2]}).to_csv(source, index=False)
    _, _, _, second = _persist_two_versions(
        "restore-session", source_path=str(source)
    )
    pd.DataFrame({"amount": [999, 1000]}).to_csv(source, index=False)
    raw_backup = next((session_dir / "data").glob("orders__raw.*"))
    _overwrite_backup(raw_backup, pd.DataFrame({"amount": [555, 556]}))
    loop = _new_loop(monkeypatch)

    loop._restore_workspace()

    restored = loop.context.workspace
    restored_info = restored.get_active_version_info("orders")
    assert restored_info["dataset_id"] != second["dataset_id"]
    assert restored_info["version"] == 1
    assert restored.get("orders")["amount"].tolist() == [999, 1000]
    assert restored.get_metadata("orders", "source_changed_since_save") is True


def test_legacy_active_only_backup_still_migrates_to_raw_and_active(tmp_path, monkeypatch):
    session_dir = _session_environment(tmp_path, monkeypatch, session_id="legacy")
    legacy = pd.DataFrame({"amount": [7, 8]}, index=[10, 20])
    (session_dir / "data").mkdir(exist_ok=True)
    legacy.to_pickle(session_dir / "data" / "orders.pkl")
    (session_dir / "workspace_meta.json").write_text(
        json.dumps({
            "orders": {
                "shape": [2, 1],
                "columns": ["amount"],
                "source_path": "",
                "source_fmt": "",
                "context": "",
            }
        }),
        encoding="utf-8",
    )
    loop = _new_loop(monkeypatch, session_id="legacy")

    loop._restore_workspace()

    restored = loop.context.workspace
    info = restored.get_active_version_info("orders")
    assert_frame_equal(restored.get("orders"), legacy)
    assert_frame_equal(restored.get_raw_snapshot(info["raw_dataset_id"]), legacy)
    assert restored.get_metadata("orders", "migrated_from_legacy_backup") is True
