(() => {
    const state = { filename: '', sessionId: '', turnId: '', blocks: [], artifacts: [], running: false };
    const byId = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    const setStatus = (text) => { byId('status').textContent = text; };
    function showError(message = '') { byId('error').textContent = message; byId('error').classList.toggle('visible', Boolean(message)); }
    function updateUrl() {
        if (!state.sessionId || !state.turnId) return;
        const url = new URL(window.location.href);
        url.searchParams.set('session_id', state.sessionId); url.searchParams.set('turn_id', state.turnId);
        history.replaceState({}, '', url);
        byId('run-id').textContent = `session ${state.sessionId} · turn ${state.turnId}`;
    }
    const artifactUrl = (chartId) => `/api/v2/sessions/${encodeURIComponent(state.sessionId)}/artifacts/${encodeURIComponent(chartId)}`;
    function chartHtml(artifact) {
        return `<figure class="chart-shell" data-chart-id="${escapeHtml(artifact.chart_id)}" data-chart-loaded="false">
            <figcaption>${escapeHtml(artifact.title)}</figcaption><iframe class="chart-frame" title="${escapeHtml(artifact.title)}" src="${artifactUrl(artifact.chart_id)}" loading="eager"></iframe></figure>`;
    }
    function bindChartReadiness() {
        byId('answer').querySelectorAll('.chart-frame').forEach((frame) => {
            const waitForPlot = (attempt = 0) => {
                try {
                    if (frame.contentDocument?.querySelector('.plotly-graph-div .main-svg')) {
                        frame.closest('.chart-shell').dataset.chartLoaded = 'true'; return;
                    }
                } catch (_) { /* same-origin artifact; retry after load */ }
                if (attempt === 20 && frame.dataset.navigationRetried !== 'true') {
                    frame.dataset.navigationRetried = 'true';
                    const retryUrl = new URL(frame.src, window.location.origin);
                    retryUrl.searchParams.set('_retry', String(Date.now()));
                    frame.src = retryUrl.toString();
                    window.setTimeout(() => waitForPlot(0), 50);
                    return;
                }
                if (attempt < 100) window.setTimeout(() => waitForPlot(attempt + 1), 50);
            };
            frame.addEventListener('load', () => waitForPlot(), { once: true }); waitForPlot();
        });
    }
    function renderBlocks(blocks, artifacts = state.artifacts, showCharts = true) {
        state.blocks = blocks || []; state.artifacts = artifacts || [];
        const renderArtifacts = showCharts ? state.artifacts : [];
        const byChartId = new Map(renderArtifacts.map((item) => [item.chart_id, item]));
        const consumed = new Set();
        const body = state.blocks.map((block) => {
            const charts = (block.chart_refs || []).map((id) => { const art = byChartId.get(id); if (!art) return ''; consumed.add(id); return chartHtml(art); }).join('');
            const limits = (block.limitations || []).length ? `<ul>${block.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '';
            return `<article class="answer-block" data-block-id="${escapeHtml(block.block_id)}"><h2>${escapeHtml(block.headline)}</h2><p>${escapeHtml(block.narrative)}</p>${charts}${limits}</article>`;
        }).join('');
        const extra = renderArtifacts.filter((item) => !consumed.has(item.chart_id));
        const supplemental = extra.length ? `<section class="supplemental"><h2>补充图表</h2>${extra.map(chartHtml).join('')}</section>` : '';
        byId('answer').innerHTML = body + supplemental; bindChartReadiness();
    }
    function progress(label) {
        byId('progress').classList.add('visible');
        const item = document.createElement('div'); item.className = 'progress-item';
        item.innerHTML = `<span class="dot"></span><span>${escapeHtml(label)}</span>`; byId('progress-list').appendChild(item);
    }
    async function uploadSelected() {
        const file = byId('file').files[0]; if (!file) throw new Error('请先选择分析文件。');
        const form = new FormData(); form.append('file', file); setStatus('正在上传');
        const response = await fetch('/api/upload', { method: 'POST', body: form }); const body = await response.json();
        if (!response.ok) throw new Error(body.error || '上传失败');
        state.filename = body.filename; byId('file-state').textContent = `已上传：${body.filename}`;
    }
    function handleEvent(event, data) {
        const labels = { turn_started: '分析会话已建立', commitment_snapshot: '因素分析规范已冻结', tool_started: '正在执行稳健多变量估计', tool_finished: '结构化估计与诊断已完成', artifact_created: '系数区间图已持久化', artifact_failed: '图表不可用，继续发布文本结论', outcome_snapshot: '已计算可发布终态', final_block_delta: '正在发布已校准答案' };
        if (labels[event]) progress(labels[event]);
        if (event === 'turn_started') { state.sessionId = data.session_id; state.turnId = data.turn_id; updateUrl(); }
        else if (event === 'artifact_created') state.artifacts = [...state.artifacts, data.artifact];
        else if (event === 'final_block_delta') renderBlocks([...state.blocks, data.block], state.artifacts, false);
        else if (event === 'turn_completed') { setStatus('分析完成'); progress('最终答案已持久化'); }
        else if (event === 'turn_failed') throw new Error(data.message || data.error_code || '因素分析失败');
    }
    async function consumeSse(response) {
        if (!response.ok || !response.body) throw new Error('无法建立因素分析流。');
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
        while (true) {
            const { value, done } = await reader.read(); if (done) break;
            buffer += decoder.decode(value, { stream: true }); const frames = buffer.split('\n\n'); buffer = frames.pop() || '';
            for (const frame of frames) { let event = ''; let data = null; for (const line of frame.split('\n')) { if (line.startsWith('event: ')) event = line.slice(7).trim(); if (line.startsWith('data: ')) data = JSON.parse(line.slice(6)); } if (event && data) handleEvent(event, data); }
        }
    }
    async function run() {
        if (state.running) return; state.running = true; byId('run').disabled = true; showError('');
        byId('progress-list').innerHTML = ''; byId('progress').classList.remove('visible'); state.artifacts = []; renderBlocks([]);
        try {
            if (!state.filename) await uploadSelected(); setStatus('分析进行中');
            const features = byId('features').value.split(',').map((item) => item.trim()).filter(Boolean);
            if (!features.length) throw new Error('请至少填写一个候选因素列。');
            const response = await fetch('/api/v2/factors', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename: state.filename, target: byId('target').value.trim(), features, analysis_unit: byId('analysis-unit').value.trim(), time_field: byId('time-field').value.trim(), question: byId('question').value.trim() }) });
            await consumeSse(response);
            // Mount chart iframes only after the SSE connection has closed. This avoids
            // competing with the still-open stream for the first artifact request.
            renderBlocks(state.blocks, state.artifacts, true);
        } catch (error) { showError(error.message); setStatus('分析失败'); }
        finally { state.running = false; byId('run').disabled = false; }
    }
    async function restore() {
        const params = new URLSearchParams(window.location.search); state.sessionId ||= params.get('session_id') || ''; state.turnId ||= params.get('turn_id') || '';
        if (!state.sessionId || !state.turnId) { showError('当前页面没有可恢复的因素分析。'); return; }
        showError(''); setStatus('正在恢复');
        const response = await fetch(`/api/v2/sessions/${encodeURIComponent(state.sessionId)}/turns/${encodeURIComponent(state.turnId)}`); const body = await response.json();
        if (!response.ok) { showError(body.error || '恢复失败'); setStatus('恢复失败'); return; }
        const context = body.request_context || {}; if (context.target) byId('target').value = context.target;
        if (context.features) byId('features').value = context.features; if (context.analysis_unit) byId('analysis-unit').value = context.analysis_unit;
        byId('time-field').value = context.time_field || ''; if (context.question) byId('question').value = context.question;
        if (context.filename) { state.filename = context.filename; byId('file-state').textContent = `已关联：${context.filename}`; }
        renderBlocks(body.blocks || [], body.artifacts || []); updateUrl(); setStatus('已从持久化消息块恢复');
    }
    byId('run').addEventListener('click', run); byId('restore').addEventListener('click', restore);
    byId('file').addEventListener('change', () => { state.filename = ''; byId('file-state').textContent = '等待上传'; });
    if (new URLSearchParams(window.location.search).has('session_id')) restore();
})();
