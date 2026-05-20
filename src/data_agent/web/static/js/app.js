/* Data Agent Web GUI — Alpine.js chat application */

function chatApp() {
    return {
        sidebarCollapsed: false,
        sessions: [],
        sessionSearch: '',
        get sessionTitle() {
            if (!this.currentSessionId || this.currentSessionId === '_pending_') return '';
            const s = this.sessions.find(s => s.session_id === this.currentSessionId);
            return s ? (s.summary || s.session_id) : this.currentSessionId;
        },
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
        sessionArtifacts: [],
        lastWorkbenchResult: null,

        // Workbench capabilities and analysis state
        capabilities: null,
        analysisState: null,

        // Bind-to-object modal
        _bindModal: { show: false, sessionId: '' },

        // Tasks
        tasks: [],
        tasksExpanded: false,
        expandedTasks: {},
        _taskDebounceTimer: null,
        _taskPollInterval: null,
        _taskPollMs: null,

        // Rewind modal (for toolbar button)
        rewindModal: { show: false, rounds: [], selectedRound: null, loading: false },

        // Compact dialog
        compactDialog: { show: false, focus: '', loading: false },

        // Toast notifications
        _toastTimer: null,
        toastMessage: '',

        // Thinking animation
        _thinkingStates: ['思考中...', '分析数据...', '生成洞察...', '处理结果...', '整理分析...', '调用工具中...'],
        _thinkingStateIndex: 0,
        _thinkingTimer: null,

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

        _initialized: false,

        async init() {
            if (this._initialized) return;
            this._initialized = true;
            await Promise.all([
                this.loadSessions(),
                this.loadObjects(),
                this.loadCapabilities(),
                this.loadModelInfo(),
                this.loadTasks(),
            ]);
            document.addEventListener('click', (e) => {
                if (this.activePopover && !e.target.closest('[data-popover]')) {
                    this.activePopover = null;
                }
            });
            this._setupRenderObserver();
            this._updateTaskPollInterval();
            // Refresh on tab focus
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden && this.currentSessionId) {
                    this.loadTasks();
                    this.loadSessionArtifacts();
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
            for (const s of this.filteredSessions) {
                const key = s.object_name || '';
                if (!groups[key]) groups[key] = [];
                groups[key].push(s);
            }
            return groups;
        },

        get unboundSessions() {
            return this.filteredSessions.filter(s => !s.object_name);
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

        get analysisSummary() {
            return (this.analysisState && this.analysisState.summary) || {
                goal: '',
                stage: 'discover',
                data_state: 'unknown',
                requirements: 0,
                has_spec: false,
                evidence_records: 0,
                insight_records: 0,
                pending_confirmations: 0,
                recommended_paths: 0,
            };
        },

        get popoverTargetId() {
            if (!this.activePopover) return '';
            if (this.activePopover.startsWith('s-')) return this.activePopover.slice(2);
            if (this.activePopover.startsWith('u-')) return this.activePopover.slice(2);
            if (this.activePopover.startsWith('obj-')) return this.activePopover.slice(4);
            return '';
        },

        // --- Model ---

        async loadCapabilities() {
            try {
                const res = await fetch('/api/capabilities');
                if (res.ok) this.capabilities = await res.json();
            } catch {}
        },

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
                alert('保存失败：' + e.message);
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
                this.connectionError = '加载会话失败';
            }
        },

        async compactContext() {
            if (!this.currentSessionId || this.isCompact) return;
            this.compactDialog = { show: true, focus: '', loading: false };
        },

        async doCompact() {
            this.compactDialog.loading = true;
            this.isCompact = true;
            const state = this._getSessionState(this.currentSessionId);
            try {
                const body = { session_id: this.currentSessionId };
                if (this.compactDialog.focus.trim()) body.focus = this.compactDialog.focus.trim();
                const res = await fetch('/api/compact', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                if (res.ok) {
                    state.turns.push({
                        role: 'assistant',
                        content: data.message || '上下文已压缩。',
                        ts: Date.now(),
                    });
                } else {
                    state.turns.push({
                        role: 'assistant',
                        content: `压缩失败：${data.error || '未知错误'}`,
                        ts: Date.now(),
                    });
                }
            } catch (e) {
                state.turns.push({
                    role: 'assistant',
                    content: `压缩失败：${e.message}`,
                    ts: Date.now(),
                });
            }
            this.isCompact = false;
            this.compactDialog.show = false;
        },

        async rewindMessage(roundIndex) {
            if (!this.currentSessionId || this.currentSessionId === '_pending_') return;
            if (!confirm('回退到这条消息之前？该消息及之后的所有内容将被移除，消息内容将填入输入框供编辑重发。')) return;
            await this._doRewind(roundIndex);
        },

        async showRewindDialog() {
            if (!this.currentSessionId || this.currentSessionId === '_pending_') return;
            this.rewindModal = { show: true, rounds: [], selectedRound: null, loading: true };
            try {
                const res = await fetch(`/api/sessions/${this.currentSessionId}/rewind-info`);
                if (res.ok) {
                    const data = await res.json();
                    this.rewindModal.rounds = (data.rounds || []).map(r => ({
                        ...r,
                        user_preview: r.user_text || r.user_preview || '',
                        assistant_preview: r.assistant_summary || r.assistant_preview || '',
                    }));
                }
            } catch {}
            this.rewindModal.loading = false;
        },

        async doRewind() {
            if (!this.rewindModal.selectedRound) return;
            const roundNum = this.rewindModal.selectedRound;
            this.rewindModal.show = false;
            await this._doRewind(roundNum);
        },

        async _doRewind(roundIndex) {
            try {
                const res = await fetch(`/api/sessions/${this.currentSessionId}/rewind`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ round: roundIndex }),
                });
                const data = await res.json();
                if (res.ok) {
                    const sid = this.currentSessionId;
                    delete this._sessionStates[sid];
                    this.currentSessionId = null;
                    await this.switchSession(sid);
                    if (data.user_message) {
                        this.inputText = data.user_message;
                    }
                    this.showToast('已回退，可编辑后重新发送');
                } else {
                    alert(data.error || '回退失败');
                }
            } catch (e) {
                alert('回退失败：' + e.message);
            }
        },

        showToast(message) {
            this.toastMessage = message;
            clearTimeout(this._toastTimer);
            this._toastTimer = setTimeout(() => { this.toastMessage = ''; }, 3000);
        },

        _startThinkingCycle(turn) {
            this._stopThinkingCycle();
            this._thinkingStateIndex = 0;
            this._thinkingTimer = setInterval(() => {
                this._thinkingStateIndex = (this._thinkingStateIndex + 1) % this._thinkingStates.length;
                turn.thinkingText = this._thinkingStates[this._thinkingStateIndex];
            }, 2000);
        },

        _stopThinkingCycle() {
            if (this._thinkingTimer) {
                clearInterval(this._thinkingTimer);
                this._thinkingTimer = null;
            }
        },

        async newSession() {
            if (this.isLoading && !confirm('任务正在运行，确认新建会话？')) return;
            this._saveCurrentState();
            this.currentSessionId = null;
            this.activeObjectName = '';
            this.analysisState = null;
            this.sessionArtifacts = [];
            this.lastWorkbenchResult = null;
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
            this.lastWorkbenchResult = null;

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
                    this.connectionError = '加载会话失败';
                }
            } else {
                // Find activeObjectName from sessions list
                const sess = this.sessions.find(s => s.session_id === sessionId);
                if (sess) this.activeObjectName = sess.object_name || '';
            }
            await Promise.all([
                this.loadAnalysisState(sessionId),
                this.loadSessionArtifacts(sessionId),
                this.loadTasks(),
            ]);
            this._scrollToBottom();
        },

        async deleteSession(sessionId) {
            if (!confirm('确认删除此会话？')) return;
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
                const res = await fetch('/api/projects');
                this.objects = await res.json();
            } catch {}
        },

        async createObject() {
            const name = this.newObjectName.trim();
            if (!name) return;
            try {
                const res = await fetch('/api/projects', {
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
                    alert(data.error || 'Failed to create project');
                }
            } catch {}
        },

        async deleteObject(objectName) {
            if (!confirm(`确认删除项目 "${objectName}" 并解除所有会话绑定？`)) return;
            try {
                const res = await fetch(`/api/projects/${encodeURIComponent(objectName)}`, { method: 'DELETE' });
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
            const newName = prompt(`将 "${objectName}" 重命名为：`, objectName);
            if (!newName || newName === objectName) return;
            try {
                const res = await fetch(`/api/projects/${encodeURIComponent(objectName)}/rename`, {
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
                const res = await fetch('/api/projects/bind', {
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
                const res = await fetch('/api/projects/unbind', {
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

        async loadSessionArtifacts(sessionId = this.currentSessionId) {
            if (!sessionId || sessionId === '_pending_') {
                this.sessionArtifacts = [];
                return;
            }
            try {
                const res = await fetch(`/api/sessions/${sessionId}/artifacts-list`);
                this.sessionArtifacts = res.ok ? await res.json() : [];
                if (sessionId === this.currentSessionId) this.turns = [...this.turns];
            } catch {
                this.sessionArtifacts = [];
            }
        },

        async deleteArtifactFromModal(index) {
            if (!confirm('确认删除此产出物？')) return;
            try {
                await fetch(`/api/sessions/${this.artifactsModal.sessionId}/artifacts/${index}`, { method: 'DELETE' });
                this.artifactsModal.items.splice(index, 1);
            } catch (e) {
                alert('Delete failed: ' + e.message);
            }
        },

        async exportSession(sessionId, format = 'html') {
            this.activePopover = null;
            await this.exportConversation(format, sessionId);
        },

        async loadAnalysisState(sessionId = this.currentSessionId) {
            if (!sessionId || sessionId === '_pending_') {
                this.analysisState = null;
                return;
            }
            try {
                const res = await fetch(`/api/sessions/${sessionId}/analysis`);
                this.analysisState = res.ok ? await res.json() : null;
            } catch {
                this.analysisState = null;
            }
        },

        async resetAnalysisState() {
            if (!this.currentSessionId || this.currentSessionId === '_pending_') return;
            if (!confirm('确认重置此会话的分析状态？对话和产出物将保留。')) return;
            const res = await fetch(`/api/sessions/${this.currentSessionId}/analysis/reset`, { method: 'POST' });
            if (res.ok) this.analysisState = await res.json();
        },

        async exportConversation(format = 'html', sessionId = this.currentSessionId) {
            if (!sessionId || sessionId === '_pending_') return;
            const res = await fetch(`/api/sessions/${sessionId}/export?format=${format}`);
            const result = await res.json();
            this.lastWorkbenchResult = result;
            await this.loadSessionArtifacts(sessionId);
            this._openArtifactResult(result);
        },

        _openArtifactResult(result) {
            const path = result && (result.artifact_path || result.fallback_artifact_path);
            if (path) window.open(this.artifactUrl(path), '_blank');
        },

        // --- Tasks ---

        async loadTasks() {
            try {
                const query = this.currentSessionId && this.currentSessionId !== '_pending_' ? `?session_id=${encodeURIComponent(this.currentSessionId)}` : '';
                const res = await fetch('/api/tasks' + query);
                const newTasks = await res.json();
                this.tasks = [...newTasks];
                if (this.activeTasks.some(t => t.status === 'in_progress')) {
                    this.tasksExpanded = true;
                } else if (this.activeTasks.length > 0 && this.activeTasks.every(t => t.status === 'completed')) {
                    setTimeout(() => { this.tasksExpanded = false; }, 3000);
                }
                this._updateTaskPollInterval();
            } catch (e) {
                console.warn('loadTasks failed:', e);
            }
        },

        _desiredTaskPollMs() {
            if (!this.currentSessionId || this.currentSessionId === '_pending_') return 0;
            if (this.activeTasks.some(t => t.status === 'in_progress')) return 5000;
            if (this.activeTasks.some(t => t.status === 'pending')) return 30000;
            return 0;
        },

        _updateTaskPollInterval() {
            const desired = this._desiredTaskPollMs();
            if (this._taskPollMs === desired) return;
            clearInterval(this._taskPollInterval);
            this._taskPollInterval = null;
            this._taskPollMs = desired;
            if (desired > 0) {
                this._taskPollInterval = setInterval(() => {
                    if (!document.hidden && this.currentSessionId && this.currentSessionId !== '_pending_') {
                        this.loadTasks();
                    }
                }, desired);
            }
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
                const viewportHeight = window.innerHeight;
                const _pos = (top) => ({
                    top, left: Math.round(rect.left),
                    right: Math.round(window.innerWidth - rect.right),
                    align: isRight ? 'right' : 'left',
                });
                // Default: position below button
                this.popoverPos = _pos(Math.round(rect.bottom + 4));
                // Wait for Alpine to render popover content, then flip above if it overflows
                setTimeout(() => {
                    const el = document.getElementById('global-popover');
                    if (!el) return;
                    const ph = el.offsetHeight;
                    if (ph === 0) return;
                    if (rect.bottom + 4 + ph > viewportHeight - 8) {
                        this.popoverPos = _pos(Math.max(4, Math.round(rect.top - ph - 4)));
                    }
                }, 50);
            }
        },

        // --- Rewind (toolbar alias) ---

        async rewindToRound(roundIndex) {
            return this.rewindMessage(roundIndex);
        },

        // --- Chat ---

        async sendMessage() {
            let text = this.inputText.trim();
            if ((!text && !this.uploadedFiles.length) || this.isLoading) return;
            // Auto-attach file references if files were uploaded
            if (this.uploadedFiles.length) {
                const fileRefs = this.uploadedFiles.map(f => `分析文件: ${f}`).join('\n');
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
                role: 'assistant', content: '', toolCalls: [], artifacts: [],
                confirmation: null, isThinking: true, thinkingText: '思考中...', _copied: false,
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
                turn.content += `\n\n**Connection error:** ${e.message}`; // i18n: Connection error
                this.connectionError = e.message;
            } finally {
                if (!state._interrupted) {
                    state.isLoading = false;
                    // this.currentSessionId may have migrated from _pending_ to real ID
                    const activeSid = this.currentSessionId;
                    const stillOnSession = activeSid && activeSid !== '_pending_';
                    if (stillOnSession) {
                        this.isLoading = false;
                        this.turns = [...state.turns];
                    }
                }
                await this.loadSessions();
                await this.loadTasks();
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

            // Display the user's response as a visible user turn
            if (turn) turn.confirmation = null;
            state.turns.push({
                role: 'user', content: userResponse,
                roundIndex: this._countUserTurns(state.turns),
                isConfirmationResponse: true,
            });

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
                state.turns.push({
                    role: 'assistant', content: '', toolCalls: [], artifacts: [],
                    confirmation: null, isThinking: true, thinkingText: '恢复中...', _copied: false,
                });
                newTurn = state.turns[state.turns.length - 1];
                this.turns = [...state.turns];
                this._scrollToBottom();
                await this._processSSE(response, newTurn, state, sseSessionId);
            } catch (e) {
                const last = state.turns[state.turns.length - 1];
                if (last) {
                    last.isThinking = false;
                    last.content += `\n\n**Connection error:** ${e.message}`; // i18n: Connection error
                }
                if (this.currentSessionId === sseSessionId) {
                    this.connectionError = e.message;
                }
            } finally {
                state._resuming = false;
                if (!state._interrupted) {
                    state.isLoading = false;
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
            if (!confirm('停止当前对话？此操作无法撤销。')) return;
            const state = this._getSessionState(this.currentSessionId);
            state._interrupted = true;
            const turn = state.turns[state.turns.length - 1];
            if (turn && turn.role === 'assistant') {
                turn.isThinking = false;
                if (!turn.content) turn.content = '*已停止。*';
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

        _escapeHtml(value) {
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        },

        _chartRefsFromContent(content) {
            const refs = [];
            const pattern = /\[\[chart:([^\]\n]+)\]\]/g;
            let match;
            while ((match = pattern.exec(content || '')) !== null) {
                refs.push(match[1].trim());
            }
            return refs;
        },

        _artifactKeys(art) {
            const path = art && art.path ? String(art.path) : '';
            const file = path.split('/').pop() || '';
            const stem = file.replace(/\.html$/i, '');
            const desc = art && art.description ? String(art.description) : '';
            return [path, file, stem, desc].filter(Boolean);
        },

        _stripChartHash(value) {
            return String(value || '').replace(/\.html$/i, '').replace(/_[a-f0-9]{6}$/i, '');
        },

        _chartArtifactMatches(art, ref) {
            const normalized = String(ref || '').trim();
            if (!normalized) return { exact: false, fuzzy: false };
            const normalizedBase = this._stripChartHash(normalized);
            let exact = false;
            let fuzzy = false;
            for (const key of this._artifactKeys(art)) {
                const keyBase = this._stripChartHash(key);
                if (key === normalized || key.endsWith(normalized)) exact = true;
                if (normalizedBase.length >= 4 && keyBase.startsWith(normalizedBase)) fuzzy = true;
            }
            return { exact, fuzzy };
        },

        _artifactMatchesChartRef(art, ref) {
            const match = this._chartArtifactMatches(art, ref);
            return match.exact || match.fuzzy;
        },

        _chartArtifactFromText(text) {
            const match = String(text || '').match(/Chart saved:\s*(sessions\/\S+?\.html)/);
            if (!match) return null;
            const path = match[1];
            const desc = this._stripChartHash((path.split('/').pop() || '').replace(/\.html$/i, ''));
            return { path, type: 'chart', description: desc };
        },

        _artifactBelongsToSession(art, sessionId) {
            if (!art || !art.path || !sessionId || sessionId === '_pending_') return false;
            return String(art.path).startsWith(`sessions/${sessionId}/`);
        },

        _addTurnArtifact(turn, art, sessionId = this.currentSessionId) {
            if (!turn || !art || !art.path) return false;
            if (!turn.artifacts) turn.artifacts = [];
            if (turn.artifacts.some(existing => existing.path === art.path)) return false;
            turn.artifacts.push(art);
            if (sessionId === this.currentSessionId && this._artifactBelongsToSession(art, sessionId)) {
                if (!this.sessionArtifacts.some(existing => existing.path === art.path)) {
                    this.sessionArtifacts.push(art);
                }
            }
            return true;
        },

        _chartSearchArtifacts(turn) {
            const seen = new Set();
            const result = [];
            for (const art of [...((turn && turn.artifacts) || []), ...(this.sessionArtifacts || [])]) {
                if (!art || !art.path || seen.has(art.path)) continue;
                seen.add(art.path);
                result.push(art);
            }
            return result;
        },

        _findChartArtifact(turn, ref) {
            const artifacts = this._chartSearchArtifacts(turn);
            const exact = artifacts.filter(art => art && art.path && this._chartArtifactMatches(art, ref).exact);
            if (exact.length === 1) return { status: 'found', artifact: exact[0] };
            if (exact.length > 1) return { status: 'ambiguous', matches: exact };
            const fuzzy = artifacts.filter(art => art && art.path && this._chartArtifactMatches(art, ref).fuzzy);
            if (fuzzy.length === 1) return { status: 'found', artifact: fuzzy[0] };
            if (fuzzy.length > 1) return { status: 'ambiguous', matches: fuzzy };
            return { status: 'missing', matches: [] };
        },

        _chartArtifactHtml(art) {
            const src = this._escapeHtml(this.artifactUrl(art.path));
            const title = this._escapeHtml(art.description || art.type || 'chart');
            return `
<div class="inline-chart-artifact rounded-lg border border-stone-200 dark:border-stone-700 overflow-hidden bg-white dark:bg-stone-900 shadow-sm not-prose my-3" data-inline-chart="${title}">
  <div class="px-3 py-2 border-b border-stone-200 dark:border-stone-700 text-xs text-stone-500">${title}</div>
  <iframe src="${src}" class="w-full border-0" style="height:450px"></iframe>
</div>`;
        },

        _replaceChartReferences(text, turn) {
            if (!turn || !text) return text;
            return text.replace(/\[\[chart:([^\]\n]+)\]\]/g, (match, rawRef) => {
                const result = this._findChartArtifact(turn, rawRef.trim());
                if (result.status === 'ambiguous') {
                    return `<div class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-3 py-2 not-prose">Chart reference is ambiguous: ${this._escapeHtml(rawRef.trim())}</div>`;
                }
                if (result.status !== 'found') {
                    return `<div class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-3 py-2 not-prose">Chart reference not found: ${this._escapeHtml(rawRef.trim())}</div>`;
                }
                return this._chartArtifactHtml(result.artifact);
            });
        },

        supplementalArtifacts(turn) {
            const artifacts = (turn && turn.artifacts) || [];
            if (!artifacts.length) return [];
            const refs = this._chartRefsFromContent(turn.content || '');
            return artifacts.filter(art => !refs.some(ref => this._artifactMatchesChartRef(art, ref)));
        },

        renderMarkdown(text, turn = null) {
            if (!text) return '';
            // Pre-process: extract Plotly JSON outside code blocks
            text = this._replaceChartReferences(text, turn);
            text = this._extractPlotlyJson(text);
            // Extract math before markdown parsing
            const mathResult = this._extractMath(text);
            try {
                if (!this._markedReady) this._setupMarked();
                let html = marked.parse(mathResult.text);
                // Restore math placeholders with KaTeX output
                html = this._restoreMath(html, mathResult.mathBlocks);
                // Fix file links generated by LLM: /files/ → /api/files/
                return html.replace(/(href=["'])\/files\//g, '$1/api/files/');
            } catch { return text; }
        },

        _extractMath(text) {
            const mathBlocks = [];
            let result = text;
            let idx = 0;

            // Step 1: protect code blocks and inline code
            const codeBlocks = [];
            result = result.replace(/```[\s\S]*?```/g, (m) => {
                const ph = `%%CODE_BLOCK_${idx}%%`;
                codeBlocks.push({ ph, content: m });
                idx++;
                return ph;
            });
            result = result.replace(/`[^`\n]+`/g, (m) => {
                const ph = `%%CODE_INLINE_${idx}%%`;
                codeBlocks.push({ ph, content: m });
                idx++;
                return ph;
            });

            // Step 2: extract display math $$...$$
            result = result.replace(/\$\$([\s\S]+?)\$\$/g, (_, formula) => {
                const ph = `%%MATH_BLOCK_${idx}%%`;
                mathBlocks.push({ ph, formula: formula.trim(), display: true });
                idx++;
                return ph;
            });

            // Step 3: extract inline math $...$
            result = result.replace(/\$([^\$\n]+?)\$/g, (_, formula) => {
                const ph = `%%MATH_INLINE_${idx}%%`;
                mathBlocks.push({ ph, formula: formula.trim(), display: false });
                idx++;
                return ph;
            });

            // Step 4: restore code blocks
            for (const cb of codeBlocks) {
                result = result.replace(cb.ph, cb.content);
            }

            return { text: result, mathBlocks };
        },

        _restoreMath(html, mathBlocks) {
            if (!mathBlocks.length || typeof katex === 'undefined') return html;
            for (const m of mathBlocks) {
                try {
                    const rendered = katex.renderToString(m.formula, {
                        displayMode: m.display,
                        throwOnError: false,
                    });
                    const replacement = m.display
                        ? `<div class="math-block">${rendered}</div>`
                        : rendered;
                    html = html.replace(m.ph, replacement);
                } catch {
                    html = html.replace(m.ph, m.display ? `$$${m.formula}$$` : `$${m.formula}$`);
                }
            }
            return html;
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
                            const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            return `<div class="mermaid-container"><div class="mermaid" id="${id}">${escaped}</div></div>`;
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
            if (typeof mermaid !== 'undefined') {
                const mermaidDivs = el.querySelectorAll('.mermaid:not([data-processed])');
                for (const div of mermaidDivs) {
                    // Use a throwaway render id — mermaid.render() removes the DOM element
                    // whose id matches the renderId, so we must NOT use div.id here
                    const renderId = 'mr-' + Math.random().toString(36).slice(2, 10);
                    try {
                        const { svg } = await mermaid.render(renderId, div.textContent);
                        div.innerHTML = svg;
                    } catch (e) {
                        const msg = (e.message || e || 'Unknown error').substring(0, 120);
                        div.innerHTML = `<div class="mermaid-error">Diagram render error: ${msg}</div>`;
                    } finally {
                        const temp = document.getElementById('d' + renderId);
                        if (temp) temp.remove();
                        div.setAttribute('data-processed', 'true');
                    }
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

        async exportSingleReply(turn, format = 'markdown') {
            if (!turn.content) return;
            if (format === 'html') {
                const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2em auto;padding:0 1em;line-height:1.7;color:#333;}pre{background:#f5f5f5;padding:1em;border-radius:6px;overflow-x:auto;}code{font-family:Menlo,Consolas,monospace;font-size:0.85em;}</style></head><body>${this.renderMarkdown(turn.content, turn)}</body></html>`;
                const blob = new Blob([html], { type: 'text/html' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a'); a.href = url; a.download = 'reply.html'; a.click();
                URL.revokeObjectURL(url);
            } else {
                const blob = new Blob([turn.content], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a'); a.href = url; a.download = 'reply.md'; a.click();
                URL.revokeObjectURL(url);
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
            if (!path) return '';
            // Encode each segment but preserve slashes so Flask <path:> routes correctly
            return '/api/files/' + path.split('/').map(encodeURIComponent).join('/');
        },

        injectChartPlotly(event) {
            const iframe = event.target;
            try {
                const doc = iframe.contentDocument;
                if (!doc) return;
                // Skip if Plotly script already included (new charts with include_plotlyjs)
                if (doc.querySelector('script[src*="plotly"]')) return;
                // Only process chart iframes that need Plotly
                if (!doc.querySelector('.plotly-graph-div')) return;
                const chartScript = doc.querySelector('body > script:not([src])');
                if (!chartScript) return;
                // Inject Plotly.js, then re-run the chart script
                const script = doc.createElement('script');
                script.src = '/static/js/plotly-3.5.0.min.js';
                doc.head.appendChild(script);
                script.onload = () => {
                    const ns = doc.createElement('script');
                    ns.textContent = chartScript.textContent;
                    chartScript.replaceWith(ns);
                };
            } catch(e) { /* cross-origin */ }
        },

        // --- SSE ---

        async _processSSE(response, turn, state, sessionId) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            // Track the effective sessionId — updated when turn_start migrates _pending_
            let effectiveSid = sessionId;
            while (true) {
                let result;
                try { result = await reader.read(); } catch {
                    turn.isThinking = false;
                    if (!turn.content) turn.content = '**连接已断开。**';
                    this.connectionError = '连接已断开';
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
                        try {
                            const updated = this._handleEvent(eventType, JSON.parse(eventData), turn, state, effectiveSid);
                            if (updated) effectiveSid = updated;
                        } catch (e) { console.error('SSE event error:', eventType, e); }
                        eventType = ''; eventData = '';
                    }
                }
            }
            turn.isThinking = false;
            state.isLoading = false;
            if (this.currentSessionId === effectiveSid) this.isLoading = false;
            this._stopThinkingCycle();
            this.connectionError = '';
        },

        _handleEvent(type, data, turn, state, sessionId) {
            let isCurrentSession = (this.currentSessionId === sessionId);
            // Return value: new sessionId if migrated from _pending_, else undefined
            let migratedSid;

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
                        migratedSid = sessionId;
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
                    turn.thinkingText = this._thinkingStates[0];
                    this._startThinkingCycle(turn);
                    if (data.pct !== undefined) {
                        state.tokenPct = data.pct;
                        state.tokenSupported = true;
                        if (isCurrentSession) { this.tokenPct = data.pct; this.tokenSupported = true; }
                    }
                    break;
                case 'text_delta':
                    turn.isThinking = false;
                    turn.content = (turn.content || '') + data.text;
                    if (isCurrentSession) {
                        this._scrollToBottom();
                    }
                    break;
                case 'tool_call':
                    turn.isThinking = true;
                    turn.thinkingText = `正在执行 ${data.name}...`;
                    state.activeSteps.push({
                        tool_call_id: data.tool_call_id, name: data.name,
                        arguments: data.arguments, duration_ms: 0,
                        result_summary: '', status: 'running', _expanded: false,
                    });
                    break;
                case 'tool_result':
                    turn.isThinking = true;
                    turn.thinkingText = '处理结果中...';
                    const step = state.activeSteps.find(s => s.tool_call_id === data.tool_call_id);
                    if (step) {
                        step.status = 'done';
                        step.duration_ms = data.duration_ms || 0;
                        const web = data.web || {};
                        step.result_summary = web.summary || web.content || '';
                        if (web.artifacts) {
                            for (const art of web.artifacts) {
                                if (art.path) this._addTurnArtifact(turn, art, sessionId);
                            }
                        }
                        const chartArtifact = this._chartArtifactFromText(web.summary || web.content || '');
                        if (chartArtifact) this._addTurnArtifact(turn, chartArtifact, sessionId);
                        if ((web.artifacts && web.artifacts.length) || chartArtifact) {
                            this.loadSessionArtifacts(sessionId);
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
                        confirmation_type: data.confirmation_type || '',
                        blocking_reason: data.blocking_reason || '',
                        related_task_id: data.related_task_id || '',
                        related_spec_id: data.related_spec_id || '',
                        _resuming: false,
                        _state: this._initConfirmationState(),
                    };
                    if (isCurrentSession) {
                        this.turns = [...state.turns];
                    }
                    break;
                case 'turn_end':
                    turn.isThinking = false;
                    state.isLoading = false;
                    this._debouncedLoadTasks();
                    if (isCurrentSession) {
                        this.isLoading = false;
                        this.turns = [...state.turns];
                        this._scrollToBottom();
                        requestAnimationFrame(() => {
                            const el = document.getElementById('messages-container');
                            if (el) this._renderMermaidInElement(el);
                        });
                    }
                    if (data.pct !== undefined) {
                        state.tokenPct = data.pct;
                        state.tokenSupported = true;
                        if (isCurrentSession) { this.tokenPct = data.pct; this.tokenSupported = true; }
                    }
                    break;
                case 'error':
                    turn.isThinking = false;
                    turn.content += `\n\n**Error:** ${data.message}`; // i18n: Error
                    if (isCurrentSession) {
                        this.turns = [...state.turns];
                    }
                    break;
            }
            return migratedSid;
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
                    const newContent = msg.content || '';
                    if (currentAssistant) {
                        // Merge consecutive assistant messages within same round
                        if (newContent.trim()) {
                            currentAssistant.content = currentAssistant.content.trim()
                                ? currentAssistant.content + '\n\n' + newContent
                                : newContent;
                        }
                    } else {
                        currentAssistant = {
                            role: 'assistant', content: newContent,
                            toolCalls: [], artifacts: [], confirmation: null,
                            isThinking: false, _copied: false,
                        };
                    }
                } else if (msg.role === 'tool' && currentAssistant) {
                    const c = msg.content || '';
                    const chartMatch = c.match(/Chart saved:\s*(sessions\/\S+\.html)/);
                    if (chartMatch) {
                        const art = this._chartArtifactFromText(c);
                        if (art) this._addTurnArtifact(currentAssistant, art, this.currentSessionId);
                    }
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

        _setupRenderObserver() {
            const container = document.getElementById('messages-container');
            if (!container || this._observerSetup) return;
            this._observerSetup = true;
            const self = this;
            const observer = new MutationObserver((mutations) => {
                // Skip mermaid/plotly rendering while streaming to avoid errors on incomplete code blocks
                if (self.isLoading) return;
                let needsRender = false;
                for (const mutation of mutations) {
                    for (const node of mutation.addedNodes) {
                        if (node.nodeType === 1 && (
                            (node.querySelector && (node.querySelector('.mermaid:not([data-processed])') || node.querySelector('.plotly-chart:not([data-processed])'))) ||
                            node.matches && (node.matches('.mermaid:not([data-processed])') || node.matches('.plotly-chart:not([data-processed])'))
                        )) {
                            needsRender = true;
                            break;
                        }
                    }
                    if (needsRender) break;
                }
                if (needsRender) {
                    requestAnimationFrame(() => self._renderMermaidInElement(container));
                }
            });
            observer.observe(container, { childList: true, subtree: true });
        },
    };
}
