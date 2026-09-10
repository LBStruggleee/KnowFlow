// KnowFlow Demo Application
(function() {
    'use strict';

    // State
    const state = {
        currentView: 'chat',
        messages: [],
        isAsking: false,
        currentKbId: 1,
        settings: { ...MockData.settings },
        conversations: [...MockData.conversations],
        currentConversationId: 1,
    };

    // DOM Elements
    const elements = {
        // Views
        chatView: document.getElementById('chatView'),
        kbView: document.getElementById('kbView'),
        settingsView: document.getElementById('settingsView'),
        
        // Navigation
        navItems: document.querySelectorAll('.nav-item'),
        navBtns: document.querySelectorAll('.nav-btn'),
        
        // Chat
        messageStream: document.getElementById('messageStream'),
        questionInput: document.getElementById('questionInput'),
        sendBtn: document.getElementById('sendBtn'),
        sendIcon: document.getElementById('sendIcon'),
        tracePanel: document.getElementById('tracePanel'),
        bestScoreTag: document.getElementById('bestScoreTag'),
        traceSummary: document.getElementById('traceSummary'),
        traceMatches: document.getElementById('traceMatches'),
        welcomeMessage: document.getElementById('welcomeMessage'),
        kbSelect: document.getElementById('kbSelect'),
        hintTopK: document.getElementById('hintTopK'),
        
        // KB
        kbList: document.getElementById('kbList'),
        docList: document.getElementById('docList'),
        chunkSection: document.getElementById('chunkSection'),
        chunkList: document.getElementById('chunkList'),
        uploadArea: document.getElementById('uploadArea'),
        docCountLabel: document.getElementById('docCountLabel'),
        
        // Settings
        topKSlider: document.getElementById('topKSlider'),
        topKValue: document.getElementById('topKValue'),
        thresholdSlider: document.getElementById('thresholdSlider'),
        thresholdValue: document.getElementById('thresholdValue'),
        tempSlider: document.getElementById('tempSlider'),
        tempValue: document.getElementById('tempValue'),
        modelSelect: document.getElementById('modelSelect'),
        maxMessages: document.getElementById('maxMessages'),
        maxChars: document.getElementById('maxChars'),
        saveSettingsBtn: document.getElementById('saveSettingsBtn'),
        resetSettingsBtn: document.getElementById('resetSettingsBtn'),
        
        // Toast
        toastContainer: document.getElementById('toastContainer'),
        
        // History
        historyList: document.getElementById('historyList'),
        historyToggle: document.getElementById('historyToggle'),
        
        // Modal
        createKbModal: document.getElementById('createKbModal'),
        createKbBtn: document.getElementById('createKbBtn'),
        closeCreateKbModal: document.getElementById('closeCreateKbModal'),
        cancelCreateKb: document.getElementById('cancelCreateKb'),
        confirmCreateKb: document.getElementById('confirmCreateKb'),
        newKbName: document.getElementById('newKbName'),
        newKbCategory: document.getElementById('newKbCategory'),
        newKbDescription: document.getElementById('newKbDescription'),
        
        // System Status
        statusKbCount: document.getElementById('statusKbCount'),
        statusDocCount: document.getElementById('statusDocCount'),
        statusChunkCount: document.getElementById('statusChunkCount'),
        statusConvCount: document.getElementById('statusConvCount'),
        statusMsgCount: document.getElementById('statusMsgCount'),
        statusTokenUsage: document.getElementById('statusTokenUsage'),
    };

    // === View Switching ===
    function switchView(viewName) {
        state.currentView = viewName;
        
        // Update nav items
        elements.navItems.forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });
        
        // Update nav buttons
        elements.navBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === viewName);
        });
        
        // Switch views
        document.querySelectorAll('.view').forEach(view => {
            view.classList.remove('active');
        });
        
        const targetView = document.getElementById(viewName + 'View');
        if (targetView) {
            targetView.classList.add('active');
        }
        
        // Refresh view data
        if (viewName === 'kb') {
            renderKbList();
            renderDocList();
        } else if (viewName === 'settings') {
            updateSettingsUI();
            updateSystemStatus();
        }
    }

    // === Chat Functions ===
    async function handleAsk() {
        const question = elements.questionInput.value.trim();
        if (!question || state.isAsking) return;
        
        state.isAsking = true;
        elements.sendBtn.disabled = true;
        elements.sendIcon.textContent = '⏳';
        
        // Hide welcome message
        if (elements.welcomeMessage) {
            elements.welcomeMessage.style.display = 'none';
        }
        
        // Add user message
        addMessage('user', question);
        elements.questionInput.value = '';
        
        // Show loading
        const loadingId = addLoadingMessage();
        
        try {
            const response = await MockAPI.askQuestion(question);
            removeLoadingMessage(loadingId);
            
            // Stream the assistant message
            await streamMessage(response.answer, response.sources);
            
            // Show trace panel
            showTracePanel(response.retrievalTrace);
            
        } catch (error) {
            removeLoadingMessage(loadingId);
            showToast('请求失败，请重试', 'error');
        } finally {
            state.isAsking = false;
            elements.sendBtn.disabled = false;
            elements.sendIcon.textContent = '➤';
        }
    }

    function addMessage(role, content, sources = []) {
        const message = {
            id: Date.now(),
            role,
            content,
            sources,
            timestamp: new Date(),
        };
        state.messages.push(message);
        renderMessage(message);
        scrollToBottom();
    }

    async function streamMessage(content, sources) {
        const message = {
            id: Date.now(),
            role: 'assistant',
            content: '',
            sources,
            timestamp: new Date(),
        };
        state.messages.push(message);
        
        // Create message element
        const messageEl = document.createElement('div');
        messageEl.className = 'message-bubble message-assistant';
        messageEl.innerHTML = 
            <header>
                <span class="ai-dot"></span>
                <strong>AI 回答</strong>
            </header>
            <div class="message-content"></div>
        ;
        elements.messageStream.appendChild(messageEl);
        const contentEl = messageEl.querySelector('.message-content');
        
        // Add cursor
        const cursor = document.createElement('span');
        cursor.className = 'streaming-cursor';
        contentEl.appendChild(cursor);
        
        // Stream characters
        const chars = content.split('');
        for (let i = 0; i < chars.length; i++) {
            await new Promise(resolve => setTimeout(resolve, 15 + Math.random() * 10));
            contentEl.insertBefore(document.createTextNode(chars[i]), cursor);
            message.content += chars[i];
            scrollToBottom();
        }
        
        // Remove cursor
        cursor.remove();
        
        // Add sources
        if (sources && sources.length > 0) {
            const sourcesEl = document.createElement('div');
            sourcesEl.className = 'sources';
            sourcesEl.innerHTML = '<strong>引用来源：</strong>' + sources.map(s => 
                <div class="source-item">
                    <div class="source-meta">
                        <span>📄 </span>
                        <span>Score: </span>
                        <span>Chunk #</span>
                    </div>
                    <p>...</p>
                </div>
            ).join('');
            messageEl.appendChild(sourcesEl);
        }
        
        scrollToBottom();
    }

    function addLoadingMessage() {
        const id = 'loading-' + Date.now();
        const html = 
            <div class="message-bubble message-assistant" id="">
                <div class="loading-dots">
                    <span></span><span></span><span></span>
                </div>
            </div>
        ;
        elements.messageStream.insertAdjacentHTML('beforeend', html);
        scrollToBottom();
        return id;
    }

    function removeLoadingMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function renderMessage(message) {
        const isUser = message.role === 'user';
        const html = 
            <div class="message-bubble message-">
                <header>
                    
                    <strong></strong>
                </header>
                <div class="message-content">
                    
                </div>
                
            </div>
        ;
        elements.messageStream.insertAdjacentHTML('beforeend', html);
    }

    function formatContent(content) {
        // Simple markdown-like formatting
        return content
            .replace(/## (.*)/g, '<h2></h2>')
            .replace(/### (.*)/g, '<h3></h3>')
            .replace(/\*\*(.*?)\*\*/g, '<strong></strong>')
            .replace(/(.*?)/g, '<code></code>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');
    }

    function renderSources(sources) {
        const items = sources.map(s => 
            <div class="source-item">
                <div class="source-meta">
                    <span>📄 </span>
                    <span>Score: </span>
                    <span>Chunk #</span>
                </div>
                <p>...</p>
            </div>
        ).join('');
        return <div class="sources"><strong>引用来源：</strong></div>;
    }

    function showTracePanel(trace) {
        if (!trace) return;
        
        elements.tracePanel.style.display = 'block';
        elements.tracePanel.open = true;
        elements.bestScoreTag.textContent = 'Best: ' + trace.bestScore.toFixed(3);
        
        elements.traceSummary.innerHTML = 
            <span>请求 Top K: </span>
            <span>返回: </span>
            <span>最高分: </span>
            <span style="color: ">
                
            </span>
        ;
        
        // Simulated matches
        const matches = [
            { id: 1, score: trace.bestScore, content: '相关内容片段，展示检索到的文档内容...' },
            { id: 2, score: trace.bestScore - 0.07, content: '另一个相关段落，提供更多上下文信息...' },
            { id: 3, score: trace.bestScore - 0.14, content: '补充说明内容，帮助理解主题...' },
        ];
        
        elements.traceMatches.innerHTML = matches.map(m => 
            <div class="trace-match">
                <div class="trace-match-header">
                    <span>Chunk #</span>
                    <span>Score: </span>
                </div>
                <p></p>
            </div>
        ).join('');
    }

    function scrollToBottom() {
        elements.messageStream.scrollTop = elements.messageStream.scrollHeight;
    }

    // === KB View Functions ===
    function renderKbList() {
        const html = MockData.knowledgeBases.map(kb => 
            <div class="kb-item " data-id="">
                <div class="kb-item-info">
                    <strong></strong>
                    <span></span>
                </div>
                <span class="kb-item-count"> 文档</span>
            </div>
        ).join('');
        elements.kbList.innerHTML = html;
        
        // Add click handlers
        elements.kbList.querySelectorAll('.kb-item').forEach(item => {
            item.addEventListener('click', () => {
                state.currentKbId = parseInt(item.dataset.id);
                renderKbList();
                renderDocList();
                const kb = MockData.knowledgeBases.find(k => k.id === state.currentKbId);
                showToast(已切换到知识库: , 'success');
            });
        });
        
        // Update kb select in chat
        elements.kbSelect.innerHTML = MockData.knowledgeBases.map(kb => 
            <option value="" ></option>
        ).join('');
    }

    function renderDocList(filter = 'all') {
        let docs = MockData.documents.filter(d => d.kbId === state.currentKbId);
        
        if (filter !== 'all') {
            docs = docs.filter(d => d.status === filter);
        }
        
        elements.docCountLabel.textContent = ${docs.length} 个文档;
        
        const html = docs.map(doc => 
            <div class="doc-item" data-id="">
                <div class="doc-icon"></div>
                <div class="doc-info">
                    <strong></strong>
                    <span> · </span>
                </div>
                <div class="doc-status ">
                    
                    
                </div>
                <div class="doc-chunks"></div>
                <button class="icon-btn small" data-action="" data-id="">
                    
                </button>
            </div>
        ).join('');
        
        elements.docList.innerHTML = html || '<p style="color: var(--color-muted); text-align: center; padding: 20px;">暂无文档</p>';
        
        // Add click handlers
        elements.docList.querySelectorAll('.doc-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.closest('.icon-btn')) return;
                const docId = parseInt(item.dataset.id);
                showChunks(docId);
            });
        });
        
        elements.docList.querySelectorAll('.icon-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                const docId = parseInt(btn.dataset.id);
                if (action === 'retry') {
                    handleRetry(docId);
                } else {
                    handleDelete(docId);
                }
            });
        });
    }

    function getFileIcon(type) {
        const icons = { PDF: '📄', Markdown: '📝', PPTX: '📊', DOCX: '📃' };
        return icons[type] || '📄';
    }

    function getStatusText(status) {
        const texts = { finished: '已完成', processing: '处理中', failed: '失败' };
        return texts[status] || status;
    }

    function showChunks(docId) {
        elements.chunkSection.style.display = 'block';
        const html = MockData.chunks.map(chunk => 
            <div class="chunk-item">
                <div class="chunk-header">
                    <span>Chunk #</span>
                    <span>Token: </span>
                </div>
                <p></p>
            </div>
        ).join('');
        elements.chunkList.innerHTML = html;
    }

    async function handleRetry(docId) {
        showToast('正在重新处理文档...', 'warning');
        await MockAPI.retryDocument(docId);
        showToast('文档已重新提交处理', 'success');
    }

    async function handleDelete(docId) {
        if (!confirm('确定要删除这个文档吗？')) return;
        await MockAPI.deleteDocument(docId);
        showToast('文档已删除', 'success');
        renderDocList();
    }

    async function handleRebuildIndex() {
        showToast('正在重建索引...', 'warning');
        const result = await MockAPI.rebuildIndex(state.currentKbId);
        showToast(索引重建完成，共  个分块, 'success');
    }

    // === Settings Functions ===
    function updateSettingsUI() {
        elements.topKSlider.value = state.settings.topK;
        elements.topKValue.textContent = state.settings.topK;
        elements.thresholdSlider.value = state.settings.threshold * 100;
        elements.thresholdValue.textContent = state.settings.threshold.toFixed(2);
        elements.tempSlider.value = state.settings.temperature * 10;
        elements.tempValue.textContent = state.settings.temperature.toFixed(2);
        elements.modelSelect.value = state.settings.model;
        elements.maxMessages.value = state.settings.maxMessages;
        elements.maxChars.value = state.settings.maxChars;
        
        // Update hint in chat
        elements.hintTopK.textContent = state.settings.topK;
    }

    function updateSystemStatus() {
        const totalDocs = MockData.documents.length;
        const totalChunks = MockData.documents.reduce((sum, d) => sum + (d.chunks || 0), 0);
        
        elements.statusKbCount.textContent = MockData.knowledgeBases.length;
        elements.statusDocCount.textContent = totalDocs;
        elements.statusChunkCount.textContent = totalChunks;
        elements.statusConvCount.textContent = state.conversations.length;
        elements.statusMsgCount.textContent = state.messages.length;
        elements.statusTokenUsage.textContent = '45.2K';
    }

    function handleSaveSettings() {
        state.settings.topK = parseInt(elements.topKSlider.value);
        state.settings.threshold = parseInt(elements.thresholdSlider.value) / 100;
        state.settings.temperature = parseInt(elements.tempSlider.value) / 10;
        state.settings.model = elements.modelSelect.value;
        state.settings.maxMessages = parseInt(elements.maxMessages.value);
        state.settings.maxChars = parseInt(elements.maxChars.value);
        
        MockAPI.saveSettings(state.settings).then(() => {
            showToast('设置已保存', 'success');
            updateSettingsUI();
        });
    }

    function handleResetSettings() {
        state.settings = { ...MockData.settings };
        updateSettingsUI();
        showToast('已重置为默认设置', 'success');
    }

    // === Knowledge Base Modal Functions ===
    function openCreateKbModal() {
        elements.createKbModal.classList.add('active');
        elements.newKbName.value = '';
        elements.newKbCategory.value = '';
        elements.newKbDescription.value = '';
        elements.newKbName.focus();
    }

    function closeCreateKbModal() {
        elements.createKbModal.classList.remove('active');
    }

    async function handleCreateKb() {
        const name = elements.newKbName.value.trim();
        const category = elements.newKbCategory.value.trim();
        const description = elements.newKbDescription.value.trim();
        
        if (!name) {
            showToast('请输入知识库名称', 'error');
            return;
        }
        
        const result = await MockAPI.createKnowledgeBase({ name, category, description });
        MockData.knowledgeBases.push(result.kb);
        
        closeCreateKbModal();
        renderKbList();
        showToast('知识库创建成功', 'success');
    }

    // === Toast Notifications ===
    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = 	oast ;
        toast.textContent = message;
        elements.toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // === History Functions ===
    function renderHistoryList() {
        const html = state.conversations.map(conv => 
            <button class="history-item " data-id="">
                <span>
                    <strong></strong>
                    <em>#</em>
                </span>
            </button>
        ).join('');
        elements.historyList.innerHTML = html;
        
        elements.historyList.querySelectorAll('.history-item').forEach(item => {
            item.addEventListener('click', () => {
                state.currentConversationId = parseInt(item.dataset.id);
                renderHistoryList();
                showToast('已切换会话', 'success');
            });
        });
    }

    // === Event Listeners ===
    function initEventListeners() {
        // Navigation
        elements.navItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                switchView(item.dataset.view);
            });
        });
        
        elements.navBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                switchView(btn.dataset.view);
            });
        });
        
        // Chat
        elements.sendBtn.addEventListener('click', handleAsk);
        
        elements.questionInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAsk();
            }
        });
        
        // Suggested questions
        document.querySelectorAll('.suggestion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                elements.questionInput.value = btn.dataset.question;
                handleAsk();
            });
        });
        
        // KB Select change
        elements.kbSelect.addEventListener('change', (e) => {
            state.currentKbId = parseInt(e.target.value);
            const kb = MockData.knowledgeBases.find(k => k.id === state.currentKbId);
            document.getElementById('currentKbName').textContent = kb.name;
            document.getElementById('currentKbCategory').textContent = '分类: ' + kb.category;
        });
        
        // Settings sliders
        elements.topKSlider.addEventListener('input', (e) => {
            elements.topKValue.textContent = e.target.value;
        });
        
        elements.thresholdSlider.addEventListener('input', (e) => {
            elements.thresholdValue.textContent = (e.target.value / 100).toFixed(2);
        });
        
        elements.tempSlider.addEventListener('input', (e) => {
            elements.tempValue.textContent = (e.target.value / 10).toFixed(2);
        });
        
        elements.saveSettingsBtn.addEventListener('click', handleSaveSettings);
        elements.resetSettingsBtn.addEventListener('click', handleResetSettings);
        
        // Upload area
        elements.uploadArea.addEventListener('click', () => {
            showToast('演示模式：文件上传功能仅作展示', 'warning');
        });
        
        // Rebuild index
        document.getElementById('rebuildIndexBtn')?.addEventListener('click', handleRebuildIndex);
        
        // History toggle
        elements.historyToggle.addEventListener('click', () => {
            elements.historyList.style.display = 
                elements.historyList.style.display === 'none' ? 'grid' : 'none';
        });
        
        // Close chunk section
        document.getElementById('closeChunkBtn')?.addEventListener('click', () => {
            elements.chunkSection.style.display = 'none';
        });
        
        // Document filter
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                renderDocList(btn.dataset.filter);
            });
        });
        
        // Create KB modal
        elements.createKbBtn.addEventListener('click', openCreateKbModal);
        elements.closeCreateKbModal.addEventListener('click', closeCreateKbModal);
        elements.cancelCreateKb.addEventListener('click', closeCreateKbModal);
        elements.confirmCreateKb.addEventListener('click', handleCreateKb);
        
        elements.createKbModal.addEventListener('click', (e) => {
            if (e.target === elements.createKbModal) closeCreateKbModal();
        });
        
        // Keyboard shortcut
        document.addEventListener('keydown', (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                document.getElementById('commandSearch').focus();
            }
            if (e.key === 'Escape') {
                closeCreateKbModal();
            }
        });
    }

    // === Initialize ===
    function init() {
        initEventListeners();
        renderKbList();
        renderDocList();
        renderHistoryList();
        updateSettingsUI();
        updateSystemStatus();
        
        // Show welcome toast
        setTimeout(() => {
            showToast('欢迎使用 KnowFlow 演示版！', 'success');
        }, 500);
    }

    // Start app
    init();
})();
