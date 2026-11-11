// A small driver of a headless Chrome over the DevTools protocol, for walking the page as a user does: real mouse and key events, pictures,
// the console. node --experimental-websocket (node 20; node 22 has WebSocket without the flag). No package needed.
//   const b = await launch({width, height}); await b.open(url); await b.click(x, y); await b.shot(path); await b.close();
import {spawn} from 'node:child_process';
import {mkdirSync, writeFileSync, rmSync} from 'node:fs';
import {inflateSync} from 'node:zlib';
import {join} from 'node:path';
import {tmpdir} from 'node:os';

const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
export const sleep = ms => new Promise(r => setTimeout(r, ms));

// A PNG of Chrome's screenshot (8 bit RGB or RGBA, not interlaced) to its pixels: {width, height, data: RGBA}
export function decodePng(buf) {
    let p = 8, width = 0, height = 0, type = 6;
    const idat = [];
    while (p < buf.length) {
        const len = buf.readUInt32BE(p), kind = buf.toString('ascii', p + 4, p + 8), body = buf.subarray(p + 8, p + 8 + len);
        if (kind === 'IHDR') { width = body.readUInt32BE(0); height = body.readUInt32BE(4); type = body[9]; }
        if (kind === 'IDAT') idat.push(body);
        p += 12 + len;
    }
    const bpp = type === 6 ? 4 : 3, raw = inflateSync(Buffer.concat(idat)), stride = width * bpp;
    const out = Buffer.alloc(width * height * 4), prev = Buffer.alloc(stride), row = Buffer.alloc(stride);
    for (let y = 0; y < height; y++) {
        const f = raw[y * (stride + 1)];
        for (let x = 0; x < stride; x++) {
            const v = raw[y * (stride + 1) + 1 + x], a = x >= bpp ? row[x - bpp] : 0, b = prev[x], c = x >= bpp ? prev[x - bpp] : 0;
            const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c);
            row[x] = (v + [0, a, b, (a + b) >> 1, pa <= pb && pa <= pc ? a : pb <= pc ? b : c][f]) & 255;
        }
        for (let x = 0; x < width; x++) { for (let k = 0; k < 3; k++) out[(y * width + x) * 4 + k] = row[x * bpp + k]; out[(y * width + x) * 4 + 3] = bpp === 4 ? row[x * 4 + 3] : 255; }
        row.copy(prev);
    }
    return {width, height, data: out};
}

export async function launch({width = 1200, height = 800, port = 9333, profile = join(tmpdir(), 'mtb_cdp_profile')} = {}) {
    rmSync(profile, {recursive: true, force: true});
    mkdirSync(profile, {recursive: true});
    const proc = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, `--window-size=${width},${height}`, '--hide-scrollbars',
        '--force-device-scale-factor=1', '--no-first-run', '--no-default-browser-check', '--disable-extensions', 'about:blank'], {stdio: 'ignore'});
    let targets = null;
    for (let i = 0; i < 50 && !targets; i++) { await sleep(200); targets = await fetch(`http://127.0.0.1:${port}/json/list`).then(r => r.json()).catch(() => null); }
    const page = targets.find(t => t.type === 'page');
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    let id = 0;
    const waiting = new Map(), listeners = [];
    ws.onmessage = m => {
        const msg = JSON.parse(m.data);
        if (msg.id && waiting.has(msg.id)) { const {res, rej} = waiting.get(msg.id); waiting.delete(msg.id); msg.error ? rej(new Error(msg.error.message)) : res(msg.result); }
        else if (msg.method) for (const l of listeners) l(msg);
    };
    const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; waiting.set(i, {res, rej}); ws.send(JSON.stringify({id: i, method, params})); });
    const errors = [];
    let b = null;
    listeners.push(m => {
        if (m.method === 'Runtime.exceptionThrown') errors.push('exception: ' + (m.params.exceptionDetails.exception ? m.params.exceptionDetails.exception.description : m.params.exceptionDetails.text));
        if (m.method === 'Runtime.consoleAPICalled' && (m.params.type === 'error' || m.params.type === 'warning')) errors.push(`console.${m.params.type}: ` + m.params.args.map(a => a.value ?? a.description).join(' '));
        if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push('log: ' + m.params.entry.text + ' ' + (m.params.entry.url || ''));
        // a dialog of the page (beforeunload, alert) is told and accepted, so a walk never hangs on it
        if (m.method === 'Page.javascriptDialogOpening') { b.dialogs.push(m.params.type + ': ' + m.params.message); send('Page.handleJavaScriptDialog', {accept: true}).catch(() => {}); }
    });
    await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable');
    b = {
        send, errors, dialogs: [], mods: 0, x: 0, y: 0,
        listen(fn) { listeners.push(fn); }, unlisten(fn) { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); },
        async size(w, h) { await send('Emulation.setDeviceMetricsOverride', {width: w, height: h, deviceScaleFactor: 1, mobile: false}); await sleep(300); },
        async open(url) {
            const loaded = new Promise(res => { const l = m => { if (m.method === 'Page.loadEventFired') { listeners.splice(listeners.indexOf(l), 1); res(); } }; listeners.push(l); });
            await send('Page.navigate', {url});
            await loaded;
        },
        async reload() {
            const loaded = new Promise(res => { const l = m => { if (m.method === 'Page.loadEventFired') { listeners.splice(listeners.indexOf(l), 1); res(); } }; listeners.push(l); });
            await send('Page.reload', {ignoreCache: true});
            await loaded;
        },
        async eval(expr) {
            const r = await send('Runtime.evaluate', {expression: expr, awaitPromise: true, returnByValue: true});
            if (r.exceptionDetails) throw new Error('eval: ' + (r.exceptionDetails.exception ? r.exceptionDetails.exception.description : r.exceptionDetails.text) + '\n' + expr.slice(0, 200));
            return r.result.value;
        },
        async until(expr, ms = 8000) {
            for (let t = 0; t < ms; t += 100) { if (await b.eval(expr).catch(() => false)) return true; await sleep(100); }
            throw new Error('timed out: ' + expr);
        },
        async rect(selector) {
            return b.eval(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, l: r.left, t: r.top, w: r.width, h: r.height}; })()`);
        },
        async mouse(type, x, y, extra = {}) {
            b.x = x; b.y = y;
            await send('Input.dispatchMouseEvent', {type, x, y, modifiers: b.mods, ...extra});
        },
        async move(x, y, steps = 1) {
            const x0 = b.x, y0 = b.y;
            for (let i = 1; i <= steps; i++) { await b.mouse('mouseMoved', x0 + (x - x0) * i / steps, y0 + (y - y0) * i / steps, {buttons: b.held || 0, button: b.held ? 'left' : 'none'}); await sleep(12); }
        },
        async down(button = 'left') { b.held = button === 'left' ? 1 : button === 'right' ? 2 : 4; await b.mouse('mousePressed', b.x, b.y, {button, buttons: b.held, clickCount: 1}); },
        async up(button = 'left') { await b.mouse('mouseReleased', b.x, b.y, {button, buttons: 0, clickCount: 1}); b.held = 0; },
        async click(x, y, {button = 'left', count = 1} = {}) {
            await b.move(x, y, 2);
            for (let c = 1; c <= count; c++) {
                await b.mouse('mousePressed', x, y, {button, buttons: button === 'left' ? 1 : 2, clickCount: c});
                await b.mouse('mouseReleased', x, y, {button, buttons: 0, clickCount: c});
            }
            await sleep(120);
        },
        async dblclick(x, y) { await b.click(x, y, {count: 2}); },
        async drag(x0, y0, x1, y1, {steps = 14, hold = null} = {}) {
            await b.move(x0, y0, 2); await b.down(); await sleep(40);
            await b.move(x1, y1, steps); await sleep(60);
            if (hold) await hold();
            await b.up(); await sleep(150);
        },
        async wheel(x, y, dy) { await b.mouse('mouseWheel', x, y, {deltaX: 0, deltaY: dy}); await sleep(80); },
        // a key: name as KeyboardEvent.key; mods: 'ctrl', 'shift', 'ctrl+shift'
        async key(key, mods = '') {
            const m = (mods.includes('alt') ? 1 : 0) | (mods.includes('ctrl') ? 2 : 0) | (mods.includes('shift') ? 8 : 0);
            const special = {Delete: [46, 'Delete'], Backspace: [8, 'Backspace'], Escape: [27, 'Escape'], Enter: [13, 'Enter'], Tab: [9, 'Tab'], F2: [113, 'F2'], F5: [116, 'F5'],
                End: [35, 'End'], Home: [36, 'Home'], ArrowUp: [38, 'ArrowUp'], ArrowDown: [40, 'ArrowDown'], ArrowLeft: [37, 'ArrowLeft'], ArrowRight: [39, 'ArrowRight']};
            const [vk, code] = special[key] || [key.toUpperCase().charCodeAt(0), /^[a-z]$/i.test(key) ? 'Key' + key.toUpperCase() : /^\d$/.test(key) ? 'Digit' + key : key];
            const text = !special[key] && !(m & 2) ? key : undefined;
            await send('Input.dispatchKeyEvent', {type: text ? 'keyDown' : 'rawKeyDown', key, code, windowsVirtualKeyCode: vk, modifiers: m, text});
            await send('Input.dispatchKeyEvent', {type: 'keyUp', key, code, windowsVirtualKeyCode: vk, modifiers: m});
            await sleep(60);
        },
        async type(text) { await send('Input.insertText', {text}); await sleep(60); },
        async shot(path, clip) {
            const r = await send('Page.captureScreenshot', {format: 'png', ...(clip ? {clip: {...clip, scale: 1}} : {})});
            writeFileSync(path, Buffer.from(r.data, 'base64'));
        },
        // the mean brightness (0..255) of a part of the screen as it is drawn: a picture of it, decoded here
        async luma(clip) {
            const r = await send('Page.captureScreenshot', {format: 'png', clip: {...clip, scale: 1}});
            const px = decodePng(Buffer.from(r.data, 'base64'));
            let s = 0;
            for (let i = 0; i < px.data.length; i += 4) s += 0.3 * px.data[i] + 0.59 * px.data[i + 1] + 0.11 * px.data[i + 2];
            return s / (px.data.length / 4);
        },
        async close() { try { await send('Browser.close'); } catch (e) { /* gone */ } ws.close(); setTimeout(() => proc.kill(), 500); },
    };
    return b;
}
