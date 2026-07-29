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

        // Projects
        projects: [],
        activeProjectName: '',
        showNewProjectForm: false,
        newProjectName: '',
        expandedProjects: {},

        // Model
        modelName: '',
        availableModels: [],

        // Popover
        activePopover: null,

        // Config modal
        configModal: { show: false, model_id: '', api_base: '', api_key: '', has_key: false, saving: false },
        capabilityModal: {
            show: false,
            skills: [],
            mcpServers: [],
            newSkillName: '',
            newSkillSource: '',
            newMcpName: '',
            newMcpTransport: 'stdio',
            newMcpCommand: '',
            newMcpUrl: '',
            loading: false,
        },
        managementCenter: {
            show: false,
            section: 'skills',
            loading: false,
            knowledge: [],
            memory: [],
            evidence: [],
            evidenceQuery: '',
            globalQuery: '',
            globalResults: { knowledge: [], memory: [], evidence: [] },
            memorySources: null,
            domains: [],
        },
        managementDrawer: {
            show: false,
            kind: '',
            title: '',
            form: {},
        },

        // Artifacts modal
        artifactsModal: { show: false, sessionId: '', items: [] },
        sessionArtifacts: [],
        lastWorkbenchResult: null,

        // Workbench capabilities and analysis state
        capabilities: null,
        analysisState: null,
        trustInspectorCollapsed: false,
        sessionSidePanelTab: 'current',
        trustHelpOpen: '',
        expandedListCounts: {},
        trustView: null,
        trustLoading: false,
        trustError: '',
        expandedFullAnswer: false,

        // Bind-to-project modal
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

        _confirmationFromPayload(payload) {
            if (!payload) return null;
            return {
                confirmation_id: payload.confirmation_id,
                suspension_id: payload.confirmation_id,
                version: payload.version || 1,
                status: payload.status || 'suspended',
                question: payload.question || '',
                options: payload.options || [],
                context: payload.context || '',
                multi_select: !!payload.multi_select,
                allow_free_text: payload.allow_free_text !== false,
                confirmation_type: payload.confirmation_type || '',
                blocking_reason: payload.blocking_reason || '',
                related_task_id: payload.related_task_id || '',
                related_spec_id: payload.related_spec_id || '',
                skippable: payload.skippable !== false,
                _resuming: false,
                _error: '',
                _idempotencyKey: '',
                _state: this._initConfirmationState(),
            };
        },

        _restoreActiveConfirmation(state, payload) {
            const confirmation = payload?._state ? payload : this._confirmationFromPayload(payload);
            if (!confirmation) return;
            let turn = state.turns[state.turns.length - 1];
            if (!turn || turn.role !== 'assistant') {
                turn = {
                    role: 'assistant',
                    content: '',
                    roundIndex: this._countUserTurns(state.turns),
                    toolCalls: [],
                    artifacts: [],
                    confirmation: null,
                    isThinking: false,
                    thinkingText: '',
                    _copied: false,
                };
                state.turns.push(turn);
            }
            turn.isThinking = false;
            turn.confirmation = confirmation;
        },

        _initialized: false,

        async init() {
            if (this._initialized) return;
            this._initialized = true;
            await Promise.all([
                this.loadSessions(),
                this.loadProjects(),
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

        get projectGroups() {
            const groups = {};
            for (const s of this.filteredSessions) {
                const key = s.project_name || '';
                if (!groups[key]) groups[key] = [];
                groups[key].push(s);
            }
            return groups;
        },

        get unboundSessions() {
            return this.filteredSessions.filter(s => !s.project_name);
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
                workflow_notes: 0,
                recommended_paths: 0,
            };
        },

        get popoverTargetId() {
            if (!this.activePopover) return '';
            if (this.activePopover.startsWith('s-')) return this.activePopover.slice(2);
            if (this.activePopover.startsWith('u-')) return this.activePopover.slice(2);
            if (this.activePopover.startsWith('proj-')) return this.activePopover.slice(5);
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

        async loadCapabilityAdmin() {
            this.capabilityModal.show = true;
            this.capabilityModal.loading = true;
            try {
                const [skillsRes, mcpRes] = await Promise.all([
                    fetch('/api/skills'),
                    fetch('/api/mcp/servers'),
                ]);
                this.capabilityModal.skills = await skillsRes.json();
                this.capabilityModal.mcpServers = await mcpRes.json();
            } catch (e) {
                this.showToast('Capabilities load failed');
            }
            this.capabilityModal.loading = false;
        },

        async addSkill() {
            if (!this.capabilityModal.newSkillName || !this.capabilityModal.newSkillSource) return;
            await fetch('/api/skills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: this.capabilityModal.newSkillName,
                    source: this.capabilityModal.newSkillSource,
                }),
            });
            this.capabilityModal.newSkillName = '';
            this.capabilityModal.newSkillSource = '';
            await this.loadCapabilityAdmin();
        },

        async setSkillEnabled(skill, enabled) {
            await fetch(`/api/skills/${encodeURIComponent(skill.name)}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' });
            await this.loadCapabilityAdmin();
        },

        async deleteSkill(skill) {
            if (!confirm(`确定删除技能「${skill.name}」？`)) return;
            await fetch(`/api/skills/${encodeURIComponent(skill.name)}`, { method: 'DELETE' });
            await this.loadCapabilityAdmin();
            if (this.managementCenter.show) await this.loadManagementSection('skills');
        },

        async addMcpServer() {
            if (!this.capabilityModal.newMcpName) return;
            await fetch('/api/mcp/servers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: this.capabilityModal.newMcpName,
                    transport: this.capabilityModal.newMcpTransport,
                    command: this.capabilityModal.newMcpCommand,
                    url: this.capabilityModal.newMcpUrl,
                    enabled: true,
                }),
            });
            this.capabilityModal.newMcpName = '';
            this.capabilityModal.newMcpCommand = '';
            this.capabilityModal.newMcpUrl = '';
            await this.loadCapabilityAdmin();
        },

        async setMcpEnabled(server, enabled) {
            await fetch(`/api/mcp/servers/${encodeURIComponent(server.name)}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' });
            await this.loadCapabilityAdmin();
        },

        async deleteMcpServer(server) {
            if (!confirm(`确定删除 MCP 服务器「${server.name}」？`)) return;
            await fetch(`/api/mcp/servers/${encodeURIComponent(server.name)}`, { method: 'DELETE' });
            await this.loadCapabilityAdmin();
            if (this.managementCenter.show) await this.loadManagementSection('mcp');
        },

        managementTitle() {
            return {
                skills: '技能',
                mcp: 'MCP 服务器',
                knowledge: '知识',
                memory: '记忆',
                evidence: '会话搜索',
            }[this.managementCenter.section] || '管理';
        },

        managementSubtitle() {
            return {
                skills: '管理全局可复用能力',
                mcp: '连接外部工具和数据源',
                knowledge: '维护用户确认的正式知识',
                memory: '审查从会话中提取的候选记忆',
                evidence: '跨会话检索历史内容和证据',
            }[this.managementCenter.section] || '';
        },

        async openManagementCenter(section = 'skills') {
            this.managementCenter.show = true;
            await this.loadManagementSection(section);
        },

        async loadManagementSection(section) {
            this.closeManagementDrawer();
            this.managementCenter.section = section;
            this.managementCenter.loading = true;
            try {
                if (section === 'skills' || section === 'mcp') {
                    await this.loadCapabilityAdmin();
                    this.capabilityModal.show = false;
                } else if (section === 'knowledge') {
                    const res = await fetch('/api/management/knowledge');
                    this.managementCenter.knowledge = res.ok ? await res.json() : [];
                } else if (section === 'memory') {
                    const res = await fetch('/api/management/memory');
                    this.managementCenter.memory = res.ok ? await res.json() : [];
                    this.managementCenter.memorySources = null;
                } else if (section === 'evidence') {
                    await this.searchEvidence();
                }
            } catch (e) {
                this.showToast('加载失败');
            }
            this.managementCenter.loading = false;
        },

        closeManagementDrawer() {
            this.managementDrawer = { show: false, kind: '', title: '', form: {} };
        },

        openSkillDrawer() {
            this.managementDrawer = {
                show: true,
                kind: 'skill',
                title: '添加技能',
                form: { name: '', source: '' },
            };
        },

        async saveSkillItem() {
            const form = this.managementDrawer.form || {};
            if (!form.name || !form.source) return;
            const res = await fetch('/api/skills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: form.name, source: form.source }),
            });
            if (!res.ok) {
                this.showToast('技能添加失败');
                return;
            }
            this.closeManagementDrawer();
            await this.loadManagementSection('skills');
        },

        openMcpDrawer() {
            this.managementDrawer = {
                show: true,
                kind: 'mcp',
                title: '添加 MCP 服务器',
                form: { name: '', transport: 'stdio', command: '', url: '' },
            };
        },

        async saveMcpServer() {
            const form = this.managementDrawer.form || {};
            if (!form.name) return;
            const res = await fetch('/api/mcp/servers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: form.name,
                    transport: form.transport || 'stdio',
                    command: form.command || '',
                    url: form.url || '',
                    enabled: true,
                }),
            });
            if (!res.ok) {
                this.showToast('服务器添加失败');
                return;
            }
            this.closeManagementDrawer();
            await this.loadManagementSection('mcp');
        },

        openKnowledgeDrawer(item = null) {
            this.managementDrawer = {
                show: true,
                kind: 'knowledge',
                title: item ? '编辑知识' : '新建知识',
                form: item ? { ...item } : { title: '', domain: 'general', summary: '', content: '' },
            };
        },

        async saveKnowledgeItem() {
            const form = this.managementDrawer.form || {};
            const payload = {
                title: form.title || '',
                domain: form.domain || 'general',
                summary: form.summary || '',
                content: form.content || '',
                tags: form.tags || [],
            };
            const url = form.id ? `/api/management/knowledge/${encodeURIComponent(form.id)}` : '/api/management/knowledge';
            const method = form.id ? 'PATCH' : 'POST';
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                this.showToast('知识保存失败');
                return;
            }
            this.closeManagementDrawer();
            await this.loadManagementSection('knowledge');
        },

        async deprecateKnowledge(item) {
            if (!confirm(`确定废弃知识「${item.title}」？`)) return;
            await fetch(`/api/management/knowledge/${encodeURIComponent(item.id)}/deprecate`, { method: 'POST' });
            await this.loadManagementSection('knowledge');
        },

        async restoreKnowledge(item) {
            await fetch(`/api/management/knowledge/${encodeURIComponent(item.id)}/restore`, { method: 'POST' });
            await this.loadManagementSection('knowledge');
        },

        async deleteKnowledge(item) {
            if (!confirm(`确定删除知识「${item.title}」？此操作不可撤销。`)) return;
            const res = await fetch(`/api/management/knowledge/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
            if (!res.ok) {
                this.showToast('删除失败');
                return;
            }
            await this.loadManagementSection('knowledge');
        },

        openMemoryDrawer(item = null) {
            const sourceIds = item?.source_evidence_ids || [];
            this.managementDrawer = {
                show: true,
                kind: 'memory',
                title: item ? '编辑记忆' : '新建记忆',
                form: item ? {
                    ...item,
                    memory_type: item.type || item.memory_type || 'workflow_pattern',
                    reason: item.reason || '',
                    review_note: item.review_note || '',
                    needs_review: !!item.needs_review,
                    dedup_key: item.dedup_key || '',
                    source_evidence_ids_text: Array.isArray(sourceIds) ? sourceIds.join('\n') : String(sourceIds || ''),
                } : {
                    summary: '',
                    memory_type: 'workflow_pattern',
                    text: '',
                    reason: '',
                    review_note: '',
                    needs_review: false,
                    dedup_key: '',
                    source_evidence_ids_text: '',
                },
            };
        },

        _memorySourceEvidenceIds(form) {
            if (form.source_evidence_ids_text === undefined && Array.isArray(form.source_evidence_ids)) {
                return form.source_evidence_ids;
            }
            return String(form.source_evidence_ids_text || '')
                .split(/[\n,]/)
                .map(v => v.trim())
                .filter(Boolean);
        },

        _memoryReviewPayload(form) {
            return {
                reason: form.reason || '',
                source_evidence_ids: this._memorySourceEvidenceIds(form),
                needs_review: !!form.needs_review,
                review_note: form.review_note || '',
                dedup_key: form.dedup_key || '',
            };
        },

        async saveMemoryCandidate() {
            const form = this.managementDrawer.form || {};
            const res = await fetch('/api/management/memory', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    summary: form.summary || '',
                    memory_type: form.memory_type || 'workflow_pattern',
                    text: form.text || '',
                    ...this._memoryReviewPayload(form),
                }),
            });
            if (!res.ok) {
                this.showToast('记忆保存失败');
                return;
            }
            this.closeManagementDrawer();
            await this.loadManagementSection('memory');
        },

        async updateMemory() {
            const form = this.managementDrawer.form || {};
            const res = await fetch(`/api/management/memory/${encodeURIComponent(form.id)}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    summary: form.summary || '',
                    memory_type: form.memory_type || form.type || 'workflow_pattern',
                    text: form.text || '',
                    domain: form.domain || 'general',
                    tags: form.tags || [],
                    ...this._memoryReviewPayload(form),
                }),
            });
            if (!res.ok) {
                this.showToast('记忆更新失败');
                return;
            }
            this.closeManagementDrawer();
            await this.loadManagementSection('memory');
        },

        async confirmMemoryCandidate(item) {
            await fetch(`/api/management/memory/${encodeURIComponent(item.id)}/confirm`, { method: 'POST' });
            await this.loadManagementSection('memory');
        },

        async rejectMemoryCandidate(item) {
            await fetch(`/api/management/memory/${encodeURIComponent(item.id)}/reject`, { method: 'POST' });
            await this.loadManagementSection('memory');
        },

        async deprecateMemory(item) {
            await fetch(`/api/management/memory/${encodeURIComponent(item.id)}/deprecate`, { method: 'POST' });
            await this.loadManagementSection('memory');
        },

        async promoteMemory(item) {
            const title = item.summary || (item.text || '').slice(0, 40) || '晋升知识';
            const res = await fetch(`/api/management/memory/${encodeURIComponent(item.id)}/promote`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, summary: item.summary || '' }),
            });
            if (!res.ok) {
                this.showToast('提升为知识失败');
                return;
            }
            await this.loadManagementSection('memory');
        },

        async deleteMemory(item) {
            if (!confirm(`确定删除记忆「${item.summary || item.text || item.id}」？`)) return;
            const res = await fetch(`/api/management/memory/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
            if (!res.ok) {
                this.showToast('只能删除候选或已拒绝的记忆');
                return;
            }
            await this.loadManagementSection('memory');
        },

        async extractMemoryCandidates() {
            const hasSavedSession = this.currentSessionId && this.currentSessionId !== '_pending_';
            if (!hasSavedSession) {
                this.showToast('请先打开一个会话');
                return;
            }
            const res = await fetch('/api/management/memory/extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.currentSessionId }),
            });
            if (!res.ok) {
                this.showToast('记忆提取失败');
                return;
            }
            const data = await res.json();
            this.showToast(`已创建 ${data.created || 0} 条候选记忆`);
            await this.loadManagementSection('memory');
        },

        async loadMemorySources(item) {
            this.managementCenter.memorySources = { memory_id: item.id, sources: [] };
            try {
                const res = await fetch(`/api/management/memory/${encodeURIComponent(item.id)}/sources`);
                if (!res.ok) {
                    this.showToast('来源证据加载失败');
                    return;
                }
                this.managementCenter.memorySources = await res.json();
                const count = (this.managementCenter.memorySources.sources || []).length;
                this.showToast(`来源证据 ${count} 条`);
            } catch (e) {
                this.managementCenter.memorySources = { memory_id: item.id, sources: [] };
                this.showToast('来源证据加载失败');
            }
        },

        async searchEvidence() {
            const q = encodeURIComponent(this.managementCenter.evidenceQuery || '');
            const res = await fetch(`/api/management/evidence/search?q=${q}`);
            this.managementCenter.evidence = res.ok ? await res.json() : [];
        },

        async indexEvidence() {
            if (!this.currentSessionId) {
                this.showToast('请先打开一个会话');
                return;
            }
            const res = await fetch('/api/management/evidence/index', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.currentSessionId }),
            });
            if (!res.ok) {
                this.showToast('证据索引失败');
                return;
            }
            await this.searchEvidence();
        },

        async globalManagementSearch() {
            const q = encodeURIComponent(this.managementCenter.globalQuery || '');
            const res = await fetch(`/api/management/search?q=${q}`);
            this.managementCenter.globalResults = res.ok ? await res.json() : { knowledge: [], memory: [], evidence: [] };
        },

        // --- Sessions ---

        async loadSessions({ preserveConnectionError = false } = {}) {
            try {
                const res = await fetch('/api/sessions');
                this.sessions = await res.json();
                if (!preserveConnectionError) this.connectionError = '';
            } catch (e) {
                if (!preserveConnectionError) this.connectionError = '加载会话失败';
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
                    this.showToast(`已回滚到 Round ${roundIndex}`);
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
            this.activeProjectName = '';
            this.analysisState = null;
            this.trustView = null;
            this.trustLoading = false;
            this.trustError = '';
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
            this.activeProjectName = '';
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
                    this.activeProjectName = data.project_name || '';
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
                // Find activeProjectName from sessions list
                const sess = this.sessions.find(s => s.session_id === sessionId);
                if (sess) this.activeProjectName = sess.project_name || '';
            }
            try {
                const confirmationRes = await fetch(`/api/sessions/${sessionId}`);
                const data = await confirmationRes.json();
                const activeConfirmation = this._confirmationFromPayload(data.active_confirmation);
                this._restoreActiveConfirmation(state, activeConfirmation);
                this.turns = state.turns;
            } catch {}
            await Promise.all([
                this.loadAnalysisState(sessionId),
                this.loadTrustView(sessionId),
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
                this.trustView = null;
                this.trustLoading = false;
                this.trustError = '';
            }
            // Also refresh from server to ensure consistency
            await this.loadSessions();
        },

        // --- Objects ---

        async loadProjects() {
            try {
                const res = await fetch('/api/projects');
                this.projects = await res.json();
            } catch {}
        },

        async createProject() {
            const name = this.newProjectName.trim();
            if (!name) return;
            try {
                const res = await fetch('/api/projects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name }),
                });
                if (res.ok) {
                    this.newProjectName = '';
                    this.showNewProjectForm = false;
                    await this.loadProjects();
                } else {
                    const data = await res.json();
                    alert(data.error || 'Failed to create project');
                }
            } catch {}
        },

        async deleteProject(projectName) {
            if (!confirm(`确认删除项目 "${projectName}" 并解除所有会话绑定？`)) return;
            try {
                const res = await fetch(`/api/projects/${encodeURIComponent(projectName)}`, { method: 'DELETE' });
                if (res.ok) {
                    await this.loadProjects();
                    await this.loadSessions();
                } else {
                    const data = await res.json();
                    alert(data.error || 'Failed');
                }
            } catch {}
        },

        async renameProject(projectName) {
            const newName = prompt(`将 "${projectName}" 重命名为：`, projectName);
            if (!newName || newName === projectName) return;
            try {
                const res = await fetch(`/api/projects/${encodeURIComponent(projectName)}/rename`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_name: newName }),
                });
                if (res.ok) {
                    await this.loadProjects();
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

        async bindSessionToProject(sessionId, projectName) {
            if (!projectName) {
                // Show project selection modal
                this._bindModal = { show: true, sessionId };
                this.activePopover = null;
                return;
            }
            try {
                const res = await fetch('/api/projects/bind', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId, name: projectName }),
                });
                const data = await res.json();
                if (res.ok) {
                    await this.loadSessions();
                    await this.loadProjects();
                    if (this.currentSessionId === sessionId) {
                        this.activeProjectName = projectName;
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
                    await this.loadProjects();
                    if (this.currentSessionId === sessionId) {
                        this.activeProjectName = '';
                    }
                } else {
                    alert(data.error || 'Unbind failed');
                }
            } catch (e) {
                alert('Unbind failed: ' + e.message);
            }
            this.activePopover = null;
        },

        toggleProject(projectName) {
            this.expandedProjects[projectName] = !this.expandedProjects[projectName];
        },

        isProjectExpanded(projectName) {
            return !!this.expandedProjects[projectName];
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
                if (sessionId === this.currentSessionId) this.sessionArtifacts = [];
                return;
            }
            try {
                const res = await fetch(`/api/sessions/${sessionId}/artifacts-list`);
                const artifacts = res.ok ? await res.json() : [];
                if (sessionId === this.currentSessionId) {
                    this.sessionArtifacts = artifacts;
                    this.turns = [...this.turns];
                }
            } catch {
                if (sessionId === this.currentSessionId) this.sessionArtifacts = [];
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

        async loadTrustView(sessionId = this.currentSessionId) {
            if (!sessionId || sessionId === '_pending_') {
                this.trustView = null;
                this.trustLoading = false;
                this.trustError = '';
                return;
            }
            if (sessionId !== this.currentSessionId) return;
            this.trustView = null;
            this.trustLoading = true;
            this.trustError = '';
            try {
                const res = await fetch(`/api/sessions/${sessionId}/trust`);
                if (!res.ok) throw new Error('Trust inspector load failed');
                const data = await res.json();
                if (sessionId === this.currentSessionId) {
                    this.trustView = data;
                    this.trustError = '';
                }
            } catch {
                if (sessionId === this.currentSessionId) {
                    this.trustView = null;
                    this.trustError = 'Trust status unavailable';
                }
            } finally {
                if (sessionId === this.currentSessionId) {
                    this.trustLoading = false;
                }
            }
        },

        multifileWorkbench() {
            return this.trustView?.workbench?.multifile_analysis || {};
        },

        actionBoard() {
            // Full empty shape (not {}) so the action-board x-show/x-text/x-for
            // don't throw before /trust resolves (no session / mid-load).
            // Mirrors backend _empty_action_board().
            return this.trustView?.workbench?.action_board || {
                confirmed: [],
                uncertain: [],
                next_steps: [],
                trust_basis: {
                    evidence_count: 0,
                    verified_claim_count: 0,
                    failed_count: 0,
                    downgraded_count: 0,
                    verification_status: 'not_run',
                    datasets_used: [],
                },
            };
        },
        fullAnswer()    { return this.trustView?.workbench?.full_answer || ''; },

        workbenchScope() {
            return this.trustView?.workbench?.details?.scope || {};
        },

        workbenchConfirmation() {
            return this.trustView?.workbench?.details?.confirmation || {};
        },

        multifileDataUnderstanding() {
            return this.multifileWorkbench().data_understanding || {};
        },

        multifileRelationships() {
            return this.multifileWorkbench().relationships || [];
        },

        visibleListItems(key, items, defaultLimit = 6) {
            const list = Array.isArray(items) ? items : [];
            const visible = Number(this.expandedListCounts[key] || defaultLimit);
            return list.slice(0, Math.max(0, visible));
        },

        hiddenListCount(key, items, defaultLimit = 6) {
            const list = Array.isArray(items) ? items : [];
            return Math.max(0, list.length - this.visibleListItems(key, list, defaultLimit).length);
        },

        showMoreListItems(key, items, step = 6, defaultLimit = 6) {
            const list = Array.isArray(items) ? items : [];
            const current = Number(this.expandedListCounts[key] || defaultLimit);
            this.expandedListCounts = {
                ...this.expandedListCounts,
                [key]: Math.min(list.length, current + step),
            };
        },

        collapseListItems(key) {
            const next = { ...this.expandedListCounts };
            delete next[key];
            this.expandedListCounts = next;
        },

        formatRiskMessage(message) {
            const text = String(message || '');
            const exact = {
                'Correlation does not imply causation': '相关性不代表因果关系',
                'No dimension column was identified': '未识别到可用于分组拆解的维度字段',
                'No metric column was identified': '未识别到可用于指标分析的数值指标字段',
                'Descriptive trend only unless supported by experimental evidence': '仅能做描述性趋势分析，除非有实验或准实验设计支持',
                'Comparison quality depends on period comparability and seasonality': '对比质量取决于两个周期是否可比，以及是否受季节性影响',
                'Requires stable user IDs and event history': '需要稳定的用户 ID 和完整事件历史',
                'Requires valid event steps or aggregate funnel columns': '需要有效的步骤事件，或已经汇总好的漏斗字段',
            };
            if (exact[text]) return exact[text];
            if (text.includes('Data is aggregate grain and missing user or entity id columns')) {
                return '当前数据粒度偏汇总，缺少稳定的用户或实体 ID，不能直接做用户级留存判断';
            }
            if (text.includes('100% missing values')) {
                return text.replace('Column', '字段').replace('has 100% missing values', '完全为空');
            }
            if (text.includes('Requires confirmation before treating as a dimension')) {
                return '该字段是否能作为维度需要先确认业务含义';
            }
            return text;
        },

        formatWorkbenchText(value, category = '') {
            const text = String(value || '');
            const labels = {
                confidence: { high: '高置信度', medium: '中等置信度', low: '低置信度' },
                route: {
                    trend: '趋势分析',
                    period_compare: '周期对比',
                    correlation: '相关性分析',
                    rate_analysis: '比率分析',
                },
                kind: { route: '推荐分析方向', data_gap: '数据缺口' },
                verification: { not_run: '尚未验证' },
                data: { 'Grain not identified': '未识别数据粒度' },
            };
            const translated = labels[category]?.[text];
            if (translated) return translated;
            return category === 'risk' || category === 'data'
                ? this.formatRiskMessage(text)
                : text;
        },

        trustStatusLabel(status) {
            const labels = {
                empty: '空',
                clear: '无需确认',
                needs_confirmation: '待确认',
                not_run: '尚未验证',
                ready: '就绪',
                ready_with_notes: '可用，有说明',
                ready_with_warnings: '有提醒',
                pass: '通过',
                pass_with_downgrades: '有降级',
                fail: '失败',
                blocked: '阻塞',
                warning: '提醒',
                proposed: '待验证',
                supported: '支持',
                inconclusive: '不确定',
                weakened: '减弱',
                unsupported_by_data: '数据不支持',
                confirmed: '已确认',
                resolved: '已处理',
                linked: '已关联',
                possibly_linked: '可能关联',
                user_scoped_latest_only: '用户选择',
                available: '可用',
                used: '本次使用',
                not_needed: '本次不需要',
                needs_decision: '需要你选择',
                unavailable: '暂不可用',
                excluded: '已排除',
                unknown: '未知',
            };
            return labels[status || 'unknown'] || labels.unknown;
        },

        trustHelpText(topic) {
            if (topic === 'outputs') {
                return '本会话可导出的对话和已生成产出物，可用于复核、归档和分享。';
            }
            return '';
        },

        trustStatusClass(status) {
            const classes = {
                clear: 'trust-pill-ok',
                needs_confirmation: 'trust-pill-warn',
                not_run: 'trust-pill-muted',
                ready: 'trust-pill-ok',
                ready_with_notes: 'trust-pill-warn',
                ready_with_warnings: 'trust-pill-warn',
                pass: 'trust-pill-ok',
                pass_with_downgrades: 'trust-pill-warn',
                warning: 'trust-pill-warn',
                proposed: 'trust-pill-muted',
                supported: 'trust-pill-ok',
                inconclusive: 'trust-pill-warn',
                weakened: 'trust-pill-warn',
                unsupported_by_data: 'trust-pill-blocked',
                confirmed: 'trust-pill-ok',
                resolved: 'trust-pill-ok',
                linked: 'trust-pill-ok',
                possibly_linked: 'trust-pill-warn',
                user_scoped_latest_only: 'trust-pill-ok',
                available: 'trust-pill-ok',
                used: 'trust-pill-ok',
                not_needed: 'trust-pill-muted',
                needs_decision: 'trust-pill-warn',
                unavailable: 'trust-pill-blocked',
                excluded: 'trust-pill-muted',
                fail: 'trust-pill-blocked',
                blocked: 'trust-pill-blocked',
                empty: 'trust-pill-muted',
                unknown: 'trust-pill-muted',
            };
            return classes[status || 'unknown'] || classes.unknown;
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

            state.turns.push({ role: 'user', content: text, roundIndex: this._countUserTurns(state.turns) + 1 });
            state.turns.push({
                role: 'assistant', content: '', toolCalls: [], artifacts: [],
                confirmation: null, isThinking: true, thinkingText: '思考中...', _copied: false,
            });
            this.turns = [...state.turns];
            state.turns = this.turns;
            const turn = this.turns[this.turns.length - 1];
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
                if (this._sessionStates[this.currentSessionId] === state) {
                    this.connectionError = e.message;
                }
            } finally {
                const isOriginCurrent = this._sessionStates[this.currentSessionId] === state;
                if (!state._interrupted) {
                    state.isLoading = false;
                    if (isOriginCurrent) {
                        this.isLoading = false;
                        this.turns = [...state.turns];
                        this._saveCurrentState();
                    }
                }
                await this.loadSessions({ preserveConnectionError: !isOriginCurrent });
                await this.loadTasks();
                if (isOriginCurrent) {
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

        async resumeConfirmation(userResponse, confirmation = null) {
            const state = this._getSessionState(this.currentSessionId);
            if (state._resuming) return;
            state._resuming = true;
            const turn = state.turns[state.turns.length - 1];
            confirmation = confirmation || turn?.confirmation;
            if (!confirmation || !confirmation.confirmation_id) {
                if (turn?.confirmation) turn.confirmation._error = 'Confirmation is no longer active. Reload the session.';
                state._resuming = false;
                return;
            }
            if (!confirmation._idempotencyKey) {
                confirmation._idempotencyKey = `web_${Date.now()}_${Math.random().toString(16).slice(2)}`;
            }
            if (turn?.confirmation) {
                turn.confirmation._resuming = true;
                turn.confirmation._error = '';
            }
            state._interrupted = false;
            let newTurn = null;
            const sseSessionId = this.currentSessionId;

            try {
                const response = await fetch('/api/chat/resume', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: this.currentSessionId,
                        confirmation_id: confirmation.confirmation_id,
                        expected_version: confirmation.version,
                        idempotency_key: confirmation._idempotencyKey,
                        user_response: userResponse,
                    }),
                });
                if (!response.ok) {
                    const errData = await response.json().catch(() => ({ error: response.statusText }));
                    if (turn) {
                        turn.confirmation = confirmation;
                        turn.confirmation._resuming = false;
                        turn.confirmation._error = errData.error || 'Confirmation failed. Please retry.';
                    }
                    state._resuming = false;
                    this.turns = [...state.turns];
                    return;
                }
                if (turn) turn.confirmation = null;
                state.turns.push({
                    role: 'user', content: userResponse,
                    roundIndex: this._countUserTurns(state.turns) + 1,
                    isConfirmationResponse: true,
                });
                state.turns.push({
                    role: 'assistant', content: '', toolCalls: [], artifacts: [],
                    confirmation: null, isThinking: true, thinkingText: '恢复中...', _copied: false,
                });
                this.turns = [...state.turns];
                state.turns = this.turns;
                const newTurn = this.turns[this.turns.length - 1];
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
                this.resumeConfirmation(response, c);
            } else {
                const response = this._submitSingleAnswer(c, st);
                this.resumeConfirmation(response, c);
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
                    this.resumeConfirmation(response, c);
                }
            } else {
                this.resumeConfirmation('skipped', c);
            }
        },

        _cancelConfirmation(turn) {
            const c = turn.confirmation;
            if (!c) return;
            this.resumeConfirmation('cancelled', c);
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

        _isDataBackedMermaid(text) {
            const source = String(text || '').trim();
            const lower = source.toLowerCase();
            if (lower.startsWith('xychart-beta')) return true;
            if (lower.startsWith('pie ') || lower.startsWith('pie\n')) {
                return /:\s*-?\d/.test(source);
            }
            return false;
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
                            if (self._isDataBackedMermaid(text)) {
                                return '<div class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-3 py-2 not-prose">Data-backed Mermaid charts are blocked. Use an interactive chart reference or a verified numeric table for analytical data.</div>';
                            }
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
            const isCurrentStreamSession = () => (
                this.currentSessionId === effectiveSid
                && this._sessionStates[effectiveSid] === state
            );
            while (true) {
                let result;
                try { result = await reader.read(); } catch {
                    turn.isThinking = false;
                    if (!turn.content) turn.content = '**连接已断开。**';
                    if (isCurrentStreamSession()) {
                        this.connectionError = '连接已断开';
                        this.turns = [...state.turns];
                        this._stopThinkingCycle();
                    }
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
            if (isCurrentStreamSession()) {
                this.isLoading = false;
                this._stopThinkingCycle();
                this.connectionError = '';
                this.turns = [...state.turns];
            }
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
                    if (isCurrentSession) this._startThinkingCycle(turn);
                    if (data.pct !== undefined) {
                        state.tokenPct = data.pct;
                        state.tokenSupported = true;
                        if (isCurrentSession) { this.tokenPct = data.pct; this.tokenSupported = true; }
                    }
                    if (isCurrentSession) this.turns = [...state.turns];
                    break;
                case 'analysis_progress':
                    // Safe live method narration. Server-authored label only —
                    // never append to turn.content (claims stay buffered until
                    // the final audited answer arrives via text_delta). The
                    // indicator is cleared by final publication or terminal
                    // error; the final status remains on the turn timeline.
                    turn.analysisProgress = {
                        code: data.code,
                        label: data.label,
                        status: data.status,
                        stepId: data.step_id || ''
                    };
                    turn.thinkingText = data.label;
                    if (isCurrentSession) this.turns = [...state.turns];
                    break;
                case 'text_delta':
                    turn.isThinking = false;
                    turn.content = (turn.content || '') + data.text;
                    if (isCurrentSession) this.turns = [...state.turns];
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
                    if (isCurrentSession) this.turns = [...state.turns];
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
                            if (isCurrentSession) this.loadSessionArtifacts(sessionId);
                        }
                    }
                    if (isCurrentSession) this.turns = [...state.turns];
                    break;
                case 'task_update':
                    this._debouncedLoadTasks();
                    break;
                case 'suspended':
                    turn.isThinking = false;
                    turn.confirmation = this._confirmationFromPayload({
                        confirmation_id: data.confirmation_id || data.suspension_id,
                        version: data.version || 1,
                        status: 'suspended',
                        question: data.question,
                        options: data.options || [],
                        context: data.context || '',
                        multi_select: !!data.multi_select,
                        confirmation_type: data.confirmation_type || '',
                        blocking_reason: data.blocking_reason || '',
                        related_task_id: data.related_task_id || '',
                        related_spec_id: data.related_spec_id || '',
                        skippable: data.skippable !== false,
                    });
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
                        this.loadTrustView();
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
