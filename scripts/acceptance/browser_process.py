"""Out-of-process exit proof and a local file-controlled acceptance server.

This does not authorize Provider use. Freeze its command, control directory and
stop policy separately before a real batch. The parent owns its Popen handle;
it never finds or terminates processes by name or by port.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def _now():
    return datetime.now(timezone.utc).isoformat()


def _save(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def serve_until_stopped(app, *, host, port, stop_path):
    """No network stop endpoint. Only the controlling local process writes it."""
    from werkzeug.serving import make_server
    stop = Path(stop_path)
    if stop.exists():
        raise ValueError('stop request already exists')
    server = make_server(host, port, app, threaded=True)
    server.timeout = 0.1
    try:
        while not stop.exists():
            server.handle_request()
    finally:
        server.server_close()


def supervise(command, control_dir, *, stop_timeout=30, terminate_owned=False):
    """Record actual child exit continuously, including abnormal/late exits."""
    control = Path(control_dir).resolve()
    control.mkdir(parents=True, exist_ok=False)
    request = control / 'stop.request'
    stop = control / 'stop.signal'
    env = dict(os.environ, DATA_AGENT_ACCEPTANCE_STOP_PATH=str(stop))
    with (control / 'process.log').open('xb') as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        _save(control/'process-start.json', {'schema_version':'browser_process_start.v1',
                                            'pid':child.pid, 'supervisor_pid':os.getpid(),
                                            'command':command, 'started_at':_now(),
                                            'stop_request_path':str(request), 'stop_signal_path':str(stop),
                                            'stop_timeout_seconds':stop_timeout})
        stop_at = None
        stop_time = None
        timeout_reached = False
        forced = False
        while True:
            code = child.poll()
            if code is not None:
                break
            if stop_at is None and request.exists():
                stop_at, stop_time = time.monotonic(), _now()
                _save(stop, {'pid':child.pid, 'requested_at':stop_time})
            if stop_at is not None and time.monotonic() - stop_at >= stop_timeout:
                timeout_reached = True
                _save(control/'timeout-diagnostic.json', {'pid':child.pid, 'captured_at':_now(),
                    'command':command, 'owned_process_handle':True, 'still_running':child.poll() is None})
                if terminate_owned and child.poll() is None:
                    child.terminate()
                    forced = True
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                break
            time.sleep(0.05)
        code = child.poll()
        elapsed = time.monotonic()-stop_at if stop_at is not None else None
        proof = {'schema_version':'browser_process_exit.v1', 'pid':child.pid, 'observed_at':_now(),
                 'stop_observed_at':stop_time, 'elapsed_after_stop_seconds':elapsed, 'exit_code':code,
                 'timeout_reached':timeout_reached, 'forced_termination':forced,
                 'process_exited':code is not None,
                 'graceful_exit':stop_at is not None and code == 0 and not timeout_reached and not forced and elapsed <= stop_timeout}
        _save(control/'process-exit.json', proof)
        return proof


def require_supervised_child(
    control_dir,
    *,
    expected_pid,
    expected_stop_signal,
    expected_command_tail=None,
    wait_seconds=2.0,
):
    """Prove the current acceptance process was started by the local supervisor.

    This is checked before the batch ledger is opened or a Provider transport
    is installed.  It does not infer ownership from a port or process name.
    """
    control = Path(control_dir).resolve()
    start_path = control / 'process-start.json'
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    while not start_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        start = json.loads(start_path.read_text('utf8'))
        command = start.get('command')
        tail = list(expected_command_tail or [])
        stop_signal = Path(start.get('stop_signal_path', '')).resolve()
        stop_request = Path(start.get('stop_request_path', '')).resolve()
        timeout = start.get('stop_timeout_seconds')
        valid = (
            start.get('schema_version') == 'browser_process_start.v1'
            and start.get('pid') == expected_pid
            and type(start.get('supervisor_pid')) is int
            and start['supervisor_pid'] > 0
            and isinstance(command, list)
            and bool(command)
            and (not tail or command[-len(tail):] == tail)
            and stop_signal == Path(expected_stop_signal).resolve()
            and stop_signal == control / 'stop.signal'
            and stop_request == control / 'stop.request'
            and isinstance(timeout, (int, float))
            and not isinstance(timeout, bool)
            and 0 < timeout <= 30
            and not (control / 'process-exit.json').exists()
            and not stop_request.exists()
            and not stop_signal.exists()
        )
    except (OSError, ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError('current supervised acceptance process not proven')
    return start


def require_graceful_exit(path, *, expected_pid):
    """Closed request accounting is not a substitute for this parent receipt."""
    try:
        proof = json.loads(Path(path).read_text('utf8'))
        elapsed = proof.get('elapsed_after_stop_seconds')
        valid = (proof.get('schema_version') == 'browser_process_exit.v1'
                 and proof.get('pid') == expected_pid and proof.get('exit_code') == 0
                 and proof.get('process_exited') is True and proof.get('graceful_exit') is True
                 and proof.get('forced_termination') is False and proof.get('timeout_reached') is False
                 and isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool)
                 and 0 <= elapsed <= 30 and bool(proof.get('stop_observed_at')))
    except (OSError, ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError('previous graceful process exit not proven')
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--control-dir', required=True)
    parser.add_argument('--terminate-owned-on-timeout', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('child command required')
    proof = supervise(command, args.control_dir, terminate_owned=args.terminate_owned_on_timeout)
    print(json.dumps(proof), flush=True)
    return 0 if proof['graceful_exit'] else 1


if __name__ == '__main__':
    sys.exit(main())
