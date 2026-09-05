import json
import os
import sys
from pathlib import Path

import pytest

from scripts.acceptance.browser_process import (
    require_graceful_exit,
    require_supervised_child,
    supervise,
)


@pytest.mark.parametrize('code', [0, 1])
def test_parent_observes_exit_code_and_stop_interval(tmp_path, code):
    script = "import os,pathlib,time\np=pathlib.Path(os.environ['DATA_AGENT_ACCEPTANCE_STOP_PATH'])\np.with_name('stop.request').touch()\nwhile not p.exists(): time.sleep(.01)\nraise SystemExit("+str(code)+")"
    proof = supervise([sys.executable, '-c', script], tmp_path/'control')
    assert proof['exit_code'] == code
    assert proof['process_exited'] and not proof['forced_termination']
    assert proof['graceful_exit'] is (code == 0)
    assert proof['elapsed_after_stop_seconds'] <= 30
    assert json.loads((tmp_path/'control/process-exit.json').read_text()) == proof
    if code == 0:
        require_graceful_exit(tmp_path/'control/process-exit.json', expected_pid=proof['pid'])
    else:
        with pytest.raises(ValueError, match='not proven'):
            require_graceful_exit(tmp_path/'control/process-exit.json', expected_pid=proof['pid'])


def test_late_owned_process_termination_never_becomes_graceful(tmp_path):
    script = "import os,pathlib,time; pathlib.Path(os.environ['DATA_AGENT_ACCEPTANCE_STOP_PATH']).with_name('stop.request').touch(); time.sleep(10)"
    proof = supervise([sys.executable, '-c', script], tmp_path/'control', stop_timeout=.2, terminate_owned=True)
    assert proof['process_exited'] and proof['forced_termination'] and proof['timeout_reached']
    assert not proof['graceful_exit']
    assert (tmp_path/'control/timeout-diagnostic.json').exists()
    with pytest.raises(ValueError, match='not proven'):
        require_graceful_exit(tmp_path/'control/process-exit.json', expected_pid=proof['pid'])


def test_spontaneous_exit_is_not_a_successful_requested_shutdown(tmp_path):
    proof = supervise([sys.executable, '-c', 'pass'], tmp_path/'control')
    assert proof['exit_code'] == 0 and not proof['graceful_exit']
    with pytest.raises(FileExistsError):
        supervise([sys.executable, '-c', 'pass'], tmp_path/'control')


def test_current_child_requires_matching_live_supervisor_start_record(tmp_path):
    control = (tmp_path / 'control').resolve()
    control.mkdir()
    launcher = (tmp_path / 'launcher.py').resolve()
    launcher.write_text('# frozen launcher', encoding='utf8')
    start = {
        'schema_version': 'browser_process_start.v1',
        'pid': os.getpid(),
        'supervisor_pid': max(1, os.getpid() - 1),
        'command': [sys.executable, str(launcher), '--case', 'M01'],
        'started_at': 'recorded',
        'stop_request_path': str(control / 'stop.request'),
        'stop_signal_path': str(control / 'stop.signal'),
        'stop_timeout_seconds': 30,
    }
    (control / 'process-start.json').write_text(json.dumps(start), encoding='utf8')
    result = require_supervised_child(
        control,
        expected_pid=os.getpid(),
        expected_stop_signal=control / 'stop.signal',
        expected_command_tail=[str(launcher), '--case', 'M01'],
        wait_seconds=0,
    )
    assert result == start
    start['pid'] = -1
    (control / 'process-start.json').write_text(json.dumps(start), encoding='utf8')
    with pytest.raises(ValueError, match='not proven'):
        require_supervised_child(
            control,
            expected_pid=os.getpid(),
            expected_stop_signal=control / 'stop.signal',
            expected_command_tail=[str(launcher), '--case', 'M01'],
            wait_seconds=0,
        )


@pytest.mark.parametrize('changes', [{'pid':-1},{'elapsed_after_stop_seconds':31},{'forced_termination':True}, {'exit_code':1}])
def test_exit_gate_rejects_misattribution_late_or_abnormal_proofs(tmp_path, changes):
    proof = {'schema_version':'browser_process_exit.v1','pid':123,'exit_code':0,'process_exited':True,
             'graceful_exit':True,'forced_termination':False,'timeout_reached':False,
             'elapsed_after_stop_seconds':.3,'stop_observed_at':'recorded', **changes}
    path = tmp_path/'proof.json'
    path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match='not proven'):
        require_graceful_exit(path, expected_pid=123)
