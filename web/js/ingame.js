// The page's mode «Как в игре»: only the ship's screen, at the size the game gives it on a chosen screen, to judge what is large, what is small and
// what fits. The game's screen is a frame of that screen's proportions on a dark ground; the panel in it is the same panel as in «Игра» (one game,
// one save), built on the root the game would have there.
//
// How the game sizes its interface (what is known, docs and files of this project):
//   - the panel: src/tww3_mtb_crew_ui.lua (build) and web/js/panel.js: min(W - 40, 1560) x min(H - 30, 870) units of the root W x H, docked at the
//     root's centre (SetDockingPoint(5)), over a backdrop of the whole root at opacity 150;
//   - the root: 1600 x 900 at a 1280 x 720 window (measured in the game, docs/design/progression-proposal.md, «2560×1440 с UI 1,6»);
//   - the setting ui_scale of the game's preferences.script.txt: «Scale of UI, 1 is default size. Can range between 0.5-2 ... but can only scale up
//     if running 1440p or larger res». The author's file has x_res 2560, y_res 1440, ui_scale 1.6.
// The rule taken here (a deduction from those three, not read from the game's code): the interface's pixel is s pixels of the screen,
//   s = min(ui_scale, 1 below 1440 lines of the screen, W / 1600, H / 900), the root = screen / s.
// So 1280 x 720 gives 0.8 and 1600 x 900 (measured); 1920 x 1080 gives 1 at any ui_scale; 2560 x 1440 at 1.6 gives 1600 x 900 (deduced in that doc).
//
// The frame's pixels: «1:1» puts one pixel of the game's screen on one pixel of the monitor (devicePixelRatio: the scale of Windows and of the
// browser's zoom); «Вписать» shows the whole screen smaller, never larger than 1:1, and says by how much.

const RES = [['mine', 'мой экран'], ['1920x1080', '1920×1080'], ['2560x1440', '2560×1440'], ['3840x2160', '3840×2160']];
const UI = [0.75, 1, 1.25, 1.5, 1.6, 1.75, 2];
const LAYOUTS = {A: 'A · как сейчас', B: 'B · дерево на месте чертежа', C: 'C · чертёж меньше, дерево шире'};
const NODE = 74, CARD_W = 23, CARD_H = 50, INFO_TEXT = 16;      // web/js/panel.js: the slot, the small unit card; the building window's body (16 units)
const KEY = 'mtb_ig';
const num = (x, d = 0) => x.toLocaleString('ru-RU', {maximumFractionDigits: d, minimumFractionDigits: 0});
const $ = id => document.getElementById(id);

// the interface's scale of the game and its root on a screen of w x h at the setting u (see above)
export function uiScale(w, h, u) {
    let s = Math.max(0.5, Math.min(2, u));
    if (h < 1440) s = Math.min(s, 1);
    return Math.min(s, w / 1600, h / 900);
}
export function rootSize(w, h, u) { const s = uiScale(w, h, u); return {w: Math.round(w / s), h: Math.round(h / s), s}; }
// this monitor in its own pixels: the CSS size of the screen times the device pixel ratio (Windows' scale; a browser zoom other than 100 % skews it)
export function myScreen() { const d = window.devicePixelRatio || 1; return {w: Math.round(screen.width * d), h: Math.round(screen.height * d)}; }
const panelUnits = (W, H) => ({w: Math.min(W - 40, 1560), h: Math.min(H - 30, 870)});

export function makeInGame(ctx) {
    const {host, flags} = ctx;
    const st = {res: 'mine', ui: 1.6, show: 'fit', ruler: false, font: true, layout: 'A', report: false};
    try { Object.assign(st, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) { /* no storage */ }
    if (flags.res) st.res = flags.res;
    if (flags.ui) st.ui = Number(flags.ui);
    if (flags.show) st.show = flags.show === '1' || flags.show === 'one' ? 'one' : 'fit';
    if (flags.layout) st.layout = flags.layout;
    if (flags.ruler) st.ruler = flags.ruler === '1';
    if (flags.font) st.font = flags.font !== 'page';
    if (!LAYOUTS[st.layout]) st.layout = 'A';
    const save = () => { try { localStorage.setItem(KEY, JSON.stringify({...st, report: false})); } catch (e) { /* no storage */ } };
    let active = false, plate = false;          // plate: the bar called back by P in the full screen at 1:1
    const fitCache = {};                        // what of the tree the column shows, per layout (the same at every screen whose panel is 1560 x 870)

    const resolution = () => {
        if (st.res === 'mine') return myScreen();
        const [w, h] = st.res.split('x').map(Number);
        return w && h ? {w, h} : myScreen();
    };
    const spec = () => { const r = resolution(), z = rootSize(r.w, r.h, st.ui); return {w: z.w, h: z.h, layout: st.layout}; };

    // ---- the plate's controls ----
    const resSel = $('ig_res'), uiSel = $('ig_ui'), laySel = $('ig_layout');
    const fillRes = () => {
        const m = myScreen();
        resSel.innerHTML = RES.map(([k, t]) => `<option value="${k}">${k === 'mine' ? `${t} ${m.w}×${m.h}` : t}</option>`).join('');
        resSel.value = st.res;
    };
    fillRes();
    uiSel.innerHTML = UI.map(u => `<option value="${u}">${num(u, 2)}${u === 1.6 ? ' (ваша)' : ''}</option>`).join('');
    uiSel.value = String(st.ui);
    laySel.innerHTML = Object.entries(LAYOUTS).map(([k, t]) => `<option value="${k}">${t}</option>`).join('');
    laySel.value = st.layout;
    const changed = () => { save(); paintButtons(); if (active) { ctx.rebuild(); fit(); } };
    resSel.addEventListener('change', () => { st.res = resSel.value; changed(); });
    uiSel.addEventListener('change', () => { st.ui = Number(uiSel.value); changed(); });
    laySel.addEventListener('change', () => { st.layout = laySel.value; changed(); });
    const setShow = s => { st.show = s; changed(); };
    $('ig_fit').addEventListener('click', () => setShow('fit'));
    $('ig_one').addEventListener('click', () => setShow('one'));
    $('ig_full').addEventListener('click', () => fullscreen());
    $('ig_ruler').addEventListener('click', () => { st.ruler = !st.ruler; changed(); });
    $('ig_font').addEventListener('click', () => { st.font = !st.font; changed(); ctx.refresh(); });
    $('ig_report_btn').addEventListener('click', () => { st.report = !st.report; paintButtons(); paintReport(); });
    function paintButtons() {
        $('ig_fit').classList.toggle('on', st.show === 'fit');
        $('ig_one').classList.toggle('on', st.show === 'one');
        $('ig_ruler').classList.toggle('on', st.ruler);
        $('ig_font').classList.toggle('on', st.font);
        $('ig_report_btn').classList.toggle('on', st.report);
        $('ig_full').textContent = document.fullscreenElement ? 'Выйти из полного экрана' : 'Во весь экран';
        document.body.classList.toggle('ig-gamefont', st.font);
    }

    // ---- the full screen ----
    const fullscreen = () => {
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        else document.documentElement.requestFullscreen().catch(() => {});
    };
    const paintPlate = () => {
        const hide = active && !!document.fullscreenElement && st.show === 'one' && !plate;
        document.body.classList.toggle('ig-noplate', hide);
    };
    document.addEventListener('fullscreenchange', () => { plate = false; paintPlate(); paintButtons(); requestAnimationFrame(fit); });

    // keys: 0 fit, 1 one to one, F the full screen, P the plate, L the ruler, R the summary (by the key's place: any keyboard layout)
    document.addEventListener('keydown', e => {
        if (!active || e.ctrlKey || e.altKey || e.metaKey || /^(INPUT|SELECT|TEXTAREA)$/.test((e.target && e.target.tagName) || '')) return;
        const act = {Digit0: () => setShow('fit'), Digit1: () => setShow('one'), KeyF: fullscreen, KeyL: () => { st.ruler = !st.ruler; changed(); },
            KeyP: () => { plate = !plate; paintPlate(); requestAnimationFrame(fit); }, KeyR: () => { st.report = !st.report; paintButtons(); paintReport(); }}[e.code];
        if (act) { e.preventDefault(); act(); }
    });

    // ---- the frame ----
    const stage = $('ig_stage'), frameEl = $('ig_screen'), overlay = $('ig_overlay'), label = $('ig_label');
    let shown = {f: 1, dpr: 1, s: 1, r: {w: 0, h: 0}};
    function fit() {
        const G = ctx.G;
        if (!active || !G || !G.root) return;
        const dpr = window.devicePixelRatio || 1, r = resolution(), z = rootSize(r.w, r.h, st.ui);
        const full = !!document.fullscreenElement, margin = full ? 0 : 12;
        const cssW = r.w / dpr, cssH = r.h / dpr;
        const aw = stage.clientWidth, ah = stage.clientHeight;
        const f = st.show === 'one' ? 1 : Math.max(0.05, Math.min(1, (aw - 2 * margin) / cssW, (ah - 2 * margin) / cssH));
        const fw = cssW * f, fh = cssH * f;
        // on whole pixels of the device: at 1:1 each of the game's pixels is one of the monitor's
        const s0 = stage.getBoundingClientRect();
        const snap = (origin, off) => Math.round((origin + off) * dpr) / dpr - origin;
        const left = fw <= aw ? snap(s0.left, (aw - fw) / 2) : 0, top = fh <= ah ? snap(s0.top, (ah - fh) / 2) : 0;
        Object.assign(frameEl.style, {width: fw + 'px', height: fh + 'px', left: left + 'px', top: top + 'px'});
        const k = fw / G.root.Width();
        G.root.el.style.transform = `scale(${k})`;
        host.style.width = fw + 'px';
        host.style.height = fh + 'px';
        shown = {f, dpr, s: z.s, r, root: z, k};
        const capped = z.s < Math.max(0.5, Math.min(2, st.ui)) - 1e-9;
        label.textContent = `экран игры ${r.w}×${r.h} · UI ${num(st.ui, 2)}${capped ? ` → ${num(z.s, 2)}` : ''} · корень ${z.w}×${z.h} · показано ${num(f * 100, f < 1 ? 0 : 0)} %`
            + (st.show === 'one' && fw > aw + 1 || st.show === 'one' && fh > ah + 1 ? ' · не помещается: прокрутка' : '');
        label.title = (capped ? (r.h < 1440 ? 'Ниже 1440 строк экрана игра не увеличивает интерфейс (ui_scale), он остаётся 1,0 или меньше. ' : 'Интерфейс не может быть меньше 1600×900 единиц: масштаб уменьшен. ') : '')
            + `Один пиксель интерфейса игры = ${num(z.s, 3)} пикселя экрана; на мониторе показано ${num(f * 100, 1)} % (devicePixelRatio ${num(dpr, 3)}).`;
        paintRuler();
        if (st.report) paintReport();
    }
    new ResizeObserver(() => fit()).observe(stage);
    window.addEventListener('resize', () => { fillRes(); if (active && st.res === 'mine') ctx.rebuild(); fit(); });

    // ---- the ruler: the sizes of the screen's parts in the game's pixels, and a grid of 100 of them ----
    const gamePx = cssLen => cssLen * shown.dpr / shown.f;        // a length on the page -> pixels of the game's screen
    function paintRuler() {
        overlay.innerHTML = '';
        overlay.style.display = st.ruler ? '' : 'none';
        const G = ctx.G;
        if (!st.ruler || !G || !G.panel) return;
        const fr = frameEl.getBoundingClientRect(), step = 100 * shown.f / shown.dpr;
        let grid = '';
        for (let i = 1; i * step < fr.width; i++) grid += `<div class="g v${i % 5 ? '' : ' major'}" style="left:${i * step}px">${i % 5 ? '' : `<i>${i * 100}</i>`}</div>`;
        for (let i = 1; i * step < fr.height; i++) grid += `<div class="g h${i % 5 ? '' : ' major'}" style="top:${i * step}px">${i % 5 ? '' : `<i>${i * 100}</i>`}</div>`;
        const s = shown.s, view = G.panel.view;
        const marks = [];
        const mark = (el, text, where = 'top') => {
            if (!el) return;
            const r = el.getBoundingClientRect();
            if (!r.width) return;
            marks.push(`<div class="m ${where}" style="left:${r.left - fr.left}px;top:${r.top - fr.top}px;width:${r.width}px;height:${r.height}px"><b>${text}</b></div>`);
        };
        const px = (u, d = 0) => num(u * s, d);
        const box = c => `${num(Math.round(gamePx(c.getBoundingClientRect().width)))}×${num(Math.round(gamePx(c.getBoundingClientRect().height)))} px`;
        const frame = view.frame;
        mark(frame.el, `панель ${frame.Width()}×${frame.Height()} ед. = ${box(frame.el)}`, 'out');
        const win = view.pan && view.pan.win;
        if (win && win.Visible()) mark(win.el, `окно дерева ${win.Width()}×${win.Height()} ед. = ${box(win.el)}`, 'in');
        // a slot in sight: the selected one, else the first whole in the window
        const wr = win ? win.el.getBoundingClientRect() : null;
        const inWin = el => { const r = el.getBoundingClientRect(); return wr && r.width && r.left >= wr.left && r.right <= wr.right && r.top >= wr.top && r.bottom <= wr.bottom; };
        const slots = (view.tree || []).filter(v => inWin(v.button.el));
        const slot = slots.find(v => v.node.key === view.selected) || slots[0];
        if (slot) mark(slot.button.el, `слот ${NODE} ед. = ${box(slot.button.el)}`, 'side');
        const card = (view.crew || []).find(c => c.v && inWin(c.card.el) && c.v !== slot);
        if (card) mark(card.card.el, `карточка ${CARD_W}×${CARD_H} ед. = ${box(card.card.el)}`, 'side');
        const t = view.selMeta && view.selMeta.Visible() && view.selMeta.textEl;
        if (t) {
            const fs = parseFloat(getComputedStyle(t).fontSize), lh = parseFloat(getComputedStyle(t).lineHeight) || fs * 1.25;
            mark(view.selMeta.el, `текст колонки: кегль ${num(fs, 1)} ед. = ${px(fs, 1)} px, строка ${px(lh, 1)} px`, 'under');
        }
        const sheet = view.sheet;
        if (sheet && (!win || !win.Visible() || view.layout !== 'B')) mark(sheet.el, `чертёж ${sheet.Width()}×${sheet.Height()} ед. = ${box(sheet.el)}`, 'in');
        if (view.column) mark(view.column.el, `колонка ${view.column.Width()} ед. = ${px(view.column.Width())} px`, 'foot');
        // the same numbers whatever is in sight: a legend in the screen's upper left corner
        const fs = t ? parseFloat(getComputedStyle(t).fontSize) : 12;
        const legend = `<div class="legend">1 ед. интерфейса = ${num(s, 3)} px экрана · сетка 100 px<br>слот ${NODE} ед. = ${px(NODE, 1)} px · карточка ${CARD_W}×${CARD_H} ед. = ${px(CARD_W, 1)}×${px(CARD_H, 1)} px<br>`
            + `текст колонки ${num(fs, 1)} ед. = ${px(fs, 1)} px · текст окна сведений ${INFO_TEXT} ед. = ${px(INFO_TEXT, 1)} px</div>`;
        overlay.innerHTML = grid + marks.join('') + legend;
    }
    setInterval(() => { if (active && st.ruler) paintRuler(); }, 400);       // the tree pans, a building is selected

    // ---- what of the tree the column shows, for the summary ----
    function treeFit(view) {
        const p = view.pan;
        if (!p || !view.tree) return null;
        const keep = {x: p.x, y: p.y, z: p.z};
        const count = () => view.tree.filter(v => {
            const x = p.x + v.button.x * p.z, y = p.y + v.button.y * p.z, n = NODE * p.z;
            return x >= 0 && y >= 0 && x + n <= p.w && y + n <= p.h;
        }).length;
        const was = p.hidden;
        p.home();
        const out = {total: view.tree.length, seen: count(), w: Math.round(p.w), h: Math.round(p.h), cw: p.cw, ch: p.ch};
        // «Развернуть дерево» of A: the same at the opened window's size
        if (view.layout === 'A' && p.fitBtn && !p.fits) { p.expand(); out.open = {seen: count(), w: Math.round(p.w), h: Math.round(p.h)}; p.expand(); }
        Object.assign(p, keep); p.clamp();
        if (was) p.hidden = was;
        return out;
    }
    let cacheOf = null;
    function measureLayouts() {
        const G = ctx.G, now = st.layout;
        if (cacheOf !== G) { for (const k of Object.keys(fitCache)) delete fitCache[k]; cacheOf = G; }      // another tree: measured again
        for (const l of Object.keys(LAYOUTS)) {
            if (fitCache[l]) continue;
            if (l !== st.layout) { st.layout = l; ctx.rebuild(); }
            fitCache[l] = treeFit(G.panel.view);
        }
        if (st.layout !== now) { st.layout = now; ctx.rebuild(); fit(); }
    }

    // ---- the summary: every screen at the chosen UI scale ----
    const report = $('ig_report');
    function paintReport() {
        report.style.display = st.report && active ? '' : 'none';
        const G = ctx.G;
        if (!st.report || !active || !G || !G.panel) return;
        measureLayouts();
        const view = G.panel.view;
        const t = view.selMeta && view.selMeta.textEl;
        const colFont = t ? parseFloat(getComputedStyle(t).fontSize) : 12;
        const m = myScreen();
        const rows = [['1920x1080', 1920, 1080], ['2560x1440', 2560, 1440], ['3840x2160', 3840, 2160], ['mine', m.w, m.h]].map(([k, w, h]) => {
            const z = rootSize(w, h, st.ui), P = panelUnits(z.w, z.h), same = P.w === 1560 && P.h === 870;
            const px = (u, d = 0) => num(u * z.s, d);
            const seen = l => (fitCache[l] ? `${same ? '' : '≈'}${fitCache[l].seen}` : '—');
            const cur = k === st.res || (st.res === 'mine' && k === 'mine');
            return `<tr class="${cur ? 'cur' : ''}"><td>${k === 'mine' ? `мой ${w}×${h}` : `${w}×${h}`}</td><td>${num(st.ui, 2)}${z.s < st.ui - 1e-9 ? ` → <b>${num(z.s, 2)}</b>` : ''}</td>`
                + `<td>${z.w}×${z.h}</td><td>${px(P.w)}×${px(P.h)}<br><span>${num(P.w * z.s / w * 100)} % ширины</span></td>`
                + `<td><b>${px(NODE)}</b></td><td>${px(CARD_W)}×${px(CARD_H)}</td><td>${px(colFont, 1)}</td><td>${px(INFO_TEXT, 1)}</td>`
                + `<td>${fitCache.A ? `${px(fitCache.A.w)}×${px(fitCache.A.h)}` : '—'}</td><td>${seen('A')}${fitCache.A && fitCache.A.open ? ` <span>(развёрнуто ${fitCache.A.open.seen})</span>` : ''}</td><td>${seen('B')}</td><td>${seen('C')}</td></tr>`;
        }).join('');
        const f = fitCache.A || {total: 0};
        const win = l => (fitCache[l] ? `${fitCache[l].w}×${fitCache[l].h} ед.` : '—');
        report.innerHTML = `<button class="close" title="Закрыть (R)">×</button><h3>Сколько дерева видно и какого всё размера</h3>
            <p>UI ${num(st.ui, 2)}; все размеры — в пикселях экрана игры. Построек в дереве: <b>${f.total}</b>, всё дерево ${f.cw || '—'}×${f.ch || '—'} ед.
            Узлы считаются целиком видимые в окне дерева без прокрутки, в исходном положении окна.</p>
            <table><thead><tr><th>Экран</th><th>UI</th><th>Корень, ед.</th><th>Панель, px</th><th>Слот 74</th><th>Карточка 23×50</th><th>Текст колонки</th><th>Текст окна сведений</th><th>Окно дерева A, px</th><th>Видно A</th><th>B</th><th>C</th></tr></thead><tbody>${rows}</tbody></table>
            <p>Окно дерева: A ${win('A')}, B ${win('B')}, C ${win('C')}. Панель в единицах интерфейса одна и та же на всех экранах, где корень не меньше 1600×900:
            игра показывает ту же картинку, только крупнее или мельче. Поэтому число видимых узлов от разрешения не зависит, от него зависит только размер в пикселях.
            Текст колонки: ${st.font ? 'шрифт игры (кегль 12 = 16 ед.)' : 'шрифт страницы (12 ед.; в игре 16)'}; окно сведений постройки и так в размере игры.</p>
            <p class="rec"><b>Совет:</b> B — дерево на месте чертежа, чертёж по вкладке. Видно больше всего узлов в игровом размере слота, сведения постройки читаются полностью; чертёж нужен реже, чем дерево, и открывается одной кнопкой.
            C — компромисс без вкладок, но чертёж мельче. A — дерево видно кусками, приходится всё время листать или разворачивать.</p>`;
        report.querySelector('.close').addEventListener('click', () => { st.report = false; paintButtons(); paintReport(); });
    }

    return {
        // for checks from the console: mtb.ig.set({res: '2560x1440', ui: 1.6, show: 'one', layout: 'B', ruler: true})
        set(o) { Object.assign(st, o); resSel.value = st.res; uiSel.value = String(st.ui); laySel.value = st.layout; changed(); ctx.refresh(); },
        spec, fit, uiScale, rootSize, myScreen, state: st, treeFit: () => ctx.G && treeFit(ctx.G.panel.view), fitCache, shown: () => shown,
        enter() {
            if (active) return;
            active = true;
            frameEl.insertBefore(host, overlay);
            paintButtons(); paintPlate(); paintReport();
            requestAnimationFrame(() => ctx.refresh());       // the texts measured again in the mode's fonts
        },
        leave() {
            if (!active) return;
            active = false;
            if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
            $('left').prepend(host);
            host.style.width = host.style.height = '';
            st.report = false;
            paintReport();
            overlay.style.display = 'none';
            document.body.classList.remove('ig-noplate', 'ig-gamefont');
            requestAnimationFrame(() => ctx.refresh());
        },
    };
}
