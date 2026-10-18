"""Main LLMClient raw sync/fragmented-stream boundary through normal app endpoints."""
from __future__ import annotations

import hashlib
import io
import json
from types import SimpleNamespace as NS

import pytest

from tests.test_trusted_publication_semantics import engine


class RawTransport:
    """Fixed public model decisions encoded as raw transport objects, never host state."""
    def __init__(self, model, fault):
        self.model, self.fault, self.calls = model, fault, []

    def __call__(self, **kwargs):
        messages = list(kwargs['messages'])
        system = messages.pop(0)['content'] if messages and messages[0]['role'] == 'system' else ''
        response = self.model.chat(messages, system=system, tools=kwargs.get('tools'))
        self.calls.append({'stream': bool(kwargs.get('stream')), 'num_retries': kwargs['num_retries'],
                           'tools': [c.name for c in response.tool_calls]})
        raw_calls = [NS(id=c.id, function=NS(name=c.name, arguments=json.dumps(c.arguments, ensure_ascii=False))) for c in response.tool_calls]
        if not kwargs.get('stream'):
            return NS(choices=[NS(message=NS(content=response.text, tool_calls=raw_calls), finish_reason='stop')])

        def chunks():
            def chunk(content=None, calls=None, finish=None):
                return NS(choices=[NS(delta=NS(content=content, tool_calls=calls), finish_reason=finish)])
            for index, call in enumerate(raw_calls):
                arguments = call.function.arguments
                targeted = call.function.name == 'distribution_analysis'
                if targeted and self.fault == 'malformed_arguments':
                    arguments = '{"name":'
                # Split JSON and Unicode at arbitrary character boundaries.
                for offset in range(0, len(arguments), 7):
                    yield chunk(calls=[NS(index=index, id=call.id if offset == 0 else None,
                        function=NS(name=call.function.name if offset == 0 else None, arguments=arguments[offset:offset+7]))])
                if targeted and self.fault == 'missing_terminal':
                    return
            for offset in range(0, len(response.text), 13):
                yield chunk(content=response.text[offset:offset+13])
            yield chunk(finish='tool_calls' if raw_calls else 'stop')
        return chunks()


@pytest.mark.parametrize('fault', ['malformed_arguments', 'missing_terminal', 'none'])
def test_main_raw_transport_normal_app_receipts_and_fail_closed(engine, tmp_path, fault):
    from data_agent.llm.client import LLMClient
    from data_agent.llm.request_policy import ONE_SHOT
    from data_agent.web.app import create_app
    from data_agent.web.agent_manager import AgentManager
    from data_agent.agent.publication.runtime import read_answer
    from data_agent.session.history import load_session
    from tests.support.publication_runtime import _NativeProductModel

    _, cfg = engine
    content = '分析上传文件，将其命名为原始金额；计算amount均值。'
    model = _NativeProductModel(content, '原始金额', 'distribution_analysis',
        {'name': '原始金额', 'columns': 'amount'},
        [{'kind': 'measurement', 'scope': {'datasets': ['原始金额'], 'metrics': ['amount'], 'quantity': 'mean'}}])
    raw = RawTransport(model, fault)
    main = LLMClient(model_id='private/offline-raw-app', transport=raw, request_policy=ONE_SHOT, max_tokens=4096)
    app = create_app()
    app.config['agent_manager'] = AgentManager(client_factory=lambda **_: main, auxiliary_client_factory=lambda: main.for_purpose())
    sid = 'raw_app_' + fault
    csv = ('amount\n' + ''.join(f'{i}\n' for i in range(1, 31))).encode()
    with app.test_client() as http:
        ticket = http.post('/api/upload', data={'file': (io.BytesIO(csv), 'amount.csv')}, content_type='multipart/form-data').get_json()
        assert ticket['sha256'] == 'sha256:' + hashlib.sha256(csv).hexdigest()
        model.ticket = ticket
        response = http.post('/api/chat', json={'session_id': sid, 'message': content, 'uploads': [ticket]})
        events = [(b.split('\n', 1)[0][7:], json.loads(b.split('\ndata: ', 1)[1]))
                  for b in response.get_data(as_text=True).split('\n\n') if b.startswith('event:')]
        durable = http.get(f'/api/sessions/{sid}/run-state').get_json()
        session = http.get(f'/api/sessions/{sid}').get_json()
        ends = [d for e, d in events if e == 'turn_end']
        assert len(ends) == 1 and ends[0]['status'] == durable['status']
        assert ends[0]['turn_id'] == durable['turn_id']
        assert any(not c['stream'] for c in raw.calls) and any(c['stream'] for c in raw.calls)
        assert all(c['num_retries'] == 0 for c in raw.calls)
        if fault == 'missing_terminal':
            assert ends[0]['status'] == 'failed'
        else:
            assert ends[0]['status'] == 'completed'
        saved = load_session(sid)
        answers = [m for m in saved['messages'] if m.get('answer_ref')]
        if fault == 'missing_terminal':
            assert not answers
        else:
            answer = read_answer(sid, answers[-1]['answer_ref'])
            body = ''.join(d['text'] for e, d in events if e == 'text_delta')
            assert body == answer['body'] == ends[0]['reply_content'] == answers[-1]['content']
            claims = answer['source_snapshot']['claims']
            means = [c for c in claims if c.get('target', {}).get('tool') == 'distribution_analysis']
            if fault == 'malformed_arguments':
                assert not means
                assert all(o['status'] != 'answered' for o in answer['requirement_outcomes'])
            else:
                assert any(c['value'] == 15.5 for c in means)
                assert all(o['status'] == 'answered' for o in answer['requirement_outcomes'])
                exported = http.post(f'/api/sessions/{sid}/export-reply', json={'reply_id': ends[0]['reply_id'], 'format': 'markdown'}).get_json()
                path = cfg.sessions_resolved / sid / exported['artifact_path'].split(sid + '/', 1)[-1]
                # Export reference is app-relative; retain exact accepted body.
                if not path.is_file():
                    path = cfg.project_root / exported['artifact_path']
                assert body in path.read_text('utf-8')
    (tmp_path / 'raw-app-evidence.json').write_text(json.dumps({'calls': raw.calls, 'events': events,
        'durable': durable, 'session': session, 'provider_calls': 0, 'remote_mcp_calls': 0}, ensure_ascii=False, indent=2), encoding='utf-8')
