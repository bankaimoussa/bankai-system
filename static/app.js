const App = (function () {
    "use strict";

    let CONFIG = null;        // /api/branches response
    let session = null;       // { branch, supervisor_id, supervisor_name, shift_id, day }
    let repsCache = [];       // آخر نتيجة من /api/reps
    let shiftClosed = false;
    let activeType = 'full';  // 'full' | 'part' -- التاب النشط

    const avatarColors = ['#2563eb', '#06b6d4', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];

    // ============================================================
    // Init
    // ============================================================
    async function init() {
        createParticles();
        setupRippleEffect();
        bindStaticEvents();
        initTheme();

        const today = new Date();
        document.getElementById('daySelect').value = today.toISOString().split('T')[0];

        CONFIG = await fetchJSON('/api/branches');
        populateBranches();
    }

    // ============================================================
    // Theme (light/dark)
    // ============================================================
    function initTheme() {
        let saved = null;
        try { saved = localStorage.getItem('bankai_theme'); } catch (e) {}
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = saved || (prefersDark ? 'dark' : 'light');
        applyTheme(theme);
        document.getElementById('themeToggleBtn').addEventListener('click', toggleTheme);
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        try { localStorage.setItem('bankai_theme', theme); } catch (e) {}
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        applyTheme(current === 'dark' ? 'light' : 'dark');
    }

    function populateBranches() {
        const sel = document.getElementById('branchSelect');
        sel.innerHTML = '<option value="">-- اختر الفرع --</option>';
        Object.entries(CONFIG.branches).forEach(([id, b]) => {
            sel.innerHTML += `<option value="${id}">📍 ${b.label}</option>`;
        });

        const shiftSel = document.getElementById('shiftSelect');
        shiftSel.innerHTML = '<option value="">-- اختر الشيفت --</option>';
        CONFIG.supervisor_shifts.forEach(s => {
            shiftSel.innerHTML += `<option value="${s.id}">🕐 ${s.label}</option>`;
        });
    }

    function bindStaticEvents() {
        document.getElementById('branchSelect').addEventListener('change', onBranchChange);
        document.getElementById('supervisorSelect').addEventListener('change', validateLoginForm);
        document.getElementById('shiftSelect').addEventListener('change', validateLoginForm);
        document.getElementById('daySelect').addEventListener('change', validateLoginForm);
        document.getElementById('loginBtn').addEventListener('click', login);

        document.getElementById('searchInput').addEventListener('input', applyFilter);
        document.getElementById('filterSelect').addEventListener('change', applyFilter);
        document.getElementById('exportBtn').addEventListener('click', exportData);
        document.getElementById('saveAllBtn').addEventListener('click', saveAll);
        document.getElementById('closeShiftBtn').addEventListener('click', closeShift);
        document.getElementById('tabFull').addEventListener('click', () => switchTypeTab('full'));
        document.getElementById('tabPart').addEventListener('click', () => switchTypeTab('part'));
        document.getElementById('modalCloseBtn').addEventListener('click', closeModal);
        document.getElementById('modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
        document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
    }

    function onBranchChange() {
        const branch = document.getElementById('branchSelect').value;
        const supSelect = document.getElementById('supervisorSelect');
        supSelect.innerHTML = '<option value="">-- اختر المشرف --</option>';
        if (branch && CONFIG.branches[branch]) {
            supSelect.disabled = false;
            CONFIG.branches[branch].supervisors.forEach(s => {
                supSelect.innerHTML += `<option value="${s.id}">👤 ${s.name} (${s.id})</option>`;
            });
        } else {
            supSelect.disabled = true;
        }
        validateLoginForm();
    }

    function validateLoginForm() {
        const branch = document.getElementById('branchSelect').value;
        const sup = document.getElementById('supervisorSelect').value;
        const shift = document.getElementById('shiftSelect').value;
        const day = document.getElementById('daySelect').value;
        document.getElementById('loginBtn').disabled = !(branch && sup && shift && day);
    }

    // ============================================================
    // Login / Logout
    // ============================================================
    async function login() {
        const branch = document.getElementById('branchSelect').value;
        const supId = document.getElementById('supervisorSelect').value;
        const shiftId = document.getElementById('shiftSelect').value;
        const day = document.getElementById('daySelect').value;

        if (!branch || !supId || !shiftId || !day) {
            showToast('خطأ', 'يرجى استكمال كل الحقول', 'error');
            return;
        }

        const sup = CONFIG.branches[branch].supervisors.find(s => s.id === supId);
        const shift = CONFIG.supervisor_shifts.find(s => s.id === shiftId);

        session = {
            branch, supervisor_id: supId, supervisor_name: sup.name,
            shift_id: shiftId, shift_label: shift.label, day,
        };

        document.getElementById('userName').textContent = sup.name;
        document.getElementById('userAvatar').textContent = sup.name.charAt(0);

        const loginScreen = document.getElementById('loginScreen');
        const mainApp = document.getElementById('mainApp');

        loginScreen.style.transition = 'opacity 0.5s, transform 0.5s';
        loginScreen.style.opacity = '0';
        loginScreen.style.transform = 'scale(0.95)';

        setTimeout(async () => {
            loginScreen.style.display = 'none';
            mainApp.classList.add('active', 'entering');
            setTimeout(() => mainApp.classList.remove('entering'), 800);

            updateDate();
            renderShiftBanner();
            await loadReps();

            setTimeout(() => showToast('مرحباً!', `أهلاً بك ${sup.name} - ${CONFIG.branches[branch].label}`), 400);
        }, 500);
    }

    function logout() {
        const mainApp = document.getElementById('mainApp');
        const loginScreen = document.getElementById('loginScreen');

        mainApp.style.transition = 'opacity 0.4s, transform 0.4s';
        mainApp.style.opacity = '0';
        mainApp.style.transform = 'scale(0.98)';

        setTimeout(() => {
            mainApp.classList.remove('active');
            mainApp.style.opacity = '';
            mainApp.style.transform = '';

            loginScreen.style.display = 'flex';
            loginScreen.style.opacity = '0';
            loginScreen.style.transform = 'scale(1.05)';
            setTimeout(() => {
                loginScreen.style.transition = 'opacity 0.5s, transform 0.5s';
                loginScreen.style.opacity = '1';
                loginScreen.style.transform = 'scale(1)';
            }, 50);

            document.getElementById('branchSelect').value = '';
            document.getElementById('supervisorSelect').innerHTML = '<option value="">-- اختر الفرع أولاً --</option>';
            document.getElementById('supervisorSelect').disabled = true;
            document.getElementById('shiftSelect').value = '';
            document.getElementById('loginBtn').disabled = true;
            session = null;
        }, 400);
    }

    function renderShiftBanner() {
        const banner = document.getElementById('currentShiftBanner');
        const dateStr = new Date(session.day + 'T00:00:00').toLocaleDateString('ar-EG', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        banner.innerHTML = `
            <span>🕐 شيفتك: ${session.shift_label} &nbsp;|&nbsp; 📅 ${dateStr}</span>
            ${shiftClosed ? '<span class="badge-closed">🔒 الشيفت مقفول</span>' : ''}
        `;
    }

    // ============================================================
    // Load reps for current session
    // ============================================================
    async function loadReps() {
        const qs = new URLSearchParams({
            branch: session.branch,
            supervisor_id: session.supervisor_id,
            shift_id: session.shift_id,
            day: session.day,
        });
        const data = await fetchJSON('/api/reps?' + qs.toString());
        repsCache = data.reps;
        shiftClosed = data.shift_closed;
        renderShiftBanner();
        renderTable();
        updateStats();
        updateCloseButtonState();
    }

    function updateCloseButtonState() {
        const btn = document.getElementById('closeShiftBtn');
        btn.disabled = shiftClosed;
        btn.innerHTML = shiftClosed
            ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> الشيفت مقفول'
            : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> إنهاء الشيفت';
        document.getElementById('saveAllBtn').disabled = shiftClosed;
    }

    // ============================================================
    // Render table
    // ============================================================
    function renderTable() {
        const table = document.getElementById('repsTable');
        const emptyState = document.getElementById('emptyState');

        updateTypeTabCounts();

        const filtered = repsCache.filter(r => r.type === activeType);

        if (filtered.length === 0) {
            table.innerHTML = '';
            emptyState.style.display = 'block';
            emptyState.textContent = repsCache.length === 0
                ? 'لا يوجد مندوبين متقاطعين مع هذا الشيفت في هذا اليوم'
                : `لا يوجد مندوبين ${activeType === 'full' ? 'دوام كامل' : 'دوام جزئي'} في هذا الشيفت`;
            return;
        }
        emptyState.style.display = 'none';

        table.innerHTML = `
            <thead>
                <tr>
                    <th style="width: 30px;"></th>
                    <th>المندوب</th>
                    <th>الحضور</th>
                    <th class="center">الأوردرات</th>
                    <th class="center">MISS</th>
                    <th>الأداء</th>
                    <th style="width: 100px; text-align: left;">إجراءات</th>
                </tr>
            </thead>
            <tbody>
                ${filtered.map((rep, i) => renderRow(rep, i)).join('')}
            </tbody>
        `;
    }

    function updateTypeTabCounts() {
        const fullCount = repsCache.filter(r => r.type === 'full').length;
        const partCount = repsCache.filter(r => r.type === 'part').length;
        document.getElementById('countFull').textContent = fullCount;
        document.getElementById('countPart').textContent = partCount;
    }

    function switchTypeTab(type) {
        if (type === activeType) return;
        activeType = type;
        document.getElementById('tabFull').classList.toggle('active', type === 'full');
        document.getElementById('tabPart').classList.toggle('active', type === 'part');
        renderTable();
    }

    function fmtHour(h) {
        const hh = Math.floor(h) % 24;
        const period = hh >= 12 ? 'م' : 'ص';
        const h12 = hh % 12 === 0 ? 12 : hh % 12;
        return `${h12}:00 ${period}`;
    }

    function renderRow(rep, idx) {
        const initials = rep.name.split(' ').slice(0, 2).map(w => w[0]).join('');
        const color = avatarColors[idx % avatarColors.length];
        const orders = rep.orders || 0;
        const miss = rep.miss || 0;
        const maxOrders = 60;
        const perfPct = Math.min((orders / maxOrders) * 100, 100);
        const perfClass = miss > 3 ? 'danger' : miss > 1 ? 'warn' : '';
        const isSaved = rep.saved;
        const disabled = shiftClosed;

        return `
            <tr data-name="${escapeAttr(rep.name)}" data-att="${rep.attendance || 'pending'}" class="${isSaved ? 'saved' : ''}">
                <td><span class="status-dot ${isSaved ? 'saved' : 'pending'}" title="${isSaved ? 'محفوظ' : 'غير محفوظ'}"></span></td>
                <td>
                    <div class="rep-cell">
                        <div class="rep-avatar" style="background: linear-gradient(135deg, ${color}, ${color}cc);">${initials}</div>
                        <div class="rep-info-main">
                            <div class="rep-name">${rep.name}</div>
                            <div class="rep-meta-row">
                                <span class="type-badge ${rep.type === 'full' ? 'full' : 'part'}">${rep.type === 'full' ? 'دوام كامل' : 'دوام جزئي'}</span>
                                <span class="rep-shift-row">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                                    ${fmtHour(rep.start)} - ${fmtHour(rep.end_hour)}
                                </span>
                            </div>
                        </div>
                    </div>
                </td>
                <td>
                    <div class="attendance-group">
                        <button class="att-chip ${rep.attendance === 'present' ? 'present' : ''}" ${disabled ? 'disabled' : ''} onclick="App.setAtt('${escapeJs(rep.name)}','present')">✓ حضر</button>
                        <button class="att-chip ${rep.attendance === 'late' ? 'late' : ''}" ${disabled ? 'disabled' : ''} onclick="App.setAtt('${escapeJs(rep.name)}','late')">⏰ تأخير</button>
                        <button class="att-chip ${rep.attendance === 'absent' ? 'absent' : ''}" ${disabled ? 'disabled' : ''} onclick="App.setAtt('${escapeJs(rep.name)}','absent')">✗ غياب</button>
                    </div>
                    ${(rep.attendance === 'late' || rep.attendance === 'absent') ? `
                        <div class="reason-badge-select">
                            <button class="reason-mini-btn ${rep.reason === 'with' ? 'active' : ''}" ${disabled ? 'disabled' : ''} onclick="App.setReason('${escapeJs(rep.name)}','with')">بسبب</button>
                            <button class="reason-mini-btn ${rep.reason === 'without' ? 'active' : ''}" ${disabled ? 'disabled' : ''} onclick="App.setReason('${escapeJs(rep.name)}','without')">بدون سبب</button>
                        </div>
                    ` : ''}
                    ${rep.reason ? `<div class="reason-badge ${rep.reason}">${rep.reason === 'with' ? '📋 بسبب' : '⚠ بدون سبب'}</div>` : ''}
                </td>
                <td class="center">
                    <div class="stepper">
                        <button class="stepper-btn" ${disabled ? 'disabled' : ''} onclick="App.stepNum('${escapeJs(rep.name)}','orders',-1)">−</button>
                        <input type="number" class="stepper-input" value="${orders}" min="0" ${disabled ? 'disabled' : ''} onchange="App.setNum('${escapeJs(rep.name)}','orders',this.value)">
                        <button class="stepper-btn" ${disabled ? 'disabled' : ''} onclick="App.stepNum('${escapeJs(rep.name)}','orders',1)">+</button>
                    </div>
                </td>
                <td class="center">
                    <div class="stepper miss">
                        <button class="stepper-btn" ${disabled ? 'disabled' : ''} onclick="App.stepNum('${escapeJs(rep.name)}','miss',-1)">−</button>
                        <input type="number" class="stepper-input" value="${miss}" min="0" ${disabled ? 'disabled' : ''} onchange="App.setNum('${escapeJs(rep.name)}','miss',this.value)">
                        <button class="stepper-btn" ${disabled ? 'disabled' : ''} onclick="App.stepNum('${escapeJs(rep.name)}','miss',1)">+</button>
                    </div>
                </td>
                <td>
                    <div class="progress-wrap">
                        <div class="progress-bar"><div class="progress-fill ${perfClass}" style="width: ${perfPct}%"></div></div>
                        <div class="progress-text"><span>${orders} أوردر</span><span>${miss} miss</span></div>
                    </div>
                </td>
                <td>
                    <div class="row-actions">
                        <button class="icon-btn save-btn ${isSaved ? 'saved' : ''}" ${disabled ? 'disabled' : ''} onclick="App.saveOne('${escapeJs(rep.name)}')" title="حفظ">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                        </button>
                        <button class="icon-btn" ${disabled ? 'disabled' : ''} onclick="App.resetRow('${escapeJs(rep.name)}')" title="إعادة تعيين">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    function findRep(name) { return repsCache.find(r => r.name === name); }

    // ============================================================
    // Mutations (optimistic local update + API save)
    // ============================================================
    async function setAtt(name, type) {
        if (shiftClosed) return;
        const rep = findRep(name);
        rep.attendance = type;
        rep.reason = null;
        rep.saved = false;
        renderTable();
        updateStats();
        await persist(rep, { attendance: type, reason: null, saved: false });
    }

    async function setReason(name, reason) {
        if (shiftClosed) return;
        const rep = findRep(name);
        rep.reason = reason;
        rep.saved = false;
        renderTable();
        await persist(rep, { reason, saved: false });
    }

    async function stepNum(name, field, delta) {
        if (shiftClosed) return;
        const rep = findRep(name);
        rep[field] = Math.max(0, (rep[field] || 0) + delta);
        rep.saved = false;
        renderTable();
        updateStats();
        await persist(rep, { [field]: rep[field], saved: false });
    }

    async function setNum(name, field, val) {
        if (shiftClosed) return;
        const rep = findRep(name);
        rep[field] = Math.max(0, parseInt(val) || 0);
        rep.saved = false;
        renderTable();
        updateStats();
        await persist(rep, { [field]: rep[field], saved: false });
    }

    async function resetRow(name) {
        if (shiftClosed) return;
        if (!confirm('هل تريد إعادة تعيين بيانات هذا المندوب؟')) return;
        const rep = findRep(name);
        await fetchJSON('/api/reset', {
            method: 'POST',
            body: {
                day: session.day, branch: session.branch,
                supervisor_id: session.supervisor_id, supervisor_shift_id: session.shift_id,
                rep_name: name,
            },
        });
        rep.attendance = null; rep.reason = null; rep.orders = 0; rep.miss = 0; rep.saved = false;
        renderTable();
        updateStats();
        showToast('تم', 'تم إعادة تعيين البيانات');
    }

    async function saveOne(name) {
        if (shiftClosed) return;
        const rep = findRep(name);
        if (!rep.attendance) { showToast('تنبيه', 'يرجى تحديد حالة الحضور أولاً', 'error'); return; }
        if ((rep.attendance === 'late' || rep.attendance === 'absent') && !rep.reason) {
            showToast('تنبيه', 'يرجى تحديد السبب', 'error'); return;
        }
        rep.saved = true;
        await persist(rep, { saved: true });
        renderTable();
        showToast('تم الحفظ ✓', `تم حفظ تقييم ${rep.name}`);
        setTimeout(() => {
            const row = document.querySelector(`tr[data-name="${cssEscape(rep.name)}"]`);
            if (row) { row.classList.add('just-saved'); setTimeout(() => row.classList.remove('just-saved'), 1000); }
        }, 50);
    }

    async function saveAll() {
        if (shiftClosed) return;
        let count = 0, errors = 0;
        for (const rep of repsCache) {
            if (rep.attendance) {
                if ((rep.attendance === 'late' || rep.attendance === 'absent') && !rep.reason) {
                    errors++;
                } else {
                    rep.saved = true;
                    await persist(rep, { saved: true });
                    count++;
                }
            }
        }
        renderTable();
        updateStats();
        if (count === 0 && errors === 0) { showToast('تنبيه', 'لا توجد تقييمات للحفظ', 'error'); return; }
        if (errors > 0) showToast('تنبيه', `هناك ${errors} مندوب يحتاج لتحديد السبب`, 'error');
        if (count > 0) {
            showModal('تم الحفظ بنجاح!', `تم حفظ ${count} تقييم للمندوبين`);
            launchConfetti();
        }
    }

    async function persist(rep, extra) {
        await fetchJSON('/api/evaluate', {
            method: 'POST',
            body: {
                branch: session.branch,
                supervisor_id: session.supervisor_id,
                supervisor_name: session.supervisor_name,
                supervisor_shift_id: session.shift_id,
                day: session.day,
                rep_name: rep.name,
                rep_type: rep.type,
                rep_start: rep.start,
                attendance: rep.attendance,
                reason: rep.reason,
                orders: rep.orders,
                miss: rep.miss,
                ...extra,
            },
        });
    }

    // ============================================================
    // Close shift
    // ============================================================
    async function closeShift() {
        if (shiftClosed) return;
        if (!confirm('هل أنت متأكد من إنهاء الشيفت؟ لن تتمكن من تعديل التقييمات بعد ذلك.')) return;

        await fetchJSON('/api/close_shift', {
            method: 'POST',
            body: {
                branch: session.branch,
                supervisor_id: session.supervisor_id,
                supervisor_name: session.supervisor_name,
                supervisor_shift_id: session.shift_id,
                day: session.day,
            },
        });

        shiftClosed = true;
        renderShiftBanner();
        renderTable();
        updateCloseButtonState();
        showModal('تم إنهاء الشيفت!', 'سيتم الآن تحميل ملف تقرير الشيفت');
        launchConfetti();
        exportData();
    }

    function exportData() {
        const qs = new URLSearchParams({
            branch: session.branch,
            supervisor_id: session.supervisor_id,
            shift_id: session.shift_id,
            day: session.day,
        });
        window.location.href = '/api/export_csv?' + qs.toString();
    }

    // ============================================================
    // Stats + filtering
    // ============================================================
    function updateStats() {
        let present = 0, late = 0, absent = 0;
        repsCache.forEach(rep => {
            if (rep.attendance === 'present') present++;
            else if (rep.attendance === 'late') late++;
            else if (rep.attendance === 'absent') absent++;
        });
        animateNum('statTotal', repsCache.length);
        animateNum('statPresent', present);
        animateNum('statLate', late);
        animateNum('statAbsent', absent);
    }

    function animateNum(id, target) {
        const el = document.getElementById(id);
        const cur = parseInt(el.textContent) || 0;
        if (cur === target) return;
        el.classList.add('bump');
        setTimeout(() => el.classList.remove('bump'), 500);
        const dur = 400, steps = 20, inc = (target - cur) / steps;
        let step = 0;
        const t = setInterval(() => {
            step++;
            el.textContent = Math.round(cur + inc * step);
            if (step >= steps) { el.textContent = target; clearInterval(t); }
        }, dur / steps);
    }

    function applyFilter() {
        const q = document.getElementById('searchInput').value.toLowerCase();
        const f = document.getElementById('filterSelect').value;
        document.querySelectorAll('.reps-table tbody tr').forEach(row => {
            const name = row.dataset.name.toLowerCase();
            const att = row.dataset.att;
            const matchSearch = !q || name.includes(q);
            let matchFilter = true;
            if (f === 'pending') matchFilter = att === 'pending' || !att;
            else if (f !== 'all') matchFilter = att === f;
            const shouldShow = matchSearch && matchFilter;
            if (shouldShow) {
                row.style.display = '';
                row.style.opacity = '1';
                row.style.transform = '';
            } else {
                row.style.opacity = '0';
                row.style.transform = 'scale(0.95)';
                setTimeout(() => { if (row.style.opacity === '0') row.style.display = 'none'; }, 200);
            }
        });
    }

    // ============================================================
    // Utilities
    // ============================================================
    function updateDate() {
        const now = new Date();
        const opts = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        document.getElementById('currentDate').textContent = now.toLocaleDateString('ar-EG', opts);
    }

    async function fetchJSON(url, opts) {
        opts = opts || {};
        const fetchOpts = { method: opts.method || 'GET', headers: {} };
        if (opts.body) {
            fetchOpts.headers['Content-Type'] = 'application/json';
            fetchOpts.body = JSON.stringify(opts.body);
        }
        const res = await fetch(url, fetchOpts);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ error: 'unknown_error' }));
            showToast('خطأ', err.error === 'shift_closed' ? 'الشيفت مقفول بالفعل' : 'حدث خطأ في الاتصال', 'error');
            throw new Error(err.error || 'request_failed');
        }
        return res.json();
    }

    function escapeAttr(s) { return String(s).replace(/"/g, '&quot;'); }
    function escapeJs(s) { return String(s).replace(/'/g, "\\'"); }
    function cssEscape(s) { return String(s).replace(/"/g, '\\"'); }

    function showToast(title, msg, type) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type === 'error' ? 'error' : ''}`;
        toast.innerHTML = `
            <div class="toast-icon">
                ${type === 'error'
                    ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
                    : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>'}
            </div>
            <div class="toast-content"><div class="toast-title">${title}</div><div class="toast-msg">${msg}</div></div>
        `;
        container.appendChild(toast);
        setTimeout(() => { toast.classList.add('removing'); setTimeout(() => toast.remove(), 400); }, 3000);
    }

    function showModal(title, desc) {
        document.getElementById('modalTitle').textContent = title;
        document.getElementById('modalDesc').textContent = desc;
        document.getElementById('modal').classList.add('show');
    }
    function closeModal() { document.getElementById('modal').classList.remove('show'); }

    function createParticles() {
        const container = document.getElementById('particles');
        for (let i = 0; i < 30; i++) {
            const p = document.createElement('div');
            p.className = 'particle';
            p.style.left = Math.random() * 100 + '%';
            p.style.animationDuration = (15 + Math.random() * 20) + 's';
            p.style.animationDelay = Math.random() * 20 + 's';
            p.style.opacity = 0.3 + Math.random() * 0.5;
            const size = 2 + Math.random() * 4;
            p.style.width = size + 'px';
            p.style.height = size + 'px';
            container.appendChild(p);
        }
    }

    function setupRippleEffect() {
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('.action-btn, .login-btn, .att-chip, .reason-mini-btn');
            if (!btn) return;
            const rect = btn.getBoundingClientRect();
            const ripple = document.createElement('span');
            ripple.className = 'ripple';
            const size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
            ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
            if (btn.classList.contains('btn-secondary')) ripple.style.background = 'rgba(37, 99, 235, 0.2)';
            btn.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    }

    function launchConfetti() {
        const container = document.getElementById('confettiContainer');
        const colors = ['#2563eb', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#a855f7', '#ec4899'];
        for (let i = 0; i < 50; i++) {
            const c = document.createElement('div');
            c.className = 'confetti';
            c.style.left = Math.random() * 100 + '%';
            c.style.background = colors[Math.floor(Math.random() * colors.length)];
            c.style.animationDelay = Math.random() * 0.5 + 's';
            c.style.animationDuration = (2 + Math.random() * 2) + 's';
            if (Math.random() > 0.5) c.style.borderRadius = '50%';
            container.appendChild(c);
            setTimeout(() => c.remove(), 4000);
        }
    }

    return {
        init, logout, setAtt, setReason, stepNum, setNum, resetRow, saveOne,
    };
})();

document.addEventListener('DOMContentLoaded', App.init);
