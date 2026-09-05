"""孤儿 run_state 的自愈：运行时消失后磁盘不得永远声称 running。

回归背景：服务进程在 turn 执行中被杀死（如关闭 start.bat 窗口）后，
run_state.json 永远停留在 running/cancelling。API 读取虽经 snapshot()
翻译成 unknown，但磁盘文件本身一直在说谎，误导文件级读取（排障、
脚本、人工查看）。
"""

import json

from data_agent.web.run_state import RunStates


def _seed_run_state(tmp_path, sid="s1", status="running", turn_id="t1"):
    directory = tmp_path / sid
    directory.mkdir(parents=True)
    (directory / "run_state.json").write_text(
        json.dumps({
            "turn_id": turn_id, "status": status, "session_id": sid,
            "updated_at": "2026-09-05T16:08:29+00:00",
        }),
        encoding="utf-8",
    )
    return directory


def _runs(tmp_path, monkeypatch):
    monkeypatch.setattr("data_agent.web.run_state._session_dir", lambda sid: tmp_path / sid)
    return RunStates()


def test_orphan_running_state_is_healed_on_disk(tmp_path, monkeypatch):
    directory = _seed_run_state(tmp_path, status="running")
    runs = _runs(tmp_path, monkeypatch)

    snap = runs.snapshot("s1")

    assert snap["status"] == "unknown"
    assert snap["reason"] == "runtime_restarted"
    healed = json.loads((directory / "run_state.json").read_text(encoding="utf-8"))
    assert healed["status"] == "unknown"
    assert healed["reason"] == "runtime_restarted"


def test_active_running_state_is_not_healed(tmp_path, monkeypatch):
    directory = _seed_run_state(tmp_path, status="completed")
    runs = _runs(tmp_path, monkeypatch)
    runs.begin("s1", "t2")  # begin 覆盖磁盘为 running 并持有内存态

    snap = runs.snapshot("s1")

    assert snap["status"] == "running"
    on_disk = json.loads((directory / "run_state.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "running"
    assert "reason" not in on_disk


def test_terminal_state_is_returned_untouched(tmp_path, monkeypatch):
    _seed_run_state(tmp_path, status="failed")
    runs = _runs(tmp_path, monkeypatch)

    snap = runs.snapshot("s1")

    assert snap["status"] == "failed"
    assert "reason" not in snap
