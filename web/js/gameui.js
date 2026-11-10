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

// The text layouts of tools/crew_ui.py: font category, size, colour. The game's fonts are not on this page: a serif stands in.
const TEXT = {
    text_title: {size: 24, colour: '#FFF8D7', bold: true, align: 'center', nowrap: true, font: 'header'},
    text_head: {size: 18, colour: '#EBBD7C', bold: true, nowrap: true, font: 'header'},
    text_name: {size: 14, colour: '#FFF8D7', nowrap: true, font: 'header'},
    // a button's label, centred: a layout the mod does not have yet (tools/crew_ui.py: text_layout(..., "Center", "Never split"))
    // the number of men on a unit card (land_unit_card, unit_strength_number): small, centred
    text_card_number: {size: 11, colour: '#FFF8D7', bold: true, align: 'center', nowrap: true},
    // the game's building information window (ui/campaign ui/building_information.twui.xml): the title header_14 centred, the chain's name and the
    // description body_12 centred (the description italic), the entries body_12. Colours as the game draws them (docs/feedback/01-building-tooltip.png):
    // the title #FFF8D7, the chain's name and the description dimmer, effects green, a reason red.
    // Sizes: the game's font sizes are points, 12 is 16 px and 14 is 19 px on the screen, lines 22 px apart (measured on that screenshot, which is 1:1:
    // its window is 400 wide as the template's). The page's older layouts above use the number as px and are smaller than the game's.
    text_info_title: {size: 19, colour: '#FFF8D7', align: 'center', nowrap: true, font: 'header'},
    text_info_centre: {size: 16, line: 22, colour: '#A19883', align: 'center', valign: 'top'},
    text_info_italic: {size: 16, line: 22, colour: '#A19883', align: 'center', valign: 'top', italic: true},
    text_info: {size: 16, line: 22, colour: '#FFF8D7', valign: 'top'},
    // a short caption under a card, centred, two lines at most
    // (16 px, the game's body size on the screen: at the scale the page has on a screen, about 0.6, it is still 10 px)
    text_caption: {size: 16, line: 20, colour: '#FFF8D7', align: 'center', valign: 'top'},
    text_caption_grey: {size: 16, line: 20, colour: '#8E8A80', align: 'center', valign: 'top'},
    text_caption_left: {size: 16, colour: '#FFF8D7', nowrap: true},
    text_caption_copper: {size: 16, colour: '#EBBD7C', align: 'right', nowrap: true},
    text_button: {size: 14, colour: '#FFF8D7', align: 'center', nowrap: true, font: 'header'},
    text_name_grey: {size: 14, colour: '#8E8A80', nowrap: true, font: 'header'},
    text_body: {size: 12, colour: '#FFF8D7', valign: 'top'},
    text_line: {size: 12, colour: '#FFF8D7', nowrap: true},
    text_line_grey: {size: 12, colour: '#8E8A80', nowrap: true},
    text_copper: {size: 12, colour: '#EBBD7C', nowrap: true},
    text_note: {size: 12, colour: '#8E8A80', valign: 'top'},
    // the green of a building's effect lines in the game's list of effects (EffectList); the shade is a guess, the game's own is not read
    // ink on the parchment, for the turns written on the drawing: a layout the mod does not have yet (tools/crew_ui.py would get it)
    text_ink: {size: 15, colour: '#3B2110', bold: true, nowrap: true, font: 'header'},
    text_green: {size: 12, colour: '#9BD36A', valign: 'top'},
};

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
    SetImagePath(path) { this.path = path; if (this.img) this.img.src = url(path); }
    SetStateText(text) { this.text = text; if (this.textEl) this.textEl.innerHTML = colourText(text); }
    GetStateText() { return this.text || ''; }
    // the game's uic:TextDimensions(): width, height and lines of the text as laid out in the component's width
    TextDimensions() {
        if (!this.textEl) return [0, 0, 0];
        const hidden = [];      // a component not shown has no layout: shown for the measure, in the same frame
        for (let c = this; c; c = c.parent) if (c.el.style.display === 'none') { hidden.push(c); c.el.style.display = ''; }
        try { return this.measureText(); } finally { for (const c of hidden) c.el.style.display = 'none'; }
    }
    measureText() {
        const r = document.createRange();
        r.selectNodeContents(this.textEl);
        const rect = r.getBoundingClientRect(), scale = this.el.getBoundingClientRect().width / (this.w || 1) || 1;
        const lineH = parseFloat(getComputedStyle(this.textEl).lineHeight) || 15;
        const h = this.text ? Math.ceil(rect.height / scale) : 0;
        return [Math.ceil(rect.width / scale), h, Math.round(h / lineH)];
    }
    SetTooltipText(text) { this.tooltip = text; if (tooltipOwner === this) { tooltipBox.innerHTML = colourText(text); if (!text) { tooltipOwner = null; hideTooltip(); } } }
    SetOpacity(a) { this.el.style.opacity = String(a / 255); }      // 0..255 as the game's
    SetState(state) { this.state = state; this.paintSkin(); }
    CurrentState() { return this.state; }
    ShaderTechniqueSet(name) {      // the game's greyscale shader
        this.greyFilter = name === 'set_greyscale_t0' ? 'grayscale(1)' : '';
        this.paintFilter();
    }
    paintFilter() { this.el.style.filter = [this.colourFilter, this.greyFilter, this.hoverFilter].filter(Boolean).join(' '); }
    SetDisabled(on) { this.SetState(on ? 'inactive' : 'active'); }
    // The colour of a state's image (the twui's image colour, RGBA): the RGB darkens it as the game's multiply does, the alpha is its opacity.
    // A real colour (not a grey) tints: the picture's shape filled with the colour, as the game's multiply does to a white picture (a bar).
    SetImageColour(r, g, b, a) {
        this.el.style.opacity = String(a / 255);
        if (this.img && (r !== g || g !== b)) {
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
        if (on && !this.clickable) {
            this.clickable = true;
            this.el.addEventListener('mouseup', e => { if (e.button === 0) clickHandler(this); });
        }
    }
    // An image that does not take the mouse (a state without interactive="true"): the mouse goes to what lies under it
    SetPassive() { this.el.style.pointerEvents = 'none'; }
    // A child shown while the mouse is over this component (the hover state's extra picture)
    SetHoverChild(child) {
        if (this.hoverChild && this.hoverChild !== child) this.hoverChild.SetVisible(false);
        this.hoverChild = child;
        if (child) child.SetVisible(!!this.hovered);
    }
    // A movie component (the game's MoviePlayer): the first of the files that exists plays looped and silent; none: a placeholder text
    async SetMovie(urls, placeholder) {
        this.el.innerHTML = '';
        for (const u of urls) {
            try {
                const r = await fetch(u, {method: 'HEAD'});
                if (!r.ok) continue;
            } catch (e) { continue; }
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
    // More children shown while the mouse is over this component, beside the one of SetHoverChild (a tooltip window of the component's own)
    AddHoverChild(child) { (this.hoverChildren ||= []).push(child); child.SetVisible(!!this.hovered); }
    // the hover state's brighten_t0 shader (0.40 on the slot): brightness raised while the mouse is over
    SetHoverBrighten(k) { this.hoverBrighten = k; }

    // ---- inside ----
    makeText(spec) {
        this.textEl = document.createElement('div');
        this.textEl.className = 't' + (spec.nowrap ? ' nowrap' : '') + (spec.valign === 'top' ? ' top' : '') + (spec.font === 'header' ? ' header' : '');
        Object.assign(this.textEl.style, {fontSize: spec.size + 'px', color: spec.colour, fontWeight: spec.bold ? 'bold' : 'normal', fontStyle: spec.italic ? 'italic' : 'normal', lineHeight: spec.line ? spec.line + 'px' : '', textAlign: spec.align || 'left',
                                          justifyContent: spec.align === 'center' ? 'center' : 'flex-start'});
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
function hideTooltip() { tooltipBox.style.display = 'none'; }
