(() => {
    const state = {
        filename: '', sessionId: '', turnId: '', runId: '', analysisKind: 'descriptive',
        blocks: [], artifacts: [], running: false, stoppable: false,
        stopRequested: false, awaitingConfirmation: false, proposal: null,
        activityCount: 0, queuedSteer: null, queuedTargetTurnId: '', terminalStatus: '',
        pendingSteerRequest: null,
    };
    const byId = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? '').replace(/&/g, '&amp;')
        .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    const setStatus = (text) => { byId('status').textContent = text; };

    function showError(message = '') {
        byId('error').textContent = message;
        byId('error').classList.toggle('visible', Boolean(message));
    }

    function updateUrl() {
        if (!state.sessionId || !state.turnId) return;
        const url = new URL(window.location.href);
        url.searchParams.set('session_id', state.sessionId);
        url.searchParams.set('turn_id', state.turnId);
        history.replaceState({}, '', url);
        const run = state.runId ? ` · run ${state.runId}` : '';
        byId('run-id').textContent = `session ${state.sessionId} · turn ${state.turnId}${run}`;
    }

    function showKindFields() {
        state.analysisKind = byId('analysis-kind').value;
        document.querySelectorAll('[data-kinds]').forEach((node) => {
            node.hidden = !node.dataset.kinds.split(' ').includes(state.analysisKind);
        });
    }

    function activity(label) {
        state.activityCount += 1;
        byId('activity-count').textContent = String(state.activityCount);
        const item = document.createElement('div');
        item.className = 'activity-item';
        item.innerHTML = `<span class="dot"></span><span>${escapeHtml(label)}</span>`;
        byId('activity-list').appendChild(item);
    }

    function canContinueSteer() {
        return !state.running
            && state.queuedSteer?.status === 'queued'
            && ['completed', 'failed'].includes(state.terminalStatus);
    }

    function updateRunControls() {
        const stop = byId('stop');
        const steer = byId('steer');
        const continueSteer = byId('continue-steer');
        stop.hidden = !state.running;
        stop.disabled = !state.stoppable || state.stopRequested;
        steer.hidden = !state.running;
        steer.disabled = !state.stoppable || state.stopRequested || !state.runId;
        continueSteer.hidden = !canContinueSteer();
        continueSteer.disabled = !canContinueSteer();
        byId('run').disabled = state.running;
        byId('restore').disabled = state.running;
    }

    const artifactUrl = (id) => `/api/v2/sessions/${encodeURIComponent(state.sessionId)}/artifacts/${encodeURIComponent(id)}`;

    function chartHtml(artifact) {
        return `<figure class="chart-shell" data-chart-id="${escapeHtml(artifact.chart_id)}" data-chart-loaded="false"><figcaption>${escapeHtml(artifact.title)}</figcaption><iframe class="chart-frame" title="${escapeHtml(artifact.title)}" src="${artifactUrl(artifact.chart_id)}" loading="eager"></iframe></figure>`;
    }

    function bindCharts() {
        byId('answer').querySelectorAll('.chart-frame').forEach((frame) => {
            const wait = (attempt = 0) => {
                try {
                    if (frame.contentDocument?.querySelector('.plotly-graph-div .main-svg')) {
                        frame.closest('.chart-shell').dataset.chartLoaded = 'true';
                        return;
                    }
                } catch (_) {}
                if (attempt === 20 && frame.dataset.navigationRetried !== 'true') {
                    frame.dataset.navigationRetried = 'true';
                    const retry = new URL(frame.src, window.location.origin);
                    retry.searchParams.set('_retry', String(Date.now()));
                    frame.src = retry.toString();
                    window.setTimeout(() => wait(0), 50);
                    return;
                }
                if (attempt < 100) window.setTimeout(() => wait(attempt + 1), 50);
            };
            frame.addEventListener('load', () => wait(), {once: true});
            wait();
        });
    }

    function renderBlocks(blocks, artifacts = state.artifacts, showCharts = true) {
        state.blocks = blocks || [];
        state.artifacts = artifacts || [];
        const visible = showCharts ? state.artifacts : [];
        const artifactById = new Map(visible.map((item) => [item.chart_id, item]));
        const consumed = new Set();
        const body = state.blocks.map((block) => {
            const charts = (block.chart_refs || []).map((id) => {
                const artifact = artifactById.get(id);
                if (!artifact) return '';
                consumed.add(id);
                return chartHtml(artifact);
            }).join('');
            const limits = (block.limitations || []).length
                ? `<ul>${block.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '';
            return `<article class="answer-block" data-block-type="${escapeHtml(block.block_type)}" data-calibration="${escapeHtml(block.calibration)}"><h2>${escapeHtml(block.headline)}</h2><p>${escapeHtml(block.narrative)}</p>${charts}${limits}</article>`;
        }).join('');
        const extra = visible.filter((item) => !consumed.has(item.chart_id));
        const supplement = extra.length
            ? `<section class="supplemental"><h2>补充图表</h2>${extra.map(chartHtml).join('')}</section>` : '';
        byId('answer').innerHTML = body + supplement;
        bindCharts();
    }

    async function uploadSelected() {
        const file = byId('file').files[0];
        if (!file) throw new Error('请先选择数据文件。');
        const form = new FormData();
        form.append('file', file);
        setStatus('正在上传');
        const response = await fetch('/api/upload', {method: 'POST', body: form});
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || '上传失败');
        state.filename = body.filename;
        byId('file-state').textContent = `已上传：${body.filename}`;
    }

    function payload() {
        const kind = byId('analysis-kind').value;
        const value = {analysis_kind: kind, filename: state.filename, question: byId('question').value.trim()};
        if (['descriptive', 'group_comparison', 'time_trend', 'forecast', 'multi_finding_synthesis', 'exploratory_python'].includes(kind)) value.metric = byId('metric').value.trim();
        if (kind === 'factor_relationship') {
            value.target = byId('target').value.trim();
            value.features = byId('features').value.split(',').map((item) => item.trim()).filter(Boolean);
            value.analysis_unit = byId('analysis-unit').value.trim();
            value.time_field = byId('time-field').value.trim();
        }
        if (kind === 'date_transformation') value.date_column = byId('date-column').value.trim();
        if (['group_comparison', 'multi_finding_synthesis'].includes(kind)) {
            value.group = byId('group').value.trim();
            value.analysis_unit = byId('analysis-unit').value.trim();
        }
        if (['time_trend', 'forecast', 'multi_finding_synthesis'].includes(kind)) {
            value.time_field = byId('time-field').value.trim();
            value.frequency = byId('frequency').value;
            value.aggregation = byId('aggregation').value;
        }
        if (kind === 'forecast') value.horizon = Number(byId('horizon').value);
        if (['group_comparison', 'time_trend', 'forecast', 'multi_finding_synthesis'].includes(kind)) {
            value.recommendation_intent = byId('recommendation-intent').value;
            value.action_risk = byId('action-risk').value;
            value.reversible = byId('reversible').checked;
        }
        if (kind === 'exploratory_python') {
            value.purpose = byId('purpose').value.trim();
            value.code = byId('code').value;
        }
        return value;
    }

    function toolLabel(data, finished = false) {
        const names = {describe_numeric: '描述统计', factor_relationship: '因素关系', date_transform: '日期转换', group_comparison: '双组比较', time_trend: '历史趋势', forecast: '回测预测', exploratory_python: '探索性 Python'};
        const label = names[data.name] || data.name || '结构化分析';
        return finished ? `${label}已完成` : `正在执行${label}`;
    }

    function renderConfirmation(proposal) {
        state.proposal = proposal;
        state.awaitingConfirmation = true;
        state.terminalStatus = 'awaiting_input';
        byId('confirmation').classList.add('visible');
        byId('confirmation-message').textContent = '日期字段存在多种无损解释。请选择符合业务语义的格式。';
        byId('confirmation-options').innerHTML = (proposal.options || []).map((option) => `<button type="button" data-option-key="${escapeHtml(option.option_key)}">${escapeHtml(option.label)}</button>`).join('');
        byId('confirmation-options').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => resolveDate(button.dataset.optionKey)));
        setStatus('等待日期语义确认');
    }

    function hideConfirmation() {
        state.proposal = null;
        state.awaitingConfirmation = false;
        byId('confirmation').classList.remove('visible');
        byId('confirmation-options').innerHTML = '';
    }

    function handleEvent(event, data) {
        if (event === 'turn_started') {
            activity('分析会话已建立');
            state.sessionId = data.session_id || state.sessionId;
            state.turnId = data.turn_id || state.turnId;
            state.runId = data.run_id || '';
            state.terminalStatus = 'running';
            updateUrl();
        } else if (event === 'commitment_snapshot') {
            state.stoppable = true;
            updateRunControls();
            activity('分析承诺已冻结');
        } else if (event === 'steer_received') {
            state.queuedSteer = data;
            setStatus('消息已排队，当前分析继续运行');
            activity('下一轮消息已持久化');
            updateRunControls();
        } else if (event === 'tool_started') activity(toolLabel(data));
        else if (event === 'tool_finished') activity(toolLabel(data, true));
        else if (event === 'artifact_created') {
            state.artifacts = [...state.artifacts, data.artifact];
            activity('图表产物已持久化');
        } else if (event === 'artifact_failed') activity('图表不可用，继续发布文本结论');
        else if (event === 'supplemental_artifact_created') activity('探索性补充已持久化');
        else if (event === 'outcome_snapshot') activity(data.publishable ? '核心承诺已达到可发布终态' : '核心承诺等待更多事实');
        else if (event === 'user_input_required') {
            state.stoppable = false;
            updateRunControls();
            renderConfirmation(data);
            activity('等待用户确认日期语义');
        } else if (event === 'final_block_delta') {
            renderBlocks([...state.blocks, data.block], state.artifacts, false);
            activity('正在发布校准答案');
        } else if (event === 'turn_completed') {
            state.stoppable = false;
            state.terminalStatus = 'completed';
            hideConfirmation();
            setStatus('分析完成');
            activity('最终答案已持久化');
        } else if (event === 'turn_interrupted') {
            state.stoppable = false;
            state.stopRequested = true;
            state.queuedSteer = null;
            state.queuedTargetTurnId = '';
            state.terminalStatus = 'interrupted';
            hideConfirmation();
            setStatus('已停止');
            activity('停止事实已持久化，运行已在安全边界结束');
        } else if (event === 'turn_failed') {
            state.terminalStatus = 'failed';
            throw new Error(data.message || data.error_code || '分析失败');
        }
    }

    async function consumeSse(response) {
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.error || '无法建立统一分析事件流。');
        }
        if (!response.body) throw new Error('统一分析事件流不可用。');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const {value, done} = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, {stream: true});
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

    function resetRunView() {
        showError('');
        hideConfirmation();
        state.blocks = [];
        state.artifacts = [];
        state.runId = '';
        state.terminalStatus = '';
        renderBlocks([]);
        state.activityCount = 0;
        byId('activity-count').textContent = '0';
        byId('activity-list').innerHTML = '';
    }

    function afterCurrentStreamCloses() {
        return new Promise((resolve) => window.setTimeout(resolve, 100));
    }

    async function executeAnalysis(requestBody, {consumingSteer = false} = {}) {
        if (state.running) return;
        state.running = true;
        state.stoppable = false;
        state.stopRequested = false;
        resetRunView();
        updateRunControls();
        let autoContinue = false;
        try {
            setStatus(consumingSteer ? '正在开始排队的下一轮' : '分析进行中');
            const response = await fetch('/api/v2/analyze', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestBody),
            });
            if (response.ok && consumingSteer) {
                state.queuedSteer = null;
                state.queuedTargetTurnId = '';
            }
            await consumeSse(response);
            renderBlocks(state.blocks, state.artifacts, true);
            if (state.awaitingConfirmation) setStatus('等待日期语义确认');
            autoContinue = state.terminalStatus === 'completed' && state.queuedSteer?.status === 'queued';
        } catch (error) {
            showError(error.message);
            setStatus('分析失败，可修改输入后重试');
        } finally {
            state.running = false;
            state.stoppable = false;
            updateRunControls();
        }
        if (autoContinue) {
            await afterCurrentStreamCloses();
            await runQueuedSteer();
        }
    }

    async function run() {
        if (state.running) return;
        try {
            if (!state.filename) await uploadSelected();
        } catch (error) {
            showError(error.message);
            setStatus('上传失败');
            return;
        }
        await executeAnalysis(payload());
    }

    async function sendSteer() {
        if (!state.running || !state.stoppable || state.stopRequested || !state.runId) return;
        const message = byId('question').value.trim();
        if (!message) {
            showError('请输入要发送到下一轮的问题。');
            return;
        }
        const pending = state.pendingSteerRequest;
        const clientRequestId = pending
            && pending.runId === state.runId
            && pending.message === message
            ? pending.clientRequestId
            : `client_${crypto.randomUUID().replaceAll('-', '')}`;
        state.pendingSteerRequest = {runId: state.runId, message, clientRequestId};
        byId('steer').disabled = true;
        showError('');
        setStatus('正在持久化下一轮消息');
        try {
            const response = await fetch('/api/v2/runs/steer', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: state.sessionId, turn_id: state.turnId,
                    expected_run_id: state.runId, client_request_id: clientRequestId,
                    message,
                }),
            });
            const body = await response.json();
            if (!response.ok) throw new Error(body.error || '下一轮消息排队失败');
            state.pendingSteerRequest = null;
            state.queuedSteer = body;
            state.queuedTargetTurnId = '';
            activity('下一轮消息已持久化');
            setStatus('消息已排队，当前分析继续运行');
        } catch (error) {
            showError(error.message);
            setStatus('排队失败，当前分析仍在运行');
        } finally {
            updateRunControls();
        }
    }

    async function runQueuedSteer() {
        if (state.running || state.queuedSteer?.status !== 'queued') return;
        const queued = state.queuedSteer;
        state.queuedTargetTurnId ||= `turn_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`;
        byId('question').value = queued.message;
        await executeAnalysis({
            session_id: state.sessionId,
            turn_id: state.queuedTargetTurnId,
            steer_id: queued.steer_id,
        }, {consumingSteer: true});
    }

    async function stop() {
        if (!state.running || !state.stoppable || state.stopRequested) return;
        state.stopRequested = true;
        updateRunControls();
        setStatus('正在持久化停止请求');
        try {
            const response = await fetch('/api/v2/runs/stop', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({session_id: state.sessionId, turn_id: state.turnId}),
            });
            const body = await response.json();
            if (!response.ok) throw new Error(body.error || '停止请求失败');
            state.queuedSteer = null;
            state.queuedTargetTurnId = '';
            state.pendingSteerRequest = null;
            activity('停止事实已持久化');
            setStatus('正在安全停止');
        } catch (error) {
            state.stopRequested = false;
            updateRunControls();
            showError(error.message);
            setStatus('停止失败，分析仍在运行');
        }
    }

    async function resolveDate(optionKey) {
        if (state.running || !state.proposal) return;
        state.running = true;
        updateRunControls();
        showError('');
        setStatus('正在应用已确认语义');
        let autoContinue = false;
        try {
            const proposal = state.proposal;
            const response = await fetch('/api/v2/transform-dates/resolve', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: state.sessionId, turn_id: state.turnId,
                    proposal_id: proposal.proposal_id, option_key: optionKey,
                    expected_parent_version_id: proposal.parent_version_id,
                    expected_parent_content_fingerprint: proposal.parent_content_fingerprint,
                }),
            });
            await consumeSse(response);
            renderBlocks(state.blocks, state.artifacts, true);
            autoContinue = state.terminalStatus === 'completed' && state.queuedSteer?.status === 'queued';
        } catch (error) {
            showError(error.message);
            setStatus('确认失败，可重新选择');
        } finally {
            state.running = false;
            updateRunControls();
        }
        if (autoContinue) {
            await afterCurrentStreamCloses();
            await runQueuedSteer();
        }
    }

    function restoreFields(context) {
        if (context.analysis_kind) {
            byId('analysis-kind').value = context.analysis_kind;
            showKindFields();
        }
        const mappings = {metric: 'metric', target: 'target', analysis_unit: 'analysis-unit', time_field: 'time-field', date_column: 'date-column', group: 'group', frequency: 'frequency', aggregation: 'aggregation', horizon: 'horizon', recommendation_intent: 'recommendation-intent', action_risk: 'action-risk', purpose: 'purpose', question: 'question'};
        Object.entries(mappings).forEach(([key, id]) => { if (context[key]) byId(id).value = context[key]; });
        if (context.features) byId('features').value = context.features;
        if (context.reversible) byId('reversible').checked = context.reversible === 'true';
        if (context.filename) {
            state.filename = context.filename;
            byId('file-state').textContent = `已关联：${context.filename}`;
        }
    }

    async function restore() {
        const params = new URLSearchParams(window.location.search);
        state.sessionId ||= params.get('session_id') || '';
        state.turnId ||= params.get('turn_id') || '';
        if (!state.sessionId || !state.turnId) {
            showError('当前页面没有可恢复的 V2 分析。');
            return;
        }
        showError('');
        setStatus('正在恢复');
        const response = await fetch(`/api/v2/sessions/${encodeURIComponent(state.sessionId)}/turns/${encodeURIComponent(state.turnId)}`);
        const body = await response.json();
        if (!response.ok) {
            showError(body.error || '恢复失败');
            setStatus('恢复失败');
            return;
        }
        restoreFields(body.request_context || {});
        state.artifacts = body.artifacts || [];
        renderBlocks(body.blocks || [], state.artifacts);
        if (body.transformation?.status==='pending') renderConfirmation(body.transformation.proposal);
        state.queuedSteer = [...(body.steers || [])].reverse().find((item) => item.status === 'queued') || null;
        state.queuedTargetTurnId = '';
        state.terminalStatus = body.status === 'finalized' ? 'completed' : body.status;
        updateUrl();
        updateRunControls();
        if (body.status === 'interrupted') setStatus('已停止');
        else if (canContinueSteer()) setStatus('有已持久化的下一轮消息待继续');
        else setStatus(state.awaitingConfirmation ? '等待日期语义确认' : '已从持久化消息块恢复');
    }

    byId('analysis-kind').addEventListener('change', showKindFields);
    byId('run').addEventListener('click', run);
    byId('steer').addEventListener('click', sendSteer);
    byId('continue-steer').addEventListener('click', runQueuedSteer);
    byId('stop').addEventListener('click', stop);
    byId('restore').addEventListener('click', restore);
    byId('file').addEventListener('change', () => {
        state.filename = '';
        byId('file-state').textContent = '等待上传';
    });
    showKindFields();
    updateRunControls();
    if (new URLSearchParams(window.location.search).has('session_id')) restore();
})();
