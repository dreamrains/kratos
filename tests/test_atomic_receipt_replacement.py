import ctypes
import json
import os
from pathlib import Path
import threading

import pytest

from data_agent.utils.atomic_files import replace_file


def test_replacement_denial_is_bounded_and_does_not_publish_partial_state(tmp_path, monkeypatch):
    destination, source = tmp_path/'receipt.json', tmp_path/'receipt.tmp'
    destination.write_text('old')
    source.write_text('new')
    attempts = []

    def denied(self, target):
        attempts.append(1)
        exc = PermissionError('locked')
        exc.winerror = 5
        raise exc

    monkeypatch.setattr(Path, 'replace', denied)
    monkeypatch.setattr('data_agent.utils.atomic_files.time.sleep', lambda _: None)
    with pytest.raises(PermissionError):
        replace_file(source, destination, attempts=3)
    assert len(attempts) == 3
    assert destination.read_text() == 'old' and source.read_text() == 'new'


@pytest.mark.skipif(os.name != 'nt', reason='Windows sharing semantics')
def test_real_windows_read_lock_preserves_then_commits_scripted_receipt(tmp_path):
    from ctypes import wintypes
    path = tmp_path/'receipt.json'
    source = tmp_path/'receipt.tmp'
    path.write_text(json.dumps({'calls': [{'status': 'started'}]}), encoding='utf-8')
    source.write_text(json.dumps({'calls': [{'status': 'completed'}]}), encoding='utf-8')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    timer = threading.Timer(0.08, lambda: kernel.CloseHandle(handle))
    try:
        assert json.loads(path.read_text())['calls'][0]['status'] == 'started'
        timer.start()
        replace_file(source, path)
    finally:
        timer.join(timeout=1)
        if timer.ident is None:
            kernel.CloseHandle(handle)
    assert json.loads(path.read_text())['calls'][0]['status'] == 'completed'
    assert not source.exists()


def test_non_windows_permission_failure_is_not_retried(tmp_path, monkeypatch):
    def denied(self, target):
        raise PermissionError('not a sharing violation')
    monkeypatch.setattr(Path, 'replace', denied)
    monkeypatch.setattr('data_agent.utils.atomic_files.time.sleep', lambda _: pytest.fail('must not retry'))
    with pytest.raises(PermissionError):
        replace_file(tmp_path/'source', tmp_path/'destination')
