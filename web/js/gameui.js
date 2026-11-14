// A small stand-in for the game's UIComponent, so the panel code reads as src/tww3_mtb_crew_ui.lua does and its numbers carry over to the game unchanged.
// Only what the game's UI has: pictures, text and buttons at offsets from the parent's top left corner (SetDockingPoint(1) + SetDockOffset), sizes (Resize),
// states of a button, SetVisible, SetOpacity, the greyscale shader, tooltips. No animation, no CSS effect the game lacks.
// Paths are the pack paths the game would use; url() maps them to the files this page has.

const LAYOUTS = 'ui/tww3_mtb/';

// pack path -> url of this page (tools/web_serve.py)
export function url(path) {
    if (path.startsWith(LAYOUTS + 'web/')) return '/art/' + path.slice((LAYOUTS + 'web/').length);   // the stage layers of tools/web_art.py
    if (path.startsWith(LAYOUTS)) return '/mod/ui/' + path.slice(LAYOUTS.length);                     // data/ui, as tools/crew_ui.py packs it
    if (path.startsWith('ui/buildings/icons/tww3_mtb_')) return '/mod/ui/buildings/' + path.slice('ui/buildings/icons/tww3_mtb_'.length);  // tools/crew_buildings.py
    if (path.startsWith('ui/skins/tww3_mtb/')) return '/build/game/' + path;                              // recoloured copies of the game's pictures, tools/web_export.py
    return '/build/game/' + path;                                                                         // the game's own pictures, tools/web_export.py
}

// The text layouts (web/js/ui_text.mjs, the one table the mod's layouts are written from: tools/ship_ui.py). The game's fonts are not on this page:
// a serif stands in.
import {TEXT} from './ui_text.mjs';

// Button skins: the picture of each state, as button_layout() of tools/crew_ui.py; margins of the 9-slice in the layout's units.
const SKIN = {
    button_row: {base: 'row', margin: 24, scale: 2},
    button_plate: {base: 'plate', margin: 24, scale: 2},
    button_mark: {base: 'web/mark', margin: 0, scale: 1},      // the marks of Malakai's side: tools/web_art.py, side_art
};
const STATE_IMAGE = {active: 'normal', hover: 'hover', down: 'selected', down_off: 'hover', selected: 'selected', selected_hover: 'selected', inactive: 'locked', invalid: 'hover'};
// the game's own state changes on the mouse (transitions of button_layout)
const ON_ENTER = {active: 'hover', selected: 'selected_hover'};
const ON_LEAVE = {hover: 'active', selected_hover: 'selected', down: 'active', down_off: 'active'};

// The clips the page has (web/art/*.webm, *.mp4): read once from the folder's listing, so a clip put there is taken at the next load and a clip that
// is not there costs no failed request.
let clipList = null;
function clips() {
    clipList ||= fetch('/art/').then(r => (r.ok ? r.text() : '')).then(t => new Set([...t.matchAll(/href="([^"]+\.(?:webm|mp4))"/g)].map(m => decodeURIComponent(m[1])))).catch(() => new Set());
    return clipList;
}

let inkCanvas = null;       // Component.InkDimensions
let tooltipBox = null;
let tooltipOwner = null;     // the component whose tooltip is shown
let clickHandler = () => {};
export function onClick(fn) { clickHandler = fn; }    // core:add_listener('ComponentLClickUp', ...)

function colourText(text) {
    // [[col:yellow]]...[[/col]] of the game's texts
    const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return esc(text).replace(/\[\[col:(\w+)\]\]/g, (_, c) => `<span class="col_${c}">`).replace(/\[\[\/col\]\]/g, '</span>').replace(/\n/g, '<br>');
}

export class Component {
    constructor(parent, id, layout) {
        this.id = id;
        this.layout = layout;
        this.parent = parent;
        this.children = [];
        this.el = document.createElement('div');
        this.el.className = 'c ' + layout;
        this.el.dataset.id = id;
        this.w = 64; this.h = 64; this.x = 0; this.y = 0;
        this.state = null;
        this.tooltip = '';
        if (parent) { parent.el.appendChild(this.el); parent.children.push(this); }
        if (TEXT[layout]) this.makeText(TEXT[layout]);
        if (SKIN[layout]) this.makeButton(SKIN[layout]);
        if (layout === 'movie') this.el.classList.add('movie');
        if (layout === 'image') { this.img = document.createElement('img'); this.img.draggable = false; this.el.appendChild(this.img); }
        this.el.addEventListener('mouseenter', e => this.onEnter(e));
        this.el.addEventListener('mousemove', e => this.onMove(e));
        this.el.addEventListener('mouseleave', e => this.onLeave(e));
    }

    // ---- the UIComponent methods the panel uses ----
    CreateComponent(id, layout) { return new Component(this, id, layout); }
    Id() { return this.id; }
    SetVisible(on) { this.el.style.display = on ? '' : 'none'; }
    Visible() { return this.el.style.display !== 'none'; }
    Resize(w, h) { this.w = Math.round(w); this.h = Math.round(h); this.el.style.width = this.w + 'px'; this.el.style.height = this.h + 'px'; this.paintSkin(); }
    Width() { return this.w; }
    Height() { return this.h; }
    SetDockOffset(x, y) { this.x = Math.round(x); this.y = Math.round(y); this.el.style.left = this.x + 'px'; this.el.style.top = this.y + 'px'; }
    MoveTo(x, y) { this.SetDockOffset(x, y); }
    // A picture changed on a component already shown (the drawing's sheet when the barge is built) keeps the old one until the new one is loaded and
    // decoded, so the screen never shows a hole where it was; the first picture of a component goes in at once (whenPictures holds the first frame).
    SetImagePath(path) {
        this.path = path;
        if (!this.img) return;
        const u = url(path);
        if (this.img.getAttribute('src') === u) return;
        if (!(this.img.getAttribute('src') && this.img.complete && this.img.naturalWidth)) { this.img.src = u; return; }
        const pre = new Image();
        pre.src = u;
        const swap = () => { if (this.path === path) { this.img.src = u; if (this.maskColour) this.SetImageColour(...this.maskColour); } };
        if (pre.complete && pre.naturalWidth) swap(); else pre.decode().then(swap, swap);
    }
    SetStateText(text) { this.text = text; if (this.textEl) this.textEl.innerHTML = colourText(text); }
    GetStateText() { return this.text || ''; }
    // the game's uic:TextDimensions(): width, height and lines of the text as laid out in the component's width
    TextDimensions() {
        if (!this.textEl) return [0, 0, 0];
        const hidden = [];      // a component not shown has no layout: shown for the measure, in the same frame
        for (let c = this; c; c = c.parent) if (c.el.style.display === 'none') { hidden.push(c); c.el.style.display = ''; }
        try { const d = this.measureText(); MEASURES[measureKey(this)] = d; return d; } finally { for (const c of hidden) c.el.style.display = 'none'; }
    }
    measureText() {
        const r = document.createRange();
        r.selectNodeContents(this.textEl);
        const rect = r.getBoundingClientRect(), scale = this.el.getBoundingClientRect().width / (this.w || 1) || 1;
        const lineH = parseFloat(getComputedStyle(this.textEl).lineHeight) || 15;
        const h = this.text ? Math.ceil(rect.height / scale) : 0;
        return [Math.ceil(rect.width / scale), h, Math.round(h / lineH)];
    }
    // The page's stand-ins for fitting a text to the picture it is written on (the title on its plate): the text's size in units (GAME: a text layout
    // of a smaller header font), and its ink as drawn, in units at that size: the advance width, the ink's left / right from the start of the line
    // and its ascent / descent from the baseline, and the font's own ascent / descent (what places the baseline in a line: CSS centres the line, not
    // the ink, so a word with descenders sits low in its box).
    SetTextSize(px) { if (this.textEl) { this.textEl.style.fontSize = px + 'px'; this.textSize = px; } }
    TextSize() { return this.textEl ? parseFloat(this.textEl.style.fontSize) || 0 : 0; }
    InkDimensions() {
        if (!this.textEl || !this.text) return null;
        const cs = getComputedStyle(this.textEl), c = (inkCanvas ||= document.createElement('canvas')).getContext('2d');
        c.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
        c.letterSpacing = cs.letterSpacing === 'normal' ? '0px' : cs.letterSpacing;
        const m = c.measureText(this.textEl.textContent);
        return MEASURES['ink|' + this.layout + '|' + this.TextSize() + '|' + this.text] = {w: m.width, left: -m.actualBoundingBoxLeft, right: m.actualBoundingBoxRight, ascent: m.actualBoundingBoxAscent, descent: m.actualBoundingBoxDescent,
                fontAscent: m.fontBoundingBoxAscent, fontDescent: m.fontBoundingBoxDescent};
    }
    SetTooltipText(text) { this.tooltip = text; if (tooltipOwner === this) { tooltipBox.innerHTML = colourText(text); if (!text) { tooltipOwner = null; hideTooltip(); } } }
    SetOpacity(a) { this.el.style.opacity = String(a / 255); this.opacity = a; }      // 0..255 as the game's
    SetState(state) { this.state = state; this.paintSkin(); }
    CurrentState() { return this.state; }
    ShaderTechniqueSet(name) {      // the game's greyscale shader
        this.shader = name;
        this.greyFilter = name === 'set_greyscale_t0' ? 'grayscale(1)' : '';
        this.paintFilter();
    }
    paintFilter() { this.el.style.filter = [this.colourFilter, this.greyFilter, this.hoverFilter, this.glowFilter].filter(Boolean).join(' '); }
    // The glow of something new (a detail the turn added to the ship): GAME: a state of the component with the picture again under it, additive
    // kind 'soft': a narrower halo for a control in a tight row (a tab under the title's edge), 6 units at most round its shape
    SetGlow(on, kind) {
        this.glow = on ? kind || 'glow' : '';
        const g = !on ? '' : kind === 'soft' ? 'drop-shadow(0 0 2px rgba(255, 220, 120, 1)) drop-shadow(0 0 4px rgba(255, 170, 60, 1)) drop-shadow(0 0 6px rgba(255, 140, 30, 0.8))'
            : 'drop-shadow(0 0 3px rgba(255, 214, 110, 0.95)) drop-shadow(0 0 9px rgba(255, 150, 40, 0.85))';
        if (g === (this.glowFilter || '')) return;
        this.glowFilter = g;
        this.paintFilter();
    }
    SetDisabled(on) { this.SetState(on ? 'inactive' : 'active'); }
    // The colour of a state's image (the twui's image colour, RGBA): the RGB darkens it as the game's multiply does, the alpha is its opacity.
    // A real colour (not a grey) tints: the picture's shape filled with the colour, as the game's multiply does to a white picture (a bar).
    SetImageColour(r, g, b, a) {
        this.colour = [r, g, b, a];
        this.el.style.opacity = String(a / 255);
        if (this.img && (r !== g || g !== b)) {
            this.maskColour = [r, g, b, a];
            const mask = `url("${this.img.src}")`;
            Object.assign(this.el.style, {backgroundColor: `rgb(${r},${g},${b})`, maskImage: mask, webkitMaskImage: mask, maskSize: '100% 100%', webkitMaskSize: '100% 100%'});
            this.img.style.visibility = 'hidden';
            return;
        }
        const k = Math.min(r, g, b) / 255;
        this.colourFilter = k < 1 ? `brightness(${k.toFixed(2)})` : '';
        this.paintFilter();
    }
    // An image or text that takes the mouse, as an interactive state of the game: a click goes where a button's would (ComponentLClickUp)
    SetInteractive(on) {
        this.interactive = !!on;
        if (on && !this.clickable) {
            this.clickable = true;
            // the click belongs to the innermost component that takes it: what lies under it does not get it too
            this.el.addEventListener('mouseup', e => { if (e.button === 0) { e.stopPropagation(); clickHandler(this); } });
        }
    }
    // An image that does not take the mouse (a state without interactive="true"): the mouse goes to what lies under it
    SetPassive() { this.el.style.pointerEvents = 'none'; this.passive = true; }
    // A child shown while the mouse is over this component (the hover state's extra picture)
    SetHoverChild(child) {
        if (this.hoverChild && this.hoverChild !== child) this.hoverChild.SetVisible(false);
        this.hoverChild = child;
        if (child) child.SetVisible(!!this.hovered);
    }
    // A movie component (the game's MoviePlayer): the first of the files that exists plays looped and silent; none: a placeholder text
    async SetMovie(urls, placeholder) {
        this.el.innerHTML = '';
        const have = await clips();
        for (const u of urls) {
            if (!have.has(u.split('/').pop())) continue;
            const v = document.createElement('video');
            Object.assign(v, {src: u, loop: true, muted: true, autoplay: true, playsInline: true});
            v.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block';
            this.el.appendChild(v);
            this.movie = u;
            return;
        }
        this.movie = null;
        const p = document.createElement('div');
        p.className = 'movie_placeholder';
        p.textContent = placeholder;
        this.el.appendChild(p);
    }
    // The layer of a window (web/css/page.css, the one scale of z-index): 'click' a window opened by a click, 'hover' a window shown under the mouse.
    // A window under the mouse is always over a window opened by a click, and both over the drawing and the panel.
    SetLayer(name) { this.el.classList.add('layer_' + name); this.layerName = name; return this; }
    // More children shown while the mouse is over this component, beside the one of SetHoverChild (a tooltip window of the component's own)
    AddHoverChild(child) { (this.hoverChildren ||= []).push(child); child.SetVisible(!!this.hovered); }
    // the hover state's brighten_t0 shader (0.40 on the slot): brightness raised while the mouse is over
    SetHoverBrighten(k) { this.hoverBrighten = k; }

    // ---- inside ----
    makeText(spec) {
        this.textEl = document.createElement('div');
        this.textEl.className = 't' + (spec.nowrap ? ' nowrap' : '') + (spec.valign === 'top' ? ' top' : '') + (spec.font === 'header' ? ' header' : '');
        Object.assign(this.textEl.style, {fontSize: spec.size + 'px', color: spec.colour, fontWeight: spec.bold ? 'bold' : 'normal', fontStyle: spec.italic ? 'italic' : 'normal', lineHeight: spec.line ? spec.line + 'px' : '', textAlign: spec.align || 'left',
                                          justifyContent: spec.align === 'center' ? 'center' : spec.align === 'right' ? 'flex-end' : 'flex-start'});
        this.el.appendChild(this.textEl);
    }
    makeButton(skin) {
        this.skin = skin;
        this.state = 'active';
        this.el.addEventListener('mousedown', e => {
            if (e.button !== 0 || this.state === 'inactive') return;
            if (this.state === 'hover' || this.state === 'active') this.SetState('down');
        });
        this.el.addEventListener('mouseup', e => {
            if (e.button !== 0 || this.state === 'inactive') return;
            if (this.state === 'down') this.SetState('hover');
            e.stopPropagation();
            clickHandler(this);
        });
    }
    paintSkin() {
        // the 9-slice picture of the state, on a layer of its own under the children, so children keep offsets from the button's own corner as in the game
        if (!this.skin) return;
        if (!this.skinEl) { this.skinEl = document.createElement('div'); this.skinEl.className = 'skin'; this.el.prepend(this.skinEl); }
        const image = STATE_IMAGE[this.state] || 'normal';
        const m = this.skin.margin;
        const s = this.skinEl.style;
        s.borderWidth = m + 'px';
        s.borderImageSource = `url(${url(LAYOUTS + this.skin.base + '_' + image + '.png')})`;
        s.borderImageSlice = `${m * this.skin.scale} fill`;
        this.el.classList.toggle('disabled', this.state === 'inactive');
    }
    onEnter(e) {
        if (this.skin && ON_ENTER[this.state]) this.SetState(ON_ENTER[this.state]);
        this.hovered = true;
        if (this.hoverChild) this.hoverChild.SetVisible(true);
        for (const c of this.hoverChildren || []) c.SetVisible(true);
        if (this.hoverBrighten) { this.hoverFilter = `brightness(${1 + this.hoverBrighten})`; this.paintFilter(); }
        if (this.tooltip) { tooltipOwner = this; showTooltip(this.tooltip, e); }
    }
    onMove(e) { if (tooltipOwner === this) moveTooltip(e); }
    onLeave() {
        if (this.skin && ON_LEAVE[this.state]) this.SetState(ON_LEAVE[this.state]);
        this.hovered = false;
        if (this.hoverChild) this.hoverChild.SetVisible(false);
        for (const c of this.hoverChildren || []) c.SetVisible(false);
        if (this.hoverBrighten) { this.hoverFilter = ''; this.paintFilter(); }
        if (tooltipOwner === this) { tooltipOwner = null; hideTooltip(); }
    }
}

// The root of the game's interface: 1600 x 900 at 1280 x 720 (docs/summary.md, section 6). The page scales it as a whole, the numbers inside stay the game's.
export function makeRoot(host, w = 1600, h = 900) {
    const root = new Component(null, 'root', 'root');
    root.Resize(w, h);
    host.appendChild(root.el);
    tooltipBox = document.createElement('div');
    tooltipBox.className = 'tooltip';
    tooltipBox.style.display = 'none';
    root.el.appendChild(tooltipBox);
    root.scale = 1;
    return root;
}

let rootOf = null;
export function setTooltipRoot(root) { rootOf = root; }

// The screen shown whole, never half drawn: the root is kept hidden until every picture in it has loaded (or failed, or `ms` passed), then shown in
// one frame. The game itself loads a panel's pictures before it draws it. -> a promise, resolved when shown
export function whenPictures(root, ms = 5000) {
    root.el.style.visibility = 'hidden';
    const imgs = [...root.el.querySelectorAll('img')].filter(i => i.getAttribute('src'));
    const one = i => (i.complete ? Promise.resolve() : new Promise(res => { i.addEventListener('load', res, {once: true}); i.addEventListener('error', res, {once: true}); }))
        .then(() => (i.complete && i.naturalWidth && i.decode ? i.decode().catch(() => {}) : null));
    return Promise.race([Promise.all(imgs.map(one)), new Promise(res => setTimeout(res, ms))])
        .then(() => new Promise(res => requestAnimationFrame(() => { root.el.style.visibility = ''; root.pictures = true; res(); })));
}

function place(e) {
    const r = rootOf.el.getBoundingClientRect();
    const k = r.width / rootOf.w;
    let x = (e.clientX - r.left) / k + 18, y = (e.clientY - r.top) / k + 20;
    const bw = tooltipBox.offsetWidth, bh = tooltipBox.offsetHeight;
    if (x + bw > rootOf.w - 4) x = Math.max(4, (e.clientX - r.left) / k - bw - 12);
    if (y + bh > rootOf.h - 4) y = Math.max(4, rootOf.h - bh - 4);
    tooltipBox.style.left = x + 'px';
    tooltipBox.style.top = y + 'px';
}
function showTooltip(text, e) { tooltipBox.innerHTML = colourText(text); tooltipBox.style.display = ''; place(e); }
function moveTooltip(e) { if (tooltipBox.style.display !== 'none') place(e); }
function hideTooltip() { if (tooltipBox) tooltipBox.style.display = 'none'; }
// a tooltip whose component went away under a still mouse (a tab changed): no leave comes, so it is taken away here
export function clearTooltip() { tooltipOwner = null; hideTooltip(); }

// ---------------- the screen as data, for the game's port (docs/design/port-to-game.md, 4.2 «Экран без игры») ----------------
// Every text measured (uic:TextDimensions, and the ink of the title plate), by what decides its size: the layout, the box's width, the text. The mod's
// offline check (tools/ui_layout_check.py, tools/tests/fake_uic.lua) takes these numbers for its own measures, so the Lua lays out the same texts the
// same way the page did; in the game the game's TextDimensions answers instead.
const MEASURES = {};
const measureKey = c => c.layout + '|' + c.w + '|' + (c.text || '');
export function measures() { return {...MEASURES}; }
export function clearMeasures() { for (const k of Object.keys(MEASURES)) delete MEASURES[k]; }

const r2 = v => Math.round(v * 100) / 100;
// The component tree under c as the game would hold it: one row a component, parents before children, each with its path of ids (a second sibling of
// the same id gets #2), its layout, the offset from its parent's corner and the size, its own visibility (SetVisible), the text, the button's state,
// the picture, and what the game sets on it besides (SetImageColour, ShaderTechniqueSet, SetOpacity, SetTooltipText, the glow state, the layer, the
// interactive flag, a text size; blank and image_opacity below). The tree's holder is moved by a transform on the page (its pan and zoom): its offset is the pan, as SetDockOffset
// would give it in the game, and scale the zoom.
export function dump(c, path = null, out = []) {
    const row = {path: path || c.id, id: c.id, layout: c.layout, x: c.x, y: c.y, w: c.w, h: c.h, visible: c.el.style.display !== 'none'};
    const t = c.el.style.transform;
    if (t) {
        const m = /translate\(([-\d.e]+)px, ([-\d.e]+)px\)(?: scale\(([-\d.e]+)\))?/.exec(t);
        if (m) { row.x = r2(c.x + Number(m[1])); row.y = r2(c.y + Number(m[2])); if (m[3] && Number(m[3]) !== 1) row.scale = r2(Number(m[3])); }
    }
    if (c.textEl) row.text = c.text || '';
    if (c.state !== null && c.state !== undefined) row.state = c.state;
    if (c.path) row.image = c.path;
    if (c.colour) row.colour = c.colour;
    if (c.shader) row.shader = c.shader;
    if (c.opacity !== undefined) row.opacity = c.opacity;
    if (c.tooltip) row.tooltip = c.tooltip;
    if (c.glow) row.glow = c.glow;
    if (c.layerName) row.layer = c.layerName;
    if (c.interactive || c.skin) row.interactive = true;
    if (c.textSize !== undefined) row.text_size = c.textSize;
    // the page's own ways of showing nothing although shown (a window with nothing to say, a hover picture of a button that does nothing), and of
    // a picture fainter than its component (a card being recruited): in the game a state of the component, here kept apart
    if (c.el.style.visibility === 'hidden') row.blank = true;
    if (c.img && c.img.style.opacity) row.image_opacity = Math.round(parseFloat(c.img.style.opacity) * 255);
    out.push(row);
    const seen = {};
    for (const k of c.children) {
        seen[k.id] = (seen[k.id] || 0) + 1;
        dump(k, row.path + '/' + k.id + (seen[k.id] > 1 ? '#' + seen[k.id] : ''), out);
    }
    return out;
}
