(() => {
    const state = { filename: '', sessionId: '', turnId: '', blocks: [], proposal: null, running: false };
    const byId = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    const setStatus = (text) => { byId('status').textContent = text; };
    function showError(message = '') { byId('error').textContent = message; byId('error').classList.toggle('visible', Boolean(message)); }
    function updateUrl() {
        if (!state.sessionId || !state.turnId) return;
        const url = new URL(window.location.href); url.searchParams.set('session_id', state.sessionId); url.searchParams.set('turn_id', state.turnId);
        history.replaceState({}, '', url); byId('run-id').textContent = `session ${state.sessionId} · turn ${state.turnId}`;
    }
    function progress(label) {
        byId('progress').classList.add('visible'); const item = document.createElement('div'); item.className = 'progress-item';
        item.innerHTML = `<span class="dot"></span><span>${escapeHtml(label)}</span>`; byId('progress-list').appendChild(item);
    }
    function renderBlocks(blocks) {
        state.blocks = blocks || []; byId('answer').innerHTML = state.blocks.map((block) => {
            const limits = (block.limitations || []).length ? `<ul>${block.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '';
            return `<article class="answer-block"><h2>${escapeHtml(block.headline)}</h2><p>${escapeHtml(block.narrative)}</p>${limits}</article>`;
        }).join('');
    }
    function renderProposal(proposal) {
        state.proposal = proposal; byId('confirmation').hidden = false;
        byId('choice-list').innerHTML = (proposal.options || []).map((option) => {
            const s = option.sensitivity || {};
            return `<article class="choice-card"><h3>${escapeHtml(option.label)}</h3><p>格式 ${escapeHtml(option.date_format)}<br>解析 ${escapeHtml(s.parsed_non_null)}/${escapeHtml(s.source_non_null)}；新增缺失 ${escapeHtml(s.new_missing)}<br>范围 ${escapeHtml(s.min_time)} 至 ${escapeHtml(s.max_time)}；与另一候选不同 ${escapeHtml(s.divergent_values)} 个值</p><button type="button" data-option-key="${escapeHtml(option.option_key)}">选择${escapeHtml(option.label)}</button></article>`;
        }).join('');
        byId('choice-list').querySelectorAll('[data-option-key]').forEach((button) => button.addEventListener('click', () => resolveChoice(button.dataset.optionKey)));
    }
    async function uploadSelected() {
        const file = byId('file').files[0]; if (!file) throw new Error('请先选择数据文件。');
        const form = new FormData(); form.append('file', file); setStatus('正在上传');
        const response = await fetch('/api/upload', { method: 'POST', body: form }); const body = await response.json();
        if (!response.ok) throw new Error(body.error || '上传失败'); state.filename = body.filename; byId('file-state').textContent = `已上传：${body.filename}`;
    }
    function handleEvent(event, data) {
        const labels = { commitment_snapshot: '转换承诺已冻结', tool_started: '正在诊断日期语义', tool_finished: '转换事实已生成', outcome_snapshot: '已计算当前终态', final_block_delta: '正在发布血缘结果' };
        if (labels[event]) progress(labels[event]);
        if (event === 'turn_started') { state.sessionId = data.session_id; state.turnId = data.turn_id; updateUrl(); progress(data.resumed ? '语义选择已接收，恢复转换' : '转换会话已建立'); }
        else if (event === 'user_input_required') { renderProposal(data); setStatus('等待日期语义选择'); progress('检测到真正的日期顺序歧义'); }
        else if (event === 'final_block_delta') renderBlocks([...state.blocks, data.block]);
        else if (event === 'turn_completed') { byId('confirmation').hidden = true; setStatus('转换完成'); progress('转换结果已持久化'); }
        else if (event === 'turn_failed') throw new Error(data.message || data.error_code || '转换失败');
    }
    async function consumeSse(response) {
        if (!response.ok || !response.body) throw new Error('无法建立转换事件流。');
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
        while (true) { const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); const frames = buffer.split('\n\n'); buffer = frames.pop() || '';
            for (const frame of frames) { let event = ''; let data = null; for (const line of frame.split('\n')) { if (line.startsWith('event: ')) event = line.slice(7).trim(); if (line.startsWith('data: ')) data = JSON.parse(line.slice(6)); } if (event && data) handleEvent(event, data); }
        }
    }
    async function run() {
        if (state.running) return; state.running = true; byId('run').disabled = true; showError(''); state.blocks = []; state.proposal = null; renderBlocks([]); byId('confirmation').hidden = true; byId('progress-list').innerHTML = ''; byId('progress').classList.remove('visible');
        try { if (!state.filename) await uploadSelected(); setStatus('转换进行中'); const response = await fetch('/api/v2/transform-dates', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename: state.filename, date_column: byId('date-column').value.trim(), question: byId('question').value.trim() }) }); await consumeSse(response); }
        catch (error) { showError(error.message); setStatus('转换失败'); }
        finally { state.running = false; byId('run').disabled = false; }
    }
    async function resolveChoice(optionKey) {
        if (state.running || !state.proposal) return; state.running = true; showError(''); byId('choice-list').querySelectorAll('button').forEach((button) => { button.disabled = true; }); setStatus('正在应用选择');
        try { const proposal = state.proposal; const response = await fetch('/api/v2/transform-dates/resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: state.sessionId, turn_id: state.turnId, proposal_id: proposal.proposal_id, option_key: optionKey, expected_parent_version_id: proposal.parent_version_id, expected_parent_content_fingerprint: proposal.parent_content_fingerprint }) }); await consumeSse(response); }
        catch (error) { showError(error.message); setStatus('确认失败'); byId('choice-list').querySelectorAll('button').forEach((button) => { button.disabled = false; }); }
        finally { state.running = false; }
    }
    async function restore() {
        const params = new URLSearchParams(window.location.search); state.sessionId ||= params.get('session_id') || ''; state.turnId ||= params.get('turn_id') || '';
        if (!state.sessionId || !state.turnId) { showError('当前页面没有可恢复的转换会话。'); return; }
        showError(''); setStatus('正在恢复'); const response = await fetch(`/api/v2/sessions/${encodeURIComponent(state.sessionId)}/turns/${encodeURIComponent(state.turnId)}`); const body = await response.json();
        if (!response.ok) { showError(body.error || '恢复失败'); setStatus('恢复失败'); return; }
        const context = body.request_context || {}; if (context.filename) { state.filename = context.filename; byId('file-state').textContent = `已关联：${context.filename}`; }
        if (context.date_column) byId('date-column').value = context.date_column; if (context.question) byId('question').value = context.question; renderBlocks(body.blocks || []); updateUrl();
        if (body.status === 'draft' && body.transformation?.status === 'pending') { renderProposal(body.transformation.proposal); setStatus('已恢复：等待日期语义选择'); }
        else { byId('confirmation').hidden = true; setStatus('已从持久化消息块恢复'); }
    }
    byId('run').addEventListener('click', run); byId('restore').addEventListener('click', restore); byId('file').addEventListener('change', () => { state.filename = ''; byId('file-state').textContent = '等待上传'; });
    if (new URLSearchParams(window.location.search).has('session_id')) restore();
})();
