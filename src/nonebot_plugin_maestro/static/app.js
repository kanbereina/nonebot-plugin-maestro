function maestroApp() {
    return {
        bots: [],
        botsLoading: false,
        activeBot: null,
        scope: 'group',
        scopes: [
            { value: 'group',   label: '群聊' },
            { value: 'c2c',     label: '私聊' },
            { value: 'channel', label: '频道' },
            { value: 'dm',      label: '频道私信' }
        ],
        // 场景图标（内联 SVG，fill/stroke 用 currentColor 继承 .scope-tab-icon 的灰色）
        icons: {
            // 私聊：单用户
            c2c: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
                       stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="8" r="3.6"/>
                <path d="M4.5 20.5c0-3.6 3.4-6 7.5-6s7.5 2.4 7.5 6"/>
            </svg>`,
            // 群聊：多用户
            group: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
                         stroke-linecap="round" stroke-linejoin="round">
                <circle cx="9" cy="8" r="3.2"/>
                <path d="M2.5 20c0-3.3 2.9-5.5 6.5-5.5s6.5 2.2 6.5 5.5"/>
                <path d="M16.5 5.2a3.2 3.2 0 0 1 0 6"/>
                <path d="M18 14.9c2.2.6 3.5 2.2 3.5 4.4"/>
            </svg>`,
            // 频道：官方 guild.svg 的图形部分（原图 viewBox 98x26，
            // 右侧是文字，此处裁到 0 0 26 26 只取徽标）
            channel: `<svg viewBox="0 0 26 26" fill="none">
                <path d="M20.9003 8.98713H17.9705L18.2468 7.15772C18.2615 7.05993 18.1851 6.97363 18.0851 6.97363H16.1986C16.1163 6.97363 16.0487 7.03116 16.0369 7.1117L15.7519 8.98713H10.8327L11.1089 7.15772C11.1236 7.05993 11.0472 6.97363 10.9473 6.97363H9.06361C8.98133 6.97363 8.91375 7.03116 8.90199 7.1117L8.61695 8.98713H5.64014C5.55786 8.98713 5.49027 9.04466 5.47851 9.1252L5.22285 10.8165C5.20816 10.9143 5.28456 11.0006 5.38448 11.0006H8.31133L7.96164 13.3046C7.01247 13.1263 6.03391 13.0228 5.03184 13.0141C4.94956 13.0141 4.87904 13.0745 4.86728 13.1522L4.61162 14.8435C4.59693 14.9385 4.67627 15.0247 4.77325 15.0247C6.03685 15.0334 6.88904 15.1369 7.65896 15.2951L7.11826 18.8648C7.10356 18.9626 7.17997 19.0489 7.27988 19.0489H9.16353C9.24581 19.0489 9.3134 18.9913 9.32515 18.9108L9.78651 15.8762C11.6819 16.5608 13.3892 17.6308 14.8027 18.9885C15.4022 19.5637 16.416 19.2214 16.5394 18.4103L16.6129 17.9242L16.7481 17.0354H19.7249C19.8072 17.0354 19.8748 16.9778 19.8865 16.8973L20.1422 15.206C20.1569 15.1082 20.0805 15.0219 19.9805 15.0219H17.0507L17.662 10.9978H20.6388C20.7211 10.9978 20.7887 10.9402 20.8004 10.8597L21.0561 9.16834C21.0708 9.07055 20.9944 8.98425 20.8944 8.98425L20.9003 8.98713ZM15.3904 11.3746L14.7351 15.6863C14.6969 15.9308 14.4119 16.043 14.2062 15.9021C13.0278 15.088 11.7319 14.4264 10.3507 13.9432C10.2009 13.8914 10.1098 13.7447 10.1333 13.5894L10.483 11.2796C10.5065 11.1186 10.6475 11.0006 10.815 11.0006H15.0584C15.2641 11.0006 15.4198 11.179 15.3904 11.3774V11.3746Z" fill="currentColor"/>
                <path d="M0.240966 16.5783C0.649432 18.773 1.53101 19.9466 2.70646 20.9016C3.91129 21.8335 5.38941 22.5325 8.16051 22.8547C9.4153 23.0014 10.9434 23.0445 12.6742 23.0445C14.4051 23.0445 15.9331 23.0014 17.1879 22.8547C19.9561 22.5296 21.4371 21.8307 22.642 20.9016C23.8145 19.9466 24.699 18.773 25.1075 16.5783C25.2926 15.5831 25.3484 14.3721 25.3484 13C25.3484 11.628 25.2926 10.4141 25.1075 9.42177C24.699 7.22706 23.8174 6.05348 22.642 5.0985C21.4371 4.16654 19.959 3.46757 17.1879 3.14541C15.9331 2.99871 14.4051 2.95557 12.6742 2.95557C10.9434 2.95557 9.4153 2.99871 8.16051 3.14541C5.39234 3.47045 3.91129 4.16942 2.70646 5.0985C1.53101 6.0506 0.649432 7.22418 0.240966 9.41889C0.0558335 10.4141 0 11.6251 0 12.9972C0 14.3692 0.0558335 15.5831 0.240966 16.5754V16.5783ZM2.11286 9.75256C2.43023 8.04684 3.03264 7.25582 3.90247 6.54247C4.72528 5.90965 5.84489 5.28835 8.38385 4.9892C9.42118 4.86839 10.7847 4.81086 12.6713 4.81086C14.5579 4.81086 15.9214 4.86839 16.9587 4.9892C19.4977 5.28547 20.6173 5.90965 21.4401 6.54247C22.3099 7.25582 22.9123 8.04684 23.2297 9.75256C23.3737 10.5234 23.4413 11.5532 23.4413 12.9972C23.4413 14.4411 23.3737 15.4709 23.2297 16.2418C22.9123 17.9475 22.3099 18.7385 21.4401 19.4519C20.6173 20.0847 19.4977 20.706 16.9587 21.0051C15.9214 21.1259 14.5579 21.1835 12.6713 21.1835C10.7847 21.1835 9.42118 21.1259 8.38385 21.0051C5.84489 20.7089 4.72528 20.0847 3.90247 19.4519C3.03264 18.7385 2.43023 17.9475 2.11286 16.2418C1.96887 15.4709 1.90128 14.4411 1.90128 12.9972C1.90128 11.5532 1.96887 10.5234 2.11286 9.75256Z" fill="currentColor"/>
            </svg>`,
            // 频道私信：邮件
            dm: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
                      stroke-linecap="round" stroke-linejoin="round">
                <rect x="2.5" y="5" width="19" height="14" rx="2.5"/>
                <path d="M3.5 7.5l7.3 5.2a2 2 0 0 0 2.4 0l7.3-5.2"/>
            </svg>`,
            // 盾牌对勾（官方 role-tag 用的同一枚）
            shield: `<svg viewBox="0 0 18 21" fill="none" xmlns="http://www.w3.org/2000/svg"
                          width="100%" height="100%">
                <path d="M5.45107 8.58206C5.11913 8.25012 4.58094 8.25012 4.24899 8.58206C3.91704 8.91401 3.91704 9.4522 4.24899 9.78415L6.54188 12.077C7.26435 12.7995 8.43571 12.7995 9.15818 12.077L13.4511 7.78415C13.783 7.4522 13.783 6.91401 13.4511 6.58207C13.1191 6.25012 12.5809 6.25012 12.249 6.58207L7.9561 10.875C7.89752 10.9335 7.80254 10.9335 7.74396 10.875L5.45107 8.58206Z" fill="currentColor"/>
                <path fill-rule="evenodd" clip-rule="evenodd" d="M10.1475 0.198012C9.30264 -0.0660042 8.39736 -0.0660039 7.5525 0.198012L3.0525 1.60426C1.23649 2.17177 0 3.85363 0 5.75625V12.6258C0 13.1357 0.129965 13.6373 0.377626 14.0831C1.91478 16.8499 4.399 18.969 7.37363 20.0507L7.75887 20.1908C8.46371 20.4471 9.23629 20.4471 9.94113 20.1908L10.3264 20.0507C13.301 18.969 15.7852 16.8499 17.3224 14.0831C17.57 13.6373 17.7 13.1357 17.7 12.6258V5.75625C17.7 3.85363 16.4635 2.17177 14.6475 1.60426L10.1475 0.198012ZM8.05957 1.82063C8.57425 1.65979 9.12575 1.65979 9.64043 1.82063L14.1404 3.22688C15.2467 3.5726 16 4.59718 16 5.75625V12.6258C16 12.8468 15.9437 13.0642 15.8363 13.2575C14.498 15.6664 12.3352 17.5113 9.74541 18.453L9.36017 18.5931C9.03061 18.713 8.66939 18.713 8.33983 18.5931L7.95459 18.453C5.36481 17.5113 3.20198 15.6664 1.86369 13.2575C1.75634 13.0642 1.7 12.8468 1.7 12.6258V5.75625C1.7 4.59718 2.45326 3.5726 3.55957 3.22688L8.05957 1.82063Z" fill="currentColor"/>
            </svg>`,
            // 右箭头（官方 bot-action）
            chevron: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none"
                           stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                           stroke-linejoin="round" width="100%" height="100%">
                <path d="M6 3l5 5-5 5"/>
            </svg>`,
            // 钥匙形状太重，appId 用更轻的井号标签
            hash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                        stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%">
                <path d="M4 9h16M4 15h16M10 3L8 21M16 3l-2 18"/>
            </svg>`,
            // 指令项：斜杠（command）
            slash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"
                         stroke-linecap="round" width="100%" height="100%">
                <path d="M15 4L9 20"/>
            </svg>`,
            // 指令项：链接（link）
            link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                        stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%">
                <path d="M10 13a5 5 0 0 0 7.07 0l2-2a5 5 0 0 0-7.07-7.07l-1 1"/>
                <path d="M14 11a5 5 0 0 0-7.07 0l-2 2a5 5 0 0 0 7.07 7.07l1-1"/>
            </svg>`,
            // 返回：左箭头
            back: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"
                        stroke-linecap="round" stroke-linejoin="round"
                        style="width:13px;height:13px;display:block">
                <path d="M10 3L5 8l5 5"/>
            </svg>`,
            // 备注：便签
            note: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                        stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%">
                <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v9L14.5 21H6.5A2.5 2.5 0 0 1 4 18.5z"/>
                <path d="M20 14.5h-4a1.5 1.5 0 0 0-1.5 1.5V21"/>
                <path d="M8 8.5h8M8 12h5"/>
            </svg>`
        },
        panels: [],
        // 各场景面板数：独立缓存，避免切换时沿用上一场景的数字
        scopeCounts: { c2c: 0, group: 0, channel: 0, dm: 0 },
        countsReady: false,
        loading: false,
        saving: false,
        showCreateModal: false,
        viewingPanel: null,
        editingPanel: null,
        // 拖拽状态：dragEnabled 仅在按下拖拽手柄后置位，
        // 否则整行 draggable 会吞掉输入框里的文本选择
        dragEnabled: false,
        dragIndex: null,
        dragOverIndex: null,
        uidSeq: 0,
        editForm: {
            remark: '',
            items: []
        },
        newPanel: {
            remark: '',
            items: []
        },

        async init() {
            await this.loadBots();
        },

        // ---- 统一请求封装：附加可选令牌（MAESTRO_TOKEN），401 时引导输入 ----

        // 令牌优先从地址栏 ?token=... 取（书签/转发友好），存 sessionStorage
        // 后立即从地址栏抹掉，避免留在历史记录里
        authToken() {
            const url = new URL(location.href);
            const q = url.searchParams.get('token');
            if (q) {
                sessionStorage.setItem('maestro_token', q);
                url.searchParams.delete('token');
                history.replaceState(null, '', url);
            }
            return sessionStorage.getItem('maestro_token');
        },

        async apiFetch(url, options = {}) {
            options.headers = { ...(options.headers || {}) };
            const token = this.authToken();
            if (token) options.headers['X-Maestro-Token'] = token;
            const resp = await fetch(url, options);
            // 401 = 令牌缺失/错误：引导输入后重试一次（只一次，避免循环弹窗）
            if (resp.status === 401 && !options._retriedAuth) {
                const input = prompt('该 WebUI 已启用令牌鉴权（MAESTRO_TOKEN），请输入访问令牌：');
                if (input !== null) {
                    sessionStorage.setItem('maestro_token', input.trim());
                    return this.apiFetch(url, { ...options, _retriedAuth: true });
                }
            }
            return resp;
        },

        async loadBots() {
            this.botsLoading = true;
            try {
                const resp = await this.apiFetch('/api/bots');
                if (!resp.ok) throw new Error(await this.errorMessage(resp));
                const data = await resp.json();
                this.bots = data.bots || [];
            } catch (error) {
                alert('加载机器人列表失败: ' + error.message);
            } finally {
                this.botsLoading = false;
            }
        },

        async openBot(bot) {
            this.activeBot = bot;
            this.scope = 'group';
            this.countsReady = false;
            this.scopeCounts = { c2c: 0, group: 0, channel: 0, dm: 0 };
            // 并发拉四个场景：既填好各自计数，也顺带拿到当前场景的列表
            await this.loadAllScopes();
        },

        // 一次性拉全部场景，计数与当前列表同源，避免两者不一致
        async loadAllScopes() {
            if (!this.activeBot) return;
            this.loading = true;
            try {
                const results = await Promise.all(
                    this.scopes.map(s => this.fetchScope(s.value))
                );
                const counts = {};
                results.forEach((records, i) => {
                    counts[this.scopes[i].value] = records.length;
                });
                this.scopeCounts = counts;
                this.countsReady = true;
                const idx = this.scopes.findIndex(s => s.value === this.scope);
                this.panels = results[idx] || [];
            } catch (error) {
                alert('加载失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        // 取单个场景的面板列表；失败按空列表处理，不阻断其它场景
        async fetchScope(scope) {
            try {
                const resp = await this.apiFetch(
                    `/api/bots/${this.activeBot.bot_id}/panels?scope=${scope}&limit=50`
                );
                if (!resp.ok) return [];
                const data = await resp.json();
                return data.records || [];
            } catch {
                return [];
            }
        },

        // 切换场景：重新拉该场景列表（面板可能在别处被改动），
        // 计数由 loadPanels 内同步，切换过程中标签数字不会串场景
        async switchScope(value) {
            if (this.scope === value) return;
            this.scope = value;
            await this.loadPanels();
        },

        backToBots() {
            this.activeBot = null;
            this.panels = [];
            this.countsReady = false;
        },

        // channel / dm 仅支持全局配置，不能挂指定对象
        scopeHint() {
            return ['channel', 'dm'].includes(this.scope)
                ? '该场景仅支持全局配置（target_type=all），不能指定用户或群'
                : '该场景支持全局或指定对象';
        },

        // QQ 服务端按显示宽度统计 name/desc（非 ASCII 计 2），
        // 而 maxlength 按 UTF-16 码元算，会漏放超长的中文串。
        width(text) {
            let w = 0;
            for (const ch of (text || '')) {
                w += ch.codePointAt(0) < 128 ? 1 : 2;
            }
            return w;
        },

        // 返回第一条校验错误信息，无错则返回 null
        validateItems(items) {
            if (items.length === 0) return '请至少添加一个指令项';
            for (const [i, item] of items.entries()) {
                const at = `第 ${i + 1} 项`;
                if (!item.name) return `${at}缺少名称`;
                if (!item.desc) return `${at}缺少描述`;
                if (this.width(item.name) > 14) {
                    return `${at}「${item.name}」名称宽度 ${this.width(item.name)} 超过 14（中文计 2）`;
                }
                if (this.width(item.desc) > 30) {
                    return `${at}「${item.name}」描述宽度 ${this.width(item.desc)} 超过 30（中文计 2）`;
                }
                if (item.type === 'link' && !(item.link || '').startsWith('https://')) {
                    return `${at}「${item.name}」为链接类型，地址必须以 https:// 开头`;
                }
            }
            return null;
        },

        async loadPanels() {
            if (!this.activeBot) return;
            this.loading = true;
            try {
                const resp = await this.apiFetch(
                    `/api/bots/${this.activeBot.bot_id}/panels?scope=${this.scope}&limit=50`
                );
                if (!resp.ok) throw new Error(await this.errorMessage(resp));
                const data = await resp.json();
                this.panels = data.records || [];
                // 同步当前场景计数，保证增删后标签数字与列表一致
                this.scopeCounts[this.scope] = this.panels.length;
            } catch (error) {
                alert('加载失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        addPanelItem() {
            if (this.newPanel.items.length >= 20) return;
            this.newPanel.items.push({
                name: '',
                desc: '',
                type: 'command',
                only_admin: false,
                link: null,
                _uid: ++this.uidSeq
            });
        },

        async createPanel() {
            const err = this.validateItems(this.newPanel.items);
            if (err) {
                alert(err);
                return;
            }
            try {
                const resp = await this.apiFetch(`/api/bots/${this.activeBot.bot_id}/panels`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scope: this.scope,
                        panel: {
                            // 剔除前端内部的 _uid
                            items: this.newPanel.items.map(i => ({
                                name: i.name,
                                desc: i.desc,
                                type: i.type,
                                only_admin: i.only_admin,
                                link: i.type === 'link' ? i.link : null
                            })),
                            remark: this.newPanel.remark
                        },
                        target_type: 'all'
                    })
                });
                if (!resp.ok) throw new Error(await this.errorMessage(resp));
                this.showCreateModal = false;
                this.newPanel = { remark: '', items: [] };
                await this.loadPanels();
            } catch (error) {
                alert('创建失败: ' + error.message);
            }
        },

        viewPanel(panel) {
            this.viewingPanel = panel;
        },

        startEdit(panel) {
            // 深拷贝，避免编辑中直接改动列表里的对象——取消时应保持原样
            this.editingPanel = panel;
            this.editForm = {
                remark: panel.panel.remark || '',
                items: JSON.parse(JSON.stringify(panel.panel.items || []))
                    .map(i => ({ ...i, _uid: ++this.uidSeq }))
            };
        },

        addEditItem() {
            if (this.editForm.items.length >= 20) return;
            this.editForm.items.push({
                name: '',
                desc: '',
                type: 'command',
                only_admin: false,
                link: null,
                _uid: ++this.uidSeq
            });
        },

        moveItem(index, delta) {
            const target = index + delta;
            if (target < 0 || target >= this.editForm.items.length) return;
            const items = this.editForm.items;
            [items[index], items[target]] = [items[target], items[index]];
        },

        // ---- 拖拽排序（编辑与新建模态框共用）----
        // which: 'edit' 操作 editForm.items，'new' 操作 newPanel.items
        dragList(which) {
            return which === 'new' ? this.newPanel.items : this.editForm.items;
        },

        onDragStart(index, event, which = 'edit') {
            if (!this.dragEnabled) {
                // 没按手柄就不允许拖，避免干扰输入框内的文本选择
                event.preventDefault();
                return;
            }
            this.dragIndex = index;
            event.dataTransfer.effectAllowed = 'move';
            // Firefox 需要 setData 才会真正启动拖拽
            event.dataTransfer.setData('text/plain', String(index));
        },

        onDragOver(index) {
            if (this.dragIndex === null) return;
            this.dragOverIndex = index;
        },

        onDrop(index, which = 'edit') {
            if (this.dragIndex === null || this.dragIndex === index) {
                this.resetDrag();
                return;
            }
            const items = this.dragList(which);
            const [moved] = items.splice(this.dragIndex, 1);
            items.splice(index, 0, moved);
            this.resetDrag();
        },

        resetDrag() {
            this.dragEnabled = false;
            this.dragIndex = null;
            this.dragOverIndex = null;
        },

        async saveEdit() {
            const err = this.validateItems(this.editForm.items);
            if (err) {
                alert(err);
                return;
            }
            this.saving = true;
            try {
                const url = `/api/bots/${this.activeBot.bot_id}/panels/${this.editingPanel.panel_id}`;
                const resp = await this.apiFetch(url, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        items: this.editForm.items.map(i => ({
                            name: i.name,
                            desc: i.desc,
                            type: i.type,
                            only_admin: i.only_admin,
                            // 剔除前端内部的 _uid，并清掉非 link 类型的残留地址
                            link: i.type === 'link' ? i.link : null
                        })),
                        remark: this.editForm.remark
                    })
                });
                if (!resp.ok) throw new Error(await this.errorMessage(resp));
                this.editingPanel = null;
                await this.loadPanels();
            } catch (error) {
                alert('保存失败: ' + error.message);
            } finally {
                this.saving = false;
            }
        },

        async errorMessage(resp) {
            // 后端把 QQ 侧业务错误转成 {detail, code, trace_id}
            try {
                const data = await resp.json();
                if (typeof data.detail === 'string') return data.detail;
                if (Array.isArray(data.detail)) {
                    return data.detail
                        .map(d => (d.msg || '').replace(/^Value error, /, ''))
                        .join('; ');
                }
                return JSON.stringify(data);
            } catch {
                return `HTTP ${resp.status}`;
            }
        },

        async confirmDelete(panelId) {
            if (!confirm(`确定要删除面板 ${panelId}？此操作不可逆。`)) return;
            try {
                const resp = await this.apiFetch(
                    `/api/bots/${this.activeBot.bot_id}/panels/${panelId}`,
                    { method: 'DELETE' }
                );
                if (!resp.ok) throw new Error(await this.errorMessage(resp));
                await this.loadPanels();
            } catch (error) {
                alert('删除失败: ' + error.message);
            }
        }
    };
}
