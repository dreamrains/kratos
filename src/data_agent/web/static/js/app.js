/* Data Agent Web GUI — Alpine.js chat application */

function chatApp() {
    return {
        sidebarCollapsed: false,
        sessions: [],
        sessionSearch: '',
        currentSessionId: null,
        turns: [],
        inputText: '',
        isLoading: false,
        uploadedFile: null,
        connectionError: '',

        // Objects
        objects: [],
        activeObjectName: '',
        showNewObjectForm: false,
        newObjectName: '',
        expandedObjects: {},

        // Token usage
        tokenPct: 0,

        // Model
        modelName: '',
        availableModels: [],

        // Popover
        activePopover: null,

        // Config modal
        configModal: { show: false, model_id: '', api_base: '', api_key: '', has_key: false, saving: false },

        // Artifacts modal
        artifactsModal: { show: false, sessionId: '', items: [] },

        // Tasks
        tasks: [],
        tasksExpanded: true,

        // Confirmation resuming state
        isResuming: false,

        async init() {
            await Promise.all([
                this.loadSessions(),
                this.loadObjects(),
                this.loadModelInfo(),
                this.loadTasks(),
            ]);
            // Close popover on outside click
            document.addEventListener('click', (e) => {
                if (this.activePopover && !e.target.closest('[data-popover]')) {
                    this.activePopover = null;
                }
            });
        },

        get filteredSessions() {
            if (!this.sessionSearch) return this.sessions;
            const q = this.sessionSearch.toLowerCase();
            return this.sessions.filter(s =>
                (s.summary || '').toLowerCase().includes(q) ||
                s.session_id.toLowerCase().includes(q)
            );
        },

        get objectGroups() {
            const groups = {};
            for (const s of this.sessions) {
                const key = s.object_name || '';
                if (!groups[key]) groups[key] = [];
                groups[key].push(s);
            }
            return groups;
        },

        get unboundSessions() {
            return this.sessions.filter(s => !s.object_name);
        },

        get activeTasks() {
            return this.tasks.filter(t => t.status !== 'deleted');
        },

        get taskProgress() {
            const active = this.activeTasks;
            const done = active.filter(t => t.status === 'completed').length;
            return `${done}/${active.length}`;
        },

        // --- Model ---

        async loadModelInfo() {
            try {
                const res = await fetch('/api/models');
                const data = await res.json();
                this.modelName = data.current || 'gpt-4o';
                this.availableModels = data.models || [this.modelName];
            } catch {
                this.modelName = 'gpt-4o';
                this.availableModels = [this.modelName];
            }
        },

        // --- Config ---

        async loadConfig() {
            try {
                const res = await fetch('/api/config');
                const data = await res.json();
                this.configModal = {
                    show: true,
                    model_id: data.model_id || '',
                    api_base: data.api_base || '',
                    api_key: '',
                    has_key: data.has_key,
                    key_masked: data.api_key_masked || '',
                    saving: false,
                };
            } catch {
                this.configModal.show = true;
                this.configModal.saving = false;
            }
        },

        async saveConfig() {
            this.configModal.saving = true;
            try {
                const body = {};
                if (this.configModal.model_id) body.model_id = this.configModal.model_id;
                if (this.configModal.api_base !== undefined) body.api_base = this.configModal.api_base;
                if (this.configModal.api_key) body.api_key = this.configModal.api_key;
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                this.modelName = this.configModal.model_id || this.modelName;
                this.configModal.show = false;
            } catch (e) {
                alert('Save failed: ' + e.message);
            }
            this.configModal.saving = false;
        },

        // --- Sessions ---

        async loadSessions() {
            try {
                const res = await fetch('/api/sessions');
                this.sessions = await res.json();
                this.connectionError = '';
            } catch (e) {
                this.connectionError = 'Failed to load sessions';
            }
        },

        async newSession() {
            if (this.isLoading && !confirm('A task is running. Start new session anyway?')) return;
            this.currentSessionId = null;
            this.turns = [];
            this.activeObjectName = '';
            this.tokenPct = 0;
        },

        async switchSession(sessionId) {
            if (this.isLoading && !confirm('A task is running. Switch session anyway?')) return;
            this.currentSessionId = sessionId;
            this.turns = [];
            this.tokenPct = 0;
            try {
                const res = await fetch(`/api/sessions/${sessionId}`);
                const data = await res.json();
                if (data.messages) this.turns = this._reconstructTurns(data.messages);
                this.activeObjectName = data.object_name || '';
                this.connectionError = '';
            } catch {
                this.connectionError = 'Failed to load session';
            }
            this._scrollToBottom();
        },

        async deleteSession(sessionId) {
            if (this.isLoading && this.currentSessionId === sessionId) {
                if (!confirm('A task is running on this session. Delete anyway?')) return;
            } else if (!confirm('Delete this session?')) return;
            await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
            if (this.currentSessionId === sessionId) {
                this.currentSessionId = null;
                this.turns = [];
                this.tokenPct = 0;
            }
            await this.loadSessions();
        },

        // --- Objects ---

        async loadObjects() {
            try {
                const res = await fetch('/api/objects');
                this.objects = await res.json();
            } catch {}
        },

        async createObject() {
            const name = this.newObjectName.trim();
            if (!name) return;
            try {
                const res = await fetch('/api/objects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name }),
                });
                if (res.ok) {
                    this.newObjectName = '';
                    this.showNewObjectForm = false;
                    await this.loadObjects();
                } else {
                    const data = await res.json();
                    alert(data.error || 'Failed to create object');
                }
            } catch {}
        },

        async deleteObject(objectName) {
            if (!confirm(`Delete object "${objectName}"?`)) return;
            try {
                const res = await fetch(`/api/objects/${encodeURIComponent(objectName)}`, { method: 'DELETE' });
                if (res.ok) {
                    await this.loadObjects();
                    await this.loadSessions();
                } else {
                    const data = await res.json();
                    alert(data.error || 'Failed');
                }
            } catch {}
        },

        toggleObject(objectName) {
            this.expandedObjects[objectName] = !this.expandedObjects[objectName];
        },

        isObjectExpanded(objectName) {
            return !!this.expandedObjects[objectName];
        },

        // --- Artifacts ---

        async showSessionArtifacts(sessionId) {
            this.activePopover = null;
            try {
                const res = await fetch(`/api/sessions/${sessionId}/artifacts-list`);
                const items = await res.json();
                this.artifactsModal = { show: true, sessionId, items };
            } catch {
                this.artifactsModal = { show: true, sessionId, items: [] };
            }
        },

        async deleteArtifactFromModal(index) {
            if (!confirm('Delete this artifact?')) return;
            try {
                await fetch(`/api/sessions/${this.artifactsModal.sessionId}/artifacts/${index}`, { method: 'DELETE' });
                this.artifactsModal.items.splice(index, 1);
            } catch (e) {
                alert('Delete failed: ' + e.message);
            }
        },

        async exportSession(sessionId, format = 'html') {
            this.activePopover = null;
            window.open(`/api/sessions/${sessionId}/export?format=${format}`, '_blank');
        },

        // --- Tasks ---

        async loadTasks() {
            try {
                const res = await fetch('/api/tasks');
                this.tasks = await res.json();
                this.tasksExpanded = this.activeTasks.some(t => t.status === 'in_progress');
            } catch {}
        },

        async deleteTask(taskId) {
            try {
                await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
                await this.loadTasks();
            } catch {}
        },

        // --- Popover ---

        togglePopover(id, event) {
            if (event) event.stopPropagation();
            this.activePopover = this.activePopover === id ? null : id;
        },

        // --- Rewind ---

        async rewindToRound(roundIndex) {
            if (!confirm('Rewind to this point? Messages after this will be removed.')) return;
            try {
                const res = await fetch(`/api/sessions/${this.currentSessionId}/rewind`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ round: roundIndex }),
                });
                const data = await res.json();
                if (res.ok) {
                    await this.switchSession(this.currentSessionId);
                } else {
                    alert(data.error || 'Rewind failed');
                }
            } catch (e) {
                alert('Rewind failed: ' + e.message);
            }
        },

        // --- Chat ---

        async sendMessage() {
            const text = this.inputText.trim();
            if (!text || this.isLoading) return;
            this.inputText = '';
            this.isLoading = true;
            this.uploadedFile = null;
            this.connectionError = '';
            this.turns.push({ role: 'user', content: text, roundIndex: this._countUserTurns() });
            this.turns.push({
                role: 'assistant', content: '', toolCalls: [], artifacts: [],
                confirmation: null, isThinking: true, thinkingText: 'Thinking...', _copied: false,
            });
            const turn = this.turns[this.turns.length - 1];
            this._scrollToBottom();
            try {
                const body = { message: text };
                if (this.currentSessionId) body.session_id = this.currentSessionId;
                if (this.modelName) body.model_id = this.modelName;
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!response.ok) {
                    const errData = await response.json().catch(() => ({ error: response.statusText }));
                    throw new Error(errData.error || `HTTP ${response.status}`);
                }
                await this._processSSE(response, turn);
            } catch (e) {
                turn.isThinking = false;
                turn.content += `\n\n**Connection error:** ${e.message}`;
                this.connectionError = e.message;
            } finally {
                this.isLoading = false;
                await this.loadSessions();
                await this.loadTasks();
            }
        },

        async resumeConfirmation(suspensionId, userResponse) {
            if (this.isResuming) return;
            this.isResuming = true;
            const turn = this.turns[this.turns.length - 1];
            if (turn) turn.confirmation._resuming = true;
            try {
                const response = await fetch('/api/chat/resume', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: this.currentSessionId,
                        suspension_id: suspensionId,
                        user_response: userResponse,
                    }),
                });
                if (!response.ok) {
                    const errData = await response.json().catch(() => ({ error: response.statusText }));
                    throw new Error(errData.error || `HTTP ${response.status}`);
                }
                if (turn) turn.confirmation = null;
                this.turns.push({
                    role: 'assistant', content: '', toolCalls: [], artifacts: [],
                    confirmation: null, isThinking: true, thinkingText: 'Resuming...', _copied: false,
                });
                const newTurn = this.turns[this.turns.length - 1];
                this._scrollToBottom();
                await this._processSSE(response, newTurn);
            } catch (e) {
                const last = this.turns[this.turns.length - 1];
                if (last) {
                    last.isThinking = false;
                    last.content += `\n\n**Connection error:** ${e.message}`;
                }
                this.connectionError = e.message;
            } finally {
                this.isResuming = false;
                await this.loadSessions();
                await this.loadTasks();
            }
        },

        async interruptTurn() {
            if (!this.currentSessionId) return;
            try {
                await fetch('/api/chat/interrupt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: this.currentSessionId }),
                });
            } catch {}
        },

        async uploadFile(event) {
            const file = event.target.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (res.ok && data.filename) {
                    this.uploadedFile = data.filename;
                    this.inputText = this.inputText
                        ? this.inputText + `\nAnalyze file: ${data.filename}`
                        : `Analyze file: ${data.filename}`;
                } else {
                    alert(data.error || 'Upload failed');
                }
            } catch (e) {
                alert('Upload failed: ' + e.message);
            }
            event.target.value = '';
        },

        renderMarkdown(text) {
            if (!text) return '';
            try { return marked.parse(text); } catch { return text; }
        },

        async copyToClipboard(text) {
            try { await navigator.clipboard.writeText(text); } catch {
                const ta = document.createElement('textarea');
                ta.value = text; document.body.appendChild(ta);
                ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
            }
            for (let i = this.turns.length - 1; i >= 0; i--) {
                if (this.turns[i].role === 'assistant' && this.turns[i].content) {
                    this.turns[i]._copied = true;
                    setTimeout(() => { this.turns[i]._copied = false; }, 2000);
                    break;
                }
            }
        },

        artifactUrl(path) {
            return path ? '/files/' + encodeURIComponent(path) : '';
        },

        // --- SSE ---

        async _processSSE(response, turn) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                let result;
                try { result = await reader.read(); } catch {
                    turn.isThinking = false;
                    if (!turn.content) turn.content = '**Connection lost.**';
                    this.connectionError = 'Connection lost';
                    return;
                }
                const { done, value } = result;
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                let eventType = '', eventData = '';
                for (const line of lines) {
                    if (line.startsWith('event: ')) eventType = line.slice(7).trim();
                    else if (line.startsWith('data: ')) eventData = line.slice(6);
                    else if (line === '' && eventType && eventData) {
                        try { this._handleEvent(eventType, JSON.parse(eventData), turn); }
                        catch (e) { console.error('SSE event error:', type, e); }
                        eventType = ''; eventData = '';
                    }
                }
            }
            turn.isThinking = false;
            this.connectionError = '';
        },

        _handleEvent(type, data, turn) {
            switch (type) {
                case 'turn_start':
                    if (data.session_id) this.currentSessionId = data.session_id;
                    if (data.pct !== undefined) this.tokenPct = data.pct;
                    break;
                case 'llm_call_start':
                    turn.isThinking = true;
                    turn.thinkingText = `Round ${data.round} — Analyzing...`;
                    if (data.pct !== undefined) this.tokenPct = data.pct;
                    break;
                case 'text_delta':
                    turn.isThinking = false;
                    turn.content += data.text;
                    this._scrollToBottom();
                    break;
                case 'tool_call':
                    turn.isThinking = true;
                    turn.thinkingText = `Running ${data.name}...`;
                    turn.toolCalls.push({
                        tool_call_id: data.tool_call_id, name: data.name,
                        arguments: data.arguments, duration_ms: 0,
                        result_summary: '', _expanded: false,
                    });
                    break;
                case 'tool_result':
                    turn.isThinking = true;
                    turn.thinkingText = 'Processing results...';
                    const tc = turn.toolCalls.find(t => t.tool_call_id === data.tool_call_id);
                    if (tc) {
                        tc.duration_ms = data.duration_ms || 0;
                        const web = data.web || {};
                        tc.result_summary = web.summary || web.content || '';
                        if (web.artifacts) {
                            for (const art of web.artifacts) {
                                if (art.path) turn.artifacts.push(art);
                            }
                        }
                    }
                    break;
                case 'task_update':
                    this.loadTasks();
                    break;
                case 'suspended':
                    turn.isThinking = false;
                    turn.confirmation = {
                        suspension_id: data.suspension_id,
                        question: data.question,
                        options: data.options || [],
                        context: data.context || '',
                        _resuming: false,
                    };
                    break;
                case 'turn_end':
                    turn.isThinking = false;
                    if (data.pct !== undefined) this.tokenPct = data.pct;
                    break;
                case 'error':
                    turn.isThinking = false;
                    turn.content += `\n\n**Error:** ${data.message}`;
                    break;
            }
        },

        // --- Helpers ---

        _countUserTurns() {
            return this.turns.filter(t => t.role === 'user').length;
        },

        _reconstructTurns(messages) {
            const turns = [];
            let currentAssistant = null;
            let roundIndex = 0;
            for (const msg of messages) {
                if (msg.role === 'user') {
                    if (currentAssistant) { turns.push(currentAssistant); currentAssistant = null; }
                    roundIndex++;
                    turns.push({ role: 'user', content: msg.content || '', roundIndex });
                } else if (msg.role === 'assistant') {
                    if (currentAssistant) turns.push(currentAssistant);
                    currentAssistant = {
                        role: 'assistant', content: msg.content || '',
                        toolCalls: [], artifacts: [], confirmation: null,
                        isThinking: false, _copied: false,
                    };
                }
            }
            if (currentAssistant) turns.push(currentAssistant);
            return turns;
        },

        _scrollToBottom() {
            requestAnimationFrame(() => {
                const el = document.getElementById('messages-container');
                if (el) el.scrollTop = el.scrollHeight;
            });
        },
    };
}
