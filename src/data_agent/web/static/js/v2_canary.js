(() => {
    const state = {
        filename: '',
        sessionId: '',
        turnId: '',
        blocks: [],
        running: false,
    };
    const byId = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

    function setStatus(text) { byId('status').textContent = text; }
    function showError(message = '') {
        const node = byId('error');
        node.textContent = message;
        node.classList.toggle('visible', Boolean(message));
    }
    function updateUrl() {
        if (!state.sessionId || !state.turnId) return;
        const url = new URL(window.location.href);
        url.searchParams.set('session_id', state.sessionId);
        url.searchParams.set('turn_id', state.turnId);
        history.replaceState({}, '', url);
        byId('run-id').textContent = `session ${state.sessionId} · turn ${state.turnId}`;
    }
    function renderBlocks(blocks) {
        state.blocks = blocks || [];
        byId('answer').innerHTML = state.blocks.map((block) => {
            const limits = (block.limitations || []).length
                ? `<ul>${block.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '';
            return `<article class="answer-block" data-block-id="${escapeHtml(block.block_id)}">
                <h2>${escapeHtml(block.headline)}</h2>
                <p>${escapeHtml(block.narrative)}</p>${limits}
            </article>`;
        }).join('');
    }
    function progress(label) {
        byId('progress').classList.add('visible');
        const item = document.createElement('div');
        item.className = 'progress-item';
        item.innerHTML = `<span class="dot"></span><span>${escapeHtml(label)}</span>`;
        byId('progress-list').appendChild(item);
    }
    async function uploadSelected() {
        const file = byId('file').files[0];
        if (!file) throw new Error('请先选择分析文件。');
        const form = new FormData();
        form.append('file', file);
        setStatus('正在上传');
        const response = await fetch('/api/upload', { method: 'POST', body: form });
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || '上传失败');
        state.filename = body.filename;
        byId('file-state').textContent = `已上传：${body.filename}`;
    }
    async function consumeSse(response) {
        if (!response.ok || !response.body) throw new Error('无法建立 V2 分析流。');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split('\n\n');
            buffer = frames.pop() || '';
            for (const frame of frames) {
                let event = '';
                let data = null;
                for (const line of frame.split('\n')) {
                    if (line.startsWith('event: ')) event = line.slice(7).trim();
                    if (line.startsWith('data: ')) data = JSON.parse(line.slice(6));
                }
                if (event && data) handleEvent(event, data);
            }
        }
    }
    function handleEvent(event, data) {
        const labels = {
            turn_started: '分析会话已建立', commitment_snapshot: '已确定核心分析承诺',
            tool_started: '正在执行描述统计', tool_finished: '结构化计算已完成',
            outcome_snapshot: '已计算分析终态', final_block_delta: '正在发布已校准答案',
        };
        if (labels[event]) progress(labels[event]);
        if (event === 'turn_started') {
            state.sessionId = data.session_id; state.turnId = data.turn_id; updateUrl();
        } else if (event === 'final_block_delta') {
            renderBlocks([...state.blocks, data.block]);
        } else if (event === 'turn_completed') {
            setStatus('分析完成'); progress('最终答案已持久化');
        } else if (event === 'turn_failed') {
            throw new Error(data.message || data.error_code || 'V2 分析失败');
        }
    }
    async function run() {
        if (state.running) return;
        state.running = true; byId('run').disabled = true; showError('');
        byId('progress-list').innerHTML = ''; byId('progress').classList.remove('visible'); renderBlocks([]);
        try {
            if (!state.filename) await uploadSelected();
            setStatus('分析进行中');
            const response = await fetch('/api/v2/describe', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: state.filename,
                    metric: byId('metric').value.trim(),
                    question: byId('question').value.trim(),
                }),
            });
            await consumeSse(response);
        } catch (error) { showError(error.message); setStatus('分析失败'); }
        finally { state.running = false; byId('run').disabled = false; }
    }
    async function restore() {
        const params = new URLSearchParams(window.location.search);
        state.sessionId = state.sessionId || params.get('session_id') || '';
        state.turnId = state.turnId || params.get('turn_id') || '';
        if (!state.sessionId || !state.turnId) { showError('当前页面没有可恢复的 V2 会话。'); return; }
        showError(''); setStatus('正在恢复');
        const response = await fetch(`/api/v2/sessions/${encodeURIComponent(state.sessionId)}/turns/${encodeURIComponent(state.turnId)}`);
        const body = await response.json();
        if (!response.ok) { showError(body.error || '恢复失败'); setStatus('恢复失败'); return; }
        renderBlocks(body.blocks || []); updateUrl(); setStatus('已从持久化消息块恢复');
    }
    byId('run').addEventListener('click', run);
    byId('restore').addEventListener('click', restore);
    byId('file').addEventListener('change', () => { state.filename = ''; byId('file-state').textContent = '等待上传'; });
    if (new URLSearchParams(window.location.search).has('session_id')) restore();
})();
