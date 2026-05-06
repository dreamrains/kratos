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
        isUploading: false,
        isCompact: false,
        uploadedFiles: [],
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
        expandedTasks: {},
        _taskDebounceTimer: null,

        // Active tool call steps (populated during streaming)
        activeSteps: [],

        // Confirmation resuming state
        isResuming: false,

        async init() {
            await Promise.all([
                this.loadSessions(),
                this.loadObjects(),
                this.loadModelInfo(),
                this.loadTasks(),
            ]);
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
            if (!this.currentSessionId) return [];
            return this.tasks.filter(t => t.status !== 'deleted' && t.session_id === this.currentSessionId);
        },

        get taskProgress() {
            const active = this.activeTasks;
            const done = active.filter(t => t.status === 'completed').length;
            return `${done}/${active.length}`;
        },

        get popoverTargetId() {
            if (!this.activePopover) return '';
            if (this.activePopover.startsWith('s-')) return this.activePopover.slice(2);
            if (this.activePopover.startsWith('u-')) return this.activePopover.slice(2);
            return '';
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

        async compactContext() {
            if (!this.currentSessionId || this.isCompact) return;
            this.isCompact = true;
            try {
                const res = await fetch('/api/compact', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: this.currentSessionId }),
                });
                const data = await res.json();
                if (res.ok) {
                    this.turns.push({
                        role: 'assistant',
                        content: data.message || 'Context compressed.',
                        ts: Date.now(),
                    });
                } else {
                    this.turns.push({
                        role: 'assistant',
                        content: `Compression failed: ${data.error || 'unknown error'}`,
                        ts: Date.now(),
                    });
                }
            } catch (e) {
                this.turns.push({
                    role: 'assistant',
                    content: `Compression failed: ${e.message}`,
                    ts: Date.now(),
                });
            }
            this.isCompact = false;
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
                const newTasks = await res.json();
                // Force Alpine reactivity by creating new array reference
                this.tasks = [...newTasks];
                // Auto-expand if any in-progress tasks
                if (this.activeTasks.some(t => t.status === 'in_progress')) {
                    this.tasksExpanded = true;
                }
            } catch {}
        },

        _debouncedLoadTasks() {
            clearTimeout(this._taskDebounceTimer);
            this._taskDebounceTimer = setTimeout(() => this.loadTasks(), 300);
        },

        async deleteTask(taskId) {
            try {
                await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
                await this.loadTasks();
            } catch {}
        },

        toggleTask(taskId) {
            this.expandedTasks[taskId] = !this.expandedTasks[taskId];
        },

        isTaskExpanded(taskId) {
            return !!this.expandedTasks[taskId];
        },

        // --- Popover ---

        popoverPos: { top: 0, left: 0, right: 0, align: 'left' },

        togglePopover(id, event) {
            if (event) event.stopPropagation();
            if (this.activePopover === id) {
                this.activePopover = null;
                return;
            }
            this.activePopover = id;
            const btn = event && event.currentTarget;
            if (btn) {
                const rect = btn.getBoundingClientRect();
                const isRight = btn.closest('[data-popover-right]');
                this.popoverPos = {
                    top: Math.round(rect.bottom + 4),
                    left: Math.round(rect.left),
                    right: Math.round(window.innerWidth - rect.right),
                    align: isRight ? 'right' : 'left',
                };
            }
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
            let text = this.inputText.trim();
            if ((!text && !this.uploadedFiles.length) || this.isLoading) return;
            // Auto-attach file references if files were uploaded
            if (this.uploadedFiles.length) {
                const fileRefs = this.uploadedFiles.map(f => `Analyze file: ${f}`).join('\n');
                text = text ? `${text}\n${fileRefs}` : fileRefs;
            }
            this.inputText = '';
            this.isLoading = true;
            this.uploadedFiles = [];
            this.connectionError = '';
            this._interrupted = false;
            this.activeSteps = [];
            this.turns.push({ role: 'user', content: text, roundIndex: this._countUserTurns() });
            this.turns.push({
                role: 'assistant', content: '', _rawContent: '', toolCalls: [], artifacts: [],
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
                if (!this._interrupted) {
                    this.isLoading = false;
                    // Reveal any buffered content
                    if (turn._rawContent) {
                        turn.content += turn._rawContent;
                        turn._rawContent = '';
                    }
                }
                this.activeSteps = [];
                await this.loadSessions();
                await this.loadTasks();
                // Render mermaid after SSE completes
                requestAnimationFrame(() => {
                    const el = document.getElementById('messages-container');
                    if (el) this._renderMermaidInElement(el);
                });
            }
        },

        // --- Confirmation helpers ---

        _initConfirmationState() {
            return {
                freeText: '',
                selectedOptions: [],    // for multi-select
                currentStep: 0,         // for multi-question
                answers: [],            // collected answers for multi-question
            };
        },

        _isMultiQuestion(confirmation) {
            if (!confirmation || !confirmation.context) return false;
            try {
                const parsed = JSON.parse(confirmation.context);
                return Array.isArray(parsed) && parsed.length > 0 && !!parsed[0].question;
            } catch { return false; }
        },

        _parseMultiQuestions(confirmation) {
            try { return JSON.parse(confirmation.context); }
            catch { return []; }
        },

        _toggleMultiSelect(confirmationState, value) {
            const idx = confirmationState.selectedOptions.indexOf(value);
            if (idx >= 0) confirmationState.selectedOptions.splice(idx, 1);
            else confirmationState.selectedOptions.push(value);
        },

        _isOptionSelected(confirmationState, value) {
            return confirmationState.selectedOptions.includes(value);
        },

        _submitSingleAnswer(confirmation, confirmationState) {
            let answer;
            if (confirmationState.selectedOptions.length > 0) {
                answer = confirmationState.selectedOptions.join(', ');
            } else if (confirmationState.freeText.trim()) {
                answer = confirmationState.freeText.trim();
            } else {
                answer = 'skipped';
            }
            return answer;
        },

        _submitMultiQuestionStep(confirmation, confirmationState, question) {
            const stepAnswer = {
                question: question.question,
                answer: '',
                is_free_input: false,
            };
            if (confirmationState.selectedOptions.length > 0) {
                stepAnswer.answer = confirmationState.selectedOptions.join(', ');
                stepAnswer.is_free_input = false;
            } else if (confirmationState.freeText.trim()) {
                stepAnswer.answer = confirmationState.freeText.trim();
                stepAnswer.is_free_input = true;
            } else {
                stepAnswer.answer = 'skipped';
            }
            confirmationState.answers.push(stepAnswer);
            // Reset for next question
            confirmationState.selectedOptions = [];
            confirmationState.freeText = '';
            confirmationState.currentStep++;
        },

        _multiQuestionComplete(confirmation, confirmationState) {
            const parts = confirmationState.answers.map((a, i) => `Q${i+1}: ${a.question} → ${a.answer}`);
            return parts.join('; ');
        },

        async resumeConfirmation(suspensionId, userResponse) {
            if (this.isResuming) return;
            this.isResuming = true;
            const turn = this.turns[this.turns.length - 1];
            if (turn) turn.confirmation._resuming = true;
            this.activeSteps = [];
            this._interrupted = false;
            let newTurn = null;
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
                    role: 'assistant', content: '', _rawContent: '', toolCalls: [], artifacts: [],
                    confirmation: null, isThinking: true, thinkingText: 'Resuming...', _copied: false,
                });
                newTurn = this.turns[this.turns.length - 1];
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
                if (!this._interrupted) {
                    this.isLoading = false;
                    if (newTurn && newTurn._rawContent) {
                        newTurn.content += newTurn._rawContent;
                        newTurn._rawContent = '';
                    }
                }
                this.activeSteps = [];
                await this.loadSessions();
                await this.loadTasks();
                // Render mermaid after resume completes
                requestAnimationFrame(() => {
                    const el = document.getElementById('messages-container');
                    if (el) this._renderMermaidInElement(el);
                });
            }
        },

        _submitConfirmation(turn) {
            const c = turn.confirmation;
            if (!c) return;
            const st = c._state;
            const isMulti = this._isMultiQuestion(c);

            if (isMulti) {
                const questions = this._parseMultiQuestions(c);
                const currentQ = questions[st.currentStep];
                if (st.currentStep < questions.length - 1) {
                    this._submitMultiQuestionStep(c, st, currentQ);
                    st.selectedOptions = [];
                    st.freeText = '';
                    return;
                }
                this._submitMultiQuestionStep(c, st, currentQ);
                const response = this._multiQuestionComplete(c, st);
                this.resumeConfirmation(c.suspension_id, response);
            } else {
                const response = this._submitSingleAnswer(c, st);
                this.resumeConfirmation(c.suspension_id, response);
            }
        },

        _skipConfirmation(turn) {
            const c = turn.confirmation;
            if (!c) return;
            const isMulti = this._isMultiQuestion(c);
            if (isMulti) {
                const st = c._state;
                const questions = this._parseMultiQuestions(c);
                st.answers.push({ question: questions[st.currentStep].question, answer: 'skipped', is_free_input: false });
                st.currentStep++;
                st.selectedOptions = [];
                st.freeText = '';
                if (st.currentStep >= questions.length) {
                    const response = this._multiQuestionComplete(c, st);
                    this.resumeConfirmation(c.suspension_id, response);
                }
            } else {
                this.resumeConfirmation(c.suspension_id, 'skipped');
            }
        },

        _cancelConfirmation(turn) {
            const c = turn.confirmation;
            if (!c) return;
            this.resumeConfirmation(c.suspension_id, 'cancelled');
        },

        async interruptTurn() {
            if (!this.currentSessionId) return;
            this._interrupted = true;
            // Mark current turn as stopped
            const turn = this.turns[this.turns.length - 1];
            if (turn && turn.role === 'assistant') {
                turn.isThinking = false;
                if (!turn.content) turn.content = '*Stopped.*';
                turn._rawContent = '';
            }
            this.activeSteps = [];
            this.isLoading = false;
            try {
                await fetch('/api/chat/interrupt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: this.currentSessionId }),
                });
            } catch {}
        },

        async uploadFile(event) {
            const files = event.target.files;
            if (!files || !files.length) return;
            this.isUploading = true;
            const uploads = Array.from(files);
            const results = await Promise.allSettled(uploads.map(async (file) => {
                const formData = new FormData();
                formData.append('file', file);
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (res.ok && data.filename) {
                    this.uploadedFiles.push(data.filename);
                    return data.filename;
                } else {
                    throw new Error(data.error || 'Upload failed');
                }
            }));
            this.isUploading = false;
            const failures = results.filter(r => r.status === 'rejected');
            if (failures.length) {
                alert(failures.map(f => f.reason.message).join('\n'));
            }
            event.target.value = '';
        },

        renderMarkdown(text) {
            if (!text) return '';
            try {
                if (!this._markedReady) this._setupMarked();
                return marked.parse(text);
            } catch { return text; }
        },

        _markedReady: false,

        _setupMarked() {
            this._markedReady = true;
            const self = this;
            marked.use({
                renderer: {
                    code({ text, lang }) {
                        const language = (lang || '').toLowerCase().trim();

                        // Mermaid diagrams
                        if (language === 'mermaid') {
                            const id = 'mermaid-' + Math.random().toString(36).slice(2, 10);
                            return `<div class="mermaid-container"><div class="mermaid" id="${id}">${text}</div></div>`;
                        }

                        // Regular code with syntax highlighting
                        let highlighted;
                        try {
                            if (language && hljs.getLanguage(language)) {
                                highlighted = hljs.highlight(text, { language }).value;
                            } else if (text.length > 0) {
                                highlighted = hljs.highlightAuto(text).value;
                            } else {
                                highlighted = '';
                            }
                        } catch {
                            highlighted = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
                        }
                        const langBadge = language ? `<span class="code-lang-badge">${language}</span>` : '';
                        return `<pre>${langBadge}<code class="hljs language-${language}">${highlighted}</code></pre>`;
                    },
                    // Auto-link file paths in text
                    text({ text }) {
                        // Match session file paths like "sessions/.../reports/xxx.html" or "sessions/.../charts/xxx.html"
                        const filePathPattern = /(?:Chart saved: |Report generated: |PDF exported: |Markdown report: |Conversation exported: )?(sessions\/[^\s"'<>]+\.(?:html|pdf|md|png))/g;
                        return text.replace(filePathPattern, (match, path) => {
                            const label = match.replace(path, '').trim() || path;
                            const url = '/files/' + encodeURIComponent(path);
                            return ` <a href="${url}" target="_blank" class="file-link">${path}</a>`;
                        });
                    },
                },
                breaks: true,
                gfm: true,
            });
        },

        async _renderMermaidInElement(el) {
            if (!el) return;
            const mermaidDivs = el.querySelectorAll('.mermaid:not([data-processed])');
            for (const div of mermaidDivs) {
                try {
                    const { svg } = await mermaid.render(div.id || ('m-' + Math.random().toString(36).slice(2)), div.textContent);
                    div.innerHTML = svg;
                    div.setAttribute('data-processed', 'true');
                } catch (e) {
                    div.innerHTML = `<div class="mermaid-error">Diagram render error: ${e.message || e}</div><pre>${div.textContent}</pre>`;
                    div.setAttribute('data-processed', 'true');
                }
            }
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
                    if (!turn.content && !turn._rawContent) turn.content = '**Connection lost.**';
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
                    // If tools are running (task mode), buffer text; otherwise stream directly
                    if (this.activeSteps.length > 0) {
                        turn._rawContent = (turn._rawContent || '') + data.text;
                    } else {
                        turn.content += data.text;
                    }
                    this._scrollToBottom();
                    break;
                case 'tool_call':
                    turn.isThinking = true;
                    turn.thinkingText = `Running ${data.name}...`;
                    // Add to active steps (shown in task panel), not in chat
                    this.activeSteps.push({
                        tool_call_id: data.tool_call_id, name: data.name,
                        arguments: data.arguments, duration_ms: 0,
                        result_summary: '', status: 'running', _expanded: false,
                    });
                    break;
                case 'tool_result':
                    turn.isThinking = true;
                    turn.thinkingText = 'Processing results...';
                    const step = this.activeSteps.find(s => s.tool_call_id === data.tool_call_id);
                    if (step) {
                        step.status = 'done';
                        step.duration_ms = data.duration_ms || 0;
                        const web = data.web || {};
                        step.result_summary = web.summary || web.content || '';
                        if (web.artifacts) {
                            for (const art of web.artifacts) {
                                if (art.path) turn.artifacts.push(art);
                            }
                        }
                    }
                    break;
                case 'task_update':
                    this._debouncedLoadTasks();
                    break;
                case 'suspended':
                    turn.isThinking = false;
                    turn.confirmation = {
                        suspension_id: data.suspension_id,
                        question: data.question,
                        options: data.options || [],
                        context: data.context || '',
                        _resuming: false,
                        _state: this._initConfirmationState(),
                    };
                    break;
                case 'turn_end':
                    turn.isThinking = false;
                    // Reveal buffered content from task execution
                    if (turn._rawContent) {
                        turn.content += turn._rawContent;
                        turn._rawContent = '';
                    }
                    if (data.pct !== undefined) this.tokenPct = data.pct;
                    // Render mermaid diagrams after content is finalized
                    this._scrollToBottom();
                    requestAnimationFrame(() => {
                        const el = document.getElementById('messages-container');
                        if (el) this._renderMermaidInElement(el);
                    });
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
