/* Data Agent Web GUI — Alpine.js chat application */

function chatApp() {
    return {
        sidebarCollapsed: false,
        sessions: [],
        sessionSearch: '',
        currentSessionId: null,
        inputText: '',
        isUploading: false,
        uploadedFiles: [],
        connectionError: '',

        // Objects
        objects: [],
        activeObjectName: '',
        showNewObjectForm: false,
        newObjectName: '',
        expandedObjects: {},

        // Model
        modelName: '',
        availableModels: [],

        // Popover
        activePopover: null,

        // Config modal
        configModal: { show: false, model_id: '', api_base: '', api_key: '', has_key: false, saving: false },

        // Artifacts modal
        artifactsModal: { show: false, sessionId: '', items: [] },

        // Bind-to-object modal
        _bindModal: { show: false, sessionId: '' },

        // Tasks
        tasks: [],
        tasksExpanded: true,
        expandedTasks: {},
        _taskDebounceTimer: null,

        // ── Per-session state ──────────────────────
        // Stores: { turns, isLoading, tokenPct, isCompact, activeSteps, _interrupted }
        _sessionStates: {},

        // Direct reactive properties — synced on session switch
        turns: [],
        isLoading: false,
        tokenPct: 0,
        tokenSupported: false,
        isCompact: false,

        _emptySessionState() {
            return {
                turns: [],
                isLoading: false,
                tokenPct: 0,
                tokenSupported: false,
                isCompact: false,
                activeSteps: [],
                _interrupted: false,
            };
        },

        _getSessionState(sid) {
            if (!this._sessionStates[sid]) {
                this._sessionStates[sid] = this._emptySessionState();
            }
            return this._sessionStates[sid];
        },

        // Save current reactive properties into per-session state
        _saveCurrentState() {
            const sid = this.currentSessionId;
            if (!sid) return;
            const s = this._getSessionState(sid);
            s.turns = this.turns;
            s.isLoading = this.isLoading;
            s.tokenPct = this.tokenPct;
            s.tokenSupported = this.tokenSupported;
            s.isCompact = this.isCompact;
        },

        // Restore reactive properties from per-session state
        _restoreState(sid) {
            const s = this._getSessionState(sid);
            this.turns = s.turns;
            this.isLoading = s.isLoading;
            this.tokenPct = s.tokenPct;
            this.tokenSupported = s.tokenSupported;
            this.isCompact = s.isCompact;
        },

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

        get hasActiveConfirmation() {
            if (!this.currentSessionId) return false;
            const state = this._getSessionState(this.currentSessionId);
            const turns = state.turns;
            if (turns.length === 0) return false;
            const lastTurn = turns[turns.length - 1];
            return lastTurn.role === 'assistant' && lastTurn.confirmation != null;
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
            if (this.activePopover.startsWith('obj-')) return this.activePopover.slice(4);
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
            const state = this._getSessionState(this.currentSessionId);
            try {
                const res = await fetch('/api/compact', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: this.currentSessionId }),
                });
                const data = await res.json();
                if (res.ok) {
                    state.turns.push({
                        role: 'assistant',
                        content: data.message || 'Context compressed.',
                        ts: Date.now(),
                    });
                } else {
                    state.turns.push({
                        role: 'assistant',
                        content: `Compression failed: ${data.error || 'unknown error'}`,
                        ts: Date.now(),
                    });
                }
            } catch (e) {
                state.turns.push({
                    role: 'assistant',
                    content: `Compression failed: ${e.message}`,
                    ts: Date.now(),
                });
            }
            this.isCompact = false;
        },

        async newSession() {
            if (this.isLoading && !confirm('A task is running. Start new session anyway?')) return;
            this._saveCurrentState();
            this.currentSessionId = null;
            this.activeObjectName = '';
            this.turns = [];
            this.isLoading = false;
            this.tokenPct = 0;
            this.isCompact = false;
        },

        async switchSession(sessionId) {
            if (sessionId === this.currentSessionId) return;
            // Save current session state (allows background SSE to keep running)
            this._saveCurrentState();
            this.currentSessionId = sessionId;
            this._restoreState(sessionId);
            this.activeObjectName = '';

            // Load fresh data from backend if not already loaded
            const state = this._getSessionState(sessionId);
            if (state.turns.length === 0) {
                try {
                    const res = await fetch(`/api/sessions/${sessionId}`);
                    const data = await res.json();
                    if (data.messages) {
                        state.turns = this._reconstructTurns(data.messages);
                        this.turns = state.turns;
                    }
                    this.activeObjectName = data.object_name || '';
                    if (data.token_usage) {
                        state.tokenPct = data.token_usage.pct || 0;
                        state.tokenSupported = true;
                    } else {
                        state.tokenPct = 0;
                        state.tokenSupported = false;
                    }
                    this.tokenPct = state.tokenPct;
                    this.tokenSupported = state.tokenSupported;
                    this.connectionError = '';
                } catch {
                    this.connectionError = 'Failed to load session';
                }
            } else {
                // Find activeObjectName from sessions list
                const sess = this.sessions.find(s => s.session_id === sessionId);
                if (sess) this.activeObjectName = sess.object_name || '';
            }
            this._scrollToBottom();
        },

        async deleteSession(sessionId) {
            if (!confirm('Delete this session?')) return;
            const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
            // Immediately remove from local sessions array for instant UI update
            this.sessions = this.sessions.filter(s => s.session_id !== sessionId);
            delete this._sessionStates[sessionId];
            if (this.currentSessionId === sessionId) {
                this.currentSessionId = null;
                this.turns = [];
                this.isLoading = false;
                this.tokenPct = 0;
            }
            // Also refresh from server to ensure consistency
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
            if (!confirm(`Delete object "${objectName}" and unbind all its sessions?`)) return;
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

        async renameObject(objectName) {
            const newName = prompt(`Rename "${objectName}" to:`, objectName);
            if (!newName || newName === objectName) return;
            try {
                const res = await fetch(`/api/objects/${encodeURIComponent(objectName)}/rename`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_name: newName }),
                });
                if (res.ok) {
                    await this.loadObjects();
                    await this.loadSessions();
                } else {
                    const data = await res.json();
                    alert(data.error || 'Rename failed');
                }
            } catch (e) {
                alert('Rename failed: ' + e.message);
            }
            this.activePopover = null;
        },

        async bindSessionToObject(sessionId, objectName) {
            if (!objectName) {
                // Show object selection modal
                this._bindModal = { show: true, sessionId };
                this.activePopover = null;
                return;
            }
            try {
                const res = await fetch('/api/objects/bind', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId, name: objectName }),
                });
                const data = await res.json();
                if (res.ok) {
                    await this.loadSessions();
                    await this.loadObjects();
                    if (this.currentSessionId === sessionId) {
                        this.activeObjectName = objectName;
                    }
                } else {
                    alert(data.error || 'Bind failed');
                }
            } catch (e) {
                alert('Bind failed: ' + e.message);
            }
            this.activePopover = null;
        },

        async unbindSession(sessionId) {
            try {
                const res = await fetch('/api/objects/unbind', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId }),
                });
                const data = await res.json();
                if (res.ok) {
                    await this.loadSessions();
                    await this.loadObjects();
                    if (this.currentSessionId === sessionId) {
                        this.activeObjectName = '';
                    }
                } else {
                    alert(data.error || 'Unbind failed');
                }
            } catch (e) {
                alert('Unbind failed: ' + e.message);
            }
            this.activePopover = null;
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
                this.tasks = [...newTasks];
                if (this.activeTasks.some(t => t.status === 'in_progress')) {
                    this.tasksExpanded = true;
                }
            } catch {}
        },

        _debouncedLoadTasks() {
            clearTimeout(this._taskDebounceTimer);
            this._taskDebounceTimer = setTimeout(() => this.loadTasks(), 300);
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
                    // Force reload: clear cached state and re-fetch from backend
                    const sid = this.currentSessionId;
                    delete this._sessionStates[sid];
                    this.currentSessionId = null; // reset so switchSession won't skip
                    await this.switchSession(sid);
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
            this.uploadedFiles = [];
            this.connectionError = '';

            // Ensure we have a session
            if (!this.currentSessionId) {
                this.currentSessionId = '_pending_';
            }

            // Save state before modifying (in case we switch away during SSE)
            this._saveCurrentState();
            const state = this._getSessionState(this.currentSessionId);
            state._interrupted = false;

            state.turns.push({ role: 'user', content: text, roundIndex: this._countUserTurns(state.turns) });
            state.turns.push({
                role: 'assistant', content: '', _rawContent: '', toolCalls: [], artifacts: [],
                confirmation: null, isThinking: true, thinkingText: 'Thinking...', _copied: false,
            });
            const turn = state.turns[state.turns.length - 1];

            // Sync to reactive properties
            this.turns = [...state.turns];
            this.isLoading = true;
            this._scrollToBottom();

            // Capture session ID for this SSE connection
            const sseSessionId = this.currentSessionId;

            try {
                const body = { message: text };
                if (sseSessionId && sseSessionId !== '_pending_') body.session_id = sseSessionId;
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
                await this._processSSE(response, turn, state, sseSessionId);
            } catch (e) {
                turn.isThinking = false;
                turn.content += `\n\n**Connection error:** ${e.message}`;
                if (this.currentSessionId === sseSessionId) {
                    this.connectionError = e.message;
                }
            } finally {
                if (!state._interrupted) {
                    state.isLoading = false;
                    if (turn._rawContent) {
                        turn.content += turn._rawContent;
                        turn._rawContent = '';
                    }
                    // Sync back if still on this session
                    if (this.currentSessionId === sseSessionId) {
                        this.isLoading = false;
                        this.turns = [...state.turns];
                    }
                }
                await this.loadSessions();
                await this.loadTasks();
                if (this.currentSessionId === sseSessionId) {
                    requestAnimationFrame(() => {
                        const el = document.getElementById('messages-container');
                        if (el) this._renderMermaidInElement(el);
                    });
                }
            }
        },

        // --- Confirmation helpers ---

        _initConfirmationState() {
            return {
                freeText: '',
                selectedOptions: [],
                currentStep: 0,
                answers: [],
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

        _toggleSingleOption(confirmationState, value) {
            confirmationState.selectedOptions =
                confirmationState.selectedOptions.includes(value) ? [] : [value];
            confirmationState.freeText = '';
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
            confirmationState.selectedOptions = [];
            confirmationState.freeText = '';
            confirmationState.currentStep++;
        },

        _multiQuestionComplete(confirmation, confirmationState) {
            const parts = confirmationState.answers.map((a, i) => `Q${i+1}: ${a.question} → ${a.answer}`);
            return parts.join('; ');
        },

        async resumeConfirmation(suspensionId, userResponse) {
            const state = this._getSessionState(this.currentSessionId);
            if (state._resuming) return;
            state._resuming = true;
            const turn = state.turns[state.turns.length - 1];
            if (turn) turn.confirmation._resuming = true;
            state._interrupted = false;
            let newTurn = null;
            const sseSessionId = this.currentSessionId;
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
                state.turns.push({
                    role: 'assistant', content: '', _rawContent: '', toolCalls: [], artifacts: [],
                    confirmation: null, isThinking: true, thinkingText: 'Resuming...', _copied: false,
                });
                newTurn = state.turns[state.turns.length - 1];
                this.turns = [...state.turns];
                this._scrollToBottom();
                await this._processSSE(response, newTurn, state, sseSessionId);
            } catch (e) {
                const last = state.turns[state.turns.length - 1];
                if (last) {
                    last.isThinking = false;
                    last.content += `\n\n**Connection error:** ${e.message}`;
                }
                if (this.currentSessionId === sseSessionId) {
                    this.connectionError = e.message;
                }
            } finally {
                state._resuming = false;
                if (!state._interrupted) {
                    state.isLoading = false;
                    if (newTurn && newTurn._rawContent) {
                        newTurn.content += newTurn._rawContent;
                        newTurn._rawContent = '';
                    }
                    if (this.currentSessionId === sseSessionId) {
                        this.isLoading = false;
                        this.turns = [...state.turns];
                    }
                }
                await this.loadSessions();
                await this.loadTasks();
                if (this.currentSessionId === sseSessionId) {
                    requestAnimationFrame(() => {
                        const el = document.getElementById('messages-container');
                        if (el) this._renderMermaidInElement(el);
                    });
                }
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
            if (!confirm('Stop the current conversation? This cannot be undone.')) return;
            const state = this._getSessionState(this.currentSessionId);
            state._interrupted = true;
            const turn = state.turns[state.turns.length - 1];
            if (turn && turn.role === 'assistant') {
                turn.isThinking = false;
                if (!turn.content) turn.content = '*Stopped.*';
                turn._rawContent = '';
                // Clear confirmation dialog if present
                if (turn.confirmation) turn.confirmation = null;
            }
            state.isLoading = false;
            this.isLoading = false;
            this.turns = [...state.turns];
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
            // Pre-process: extract Plotly JSON outside code blocks
            text = this._extractPlotlyJson(text);
            try {
                if (!this._markedReady) this._setupMarked();
                return marked.parse(text);
            } catch { return text; }
        },

        // Chart data store — avoids embedding large JSON in HTML attributes
        _chartData: {},

        _extractPlotlyJson(text) {
            const MARKER = '{"data":';
            let result = text;
            let searchOffset = 0;

            while (true) {
                const startIdx = result.indexOf(MARKER, searchOffset);
                if (startIdx === -1) break;

                // Skip if inside a code block
                const before = result.substring(Math.max(0, startIdx - 300), startIdx);
                const lastFence = before.lastIndexOf('```');
                if (lastFence !== -1 && !before.substring(lastFence).includes('\n```')) {
                    searchOffset = startIdx + 1;
                    continue;
                }

                // Extract complete JSON via brace matching
                let depth = 0, inStr = false, esc = false, endIdx = -1;
                for (let i = startIdx; i < result.length && i < startIdx + 200000; i++) {
                    const ch = result[i];
                    if (esc) { esc = false; continue; }
                    if (ch === '\\' && inStr) { esc = true; continue; }
                    if (ch === '"' && !esc) { inStr = !inStr; continue; }
                    if (inStr) continue;
                    if (ch === '{') depth++;
                    if (ch === '}') { depth--; if (depth === 0) { endIdx = i; break; } }
                }
                if (endIdx === -1) { searchOffset = startIdx + 1; continue; }

                const jsonStr = result.substring(startIdx, endIdx + 1);
                try {
                    const parsed = JSON.parse(jsonStr);
                    if (parsed && Array.isArray(parsed.data) && parsed.data.length > 0) {
                        const chartId = 'plotly-' + Math.random().toString(36).slice(2, 10);
                        this._chartData[chartId] = parsed;
                        const placeholder = `\n<div class="plotly-chart-container"><div id="${chartId}" class="plotly-chart"></div></div>\n`;
                        result = result.substring(0, startIdx) + placeholder + result.substring(endIdx + 1);
                        searchOffset = startIdx + placeholder.length;
                        continue;
                    }
                } catch {}
                searchOffset = startIdx + 1;
            }
            return result;
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

                        // Plotly JSON charts — detect in ANY code block, only require `data` field
                        try {
                            const parsed = JSON.parse(text);
                            if (parsed && Array.isArray(parsed.data) && parsed.data.length > 0) {
                                const chartId = 'plotly-' + Math.random().toString(36).slice(2, 10);
                                self._chartData[chartId] = parsed;
                                return `<div class="plotly-chart-container"><div id="${chartId}" class="plotly-chart"></div></div>`;
                            }
                        } catch {}

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
                },
                breaks: true,
                gfm: true,
            });
        },

        async _renderMermaidInElement(el) {
            if (!el) return;
            // Render mermaid diagrams
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
            // Render plotly charts — use _chartData map (primary) or data-chart attr (legacy)
            const plotlyDivs = el.querySelectorAll('.plotly-chart:not([data-processed])');
            for (const div of plotlyDivs) {
                try {
                    let chartObj = this._chartData[div.id];
                    if (!chartObj) {
                        const attr = div.getAttribute('data-chart');
                        if (attr) chartObj = JSON.parse(attr);
                    }
                    if (chartObj && typeof Plotly !== 'undefined') {
                        Plotly.newPlot(div, chartObj.data, chartObj.layout || {}, { responsive: true, displayModeBar: false });
                        div.setAttribute('data-processed', 'true');
                        delete this._chartData[div.id];
                    }
                } catch (e) {
                    div.innerHTML = `<div class="mermaid-error">Chart render error: ${e.message || e}</div>`;
                    div.setAttribute('data-processed', 'true');
                }
            }
        },

        async copyToClipboard(text, turn) {
            try { await navigator.clipboard.writeText(text); } catch {
                const ta = document.createElement('textarea');
                ta.value = text; document.body.appendChild(ta);
                ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
            }
            if (turn) {
                turn._copied = true;
                setTimeout(() => { turn._copied = false; }, 2000);
            }
        },

        artifactUrl(path) {
            return path ? '/files/' + encodeURIComponent(path) : '';
        },

        // --- SSE ---

        async _processSSE(response, turn, state, sessionId) {
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
                        try { this._handleEvent(eventType, JSON.parse(eventData), turn, state, sessionId); }
                        catch (e) { console.error('SSE event error:', type, e); }
                        eventType = ''; eventData = '';
                    }
                }
            }
            turn.isThinking = false;
            this.connectionError = '';
        },

        _handleEvent(type, data, turn, state, sessionId) {
            let isCurrentSession = (this.currentSessionId === sessionId);

            switch (type) {
                case 'turn_start':
                    if (data.session_id && sessionId === '_pending_') {
                        // Migrate _pending_ state to real session ID
                        const oldState = this._sessionStates['_pending_'];
                        delete this._sessionStates['_pending_'];
                        this._sessionStates[data.session_id] = oldState || state;
                        if (this.currentSessionId === '_pending_') {
                            this.currentSessionId = data.session_id;
                        }
                        sessionId = data.session_id;
                        state = this._sessionStates[sessionId];
                        isCurrentSession = (this.currentSessionId === sessionId);
                    }
                    if (data.pct !== undefined) {
                        state.tokenPct = data.pct;
                        state.tokenSupported = true;
                        if (isCurrentSession) { this.tokenPct = data.pct; this.tokenSupported = true; }
                    }
                    break;
                case 'llm_call_start':
                    turn.isThinking = true;
                    turn.thinkingText = `Round ${data.round} — Analyzing...`;
                    if (data.pct !== undefined) {
                        state.tokenPct = data.pct;
                        state.tokenSupported = true;
                        if (isCurrentSession) { this.tokenPct = data.pct; this.tokenSupported = true; }
                    }
                    break;
                case 'text_delta':
                    turn.isThinking = false;
                    // Always buffer text during a turn — only reveal at turn_end
                    turn._rawContent = (turn._rawContent || '') + data.text;
                    if (isCurrentSession) {
                        this._scrollToBottom();
                    }
                    break;
                case 'tool_call':
                    turn.isThinking = true;
                    turn.thinkingText = `Running ${data.name}...`;
                    state.activeSteps.push({
                        tool_call_id: data.tool_call_id, name: data.name,
                        arguments: data.arguments, duration_ms: 0,
                        result_summary: '', status: 'running', _expanded: false,
                    });
                    break;
                case 'tool_result':
                    turn.isThinking = true;
                    turn.thinkingText = 'Processing results...';
                    const step = state.activeSteps.find(s => s.tool_call_id === data.tool_call_id);
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
                    // Reveal buffered content before showing confirmation
                    if (turn._rawContent) {
                        turn.content += turn._rawContent;
                        turn._rawContent = '';
                    }
                    turn.confirmation = {
                        suspension_id: data.suspension_id,
                        question: data.question,
                        options: data.options || [],
                        context: data.context || '',
                        _resuming: false,
                        _state: this._initConfirmationState(),
                    };
                    if (isCurrentSession) {
                        this.turns = [...state.turns];
                    }
                    break;
                case 'turn_end':
                    turn.isThinking = false;
                    // Reveal buffered content from task execution
                    if (turn._rawContent) {
                        turn.content += turn._rawContent;
                        turn._rawContent = '';
                    }
                    if (data.pct !== undefined) {
                        state.tokenPct = data.pct;
                        state.tokenSupported = true;
                        if (isCurrentSession) { this.tokenPct = data.pct; this.tokenSupported = true; }
                    }
                    if (isCurrentSession) {
                        this.turns = [...state.turns];
                        this._scrollToBottom();
                        requestAnimationFrame(() => {
                            const el = document.getElementById('messages-container');
                            if (el) this._renderMermaidInElement(el);
                        });
                    }
                    break;
                case 'error':
                    turn.isThinking = false;
                    turn.content += `\n\n**Error:** ${data.message}`;
                    if (isCurrentSession) {
                        this.turns = [...state.turns];
                    }
                    break;
            }
        },

        // --- Helpers ---

        _countUserTurns(turns) {
            return turns.filter(t => t.role === 'user').length;
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
