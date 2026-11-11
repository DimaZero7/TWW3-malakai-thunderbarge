// The author's tree after the notes were applied, as he sees it in the constructor: a copy of his file on a server of its own (port 8769), the nest
// selected with its new detail and note, and the forge's army card on the canvas. node --experimental-websocket tools/tests/caps_user_tree_shot.mjs
import {copyFileSync, mkdirSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, sleep} from './cdp.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DATA = join(tmpdir(), 'mtb_user_tree_shot');
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
copyFileSync(join(ROOT, 'web/data/tree_design.json'), FILE);
const server = spawn('py', ['-3.14', join(ROOT, 'tools/web_serve.py'), '--port', '8769', '--tree', FILE], {stdio: 'ignore'});
for (let i = 0; i < 50; i++) { if (await fetch('http://127.0.0.1:8769/data/tree_design.json').then(r => r.ok).catch(() => false)) break; await sleep(200); }
const b = await launch({width: 1280, height: 800, port: 9334, profile: join(tmpdir(), 'mtb_cdp_shot')});
try {
    await b.size(1280, 800);
    await b.open('http://127.0.0.1:8769/?mode=constructor');
    await b.until('!!(window.mtb && mtb.editor && mtb.editor.design().nodes.length === 22)', 15000);
    await sleep(800);
    const item = await b.eval(`(() => { const e = [...document.querySelectorAll('.cx-pal-item')].find(x => (x.title.split(String.fromCharCode(10))[1] || '') === 'mtb_nest_1'); e.scrollIntoView({block: 'nearest'}); const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    await b.click(item.x, item.y);
    await sleep(400);
    await b.eval(`document.querySelector('.cx-props [data-field="note"]').scrollIntoView({block: 'start'})`);
    await sleep(300);
    await b.shot(join(ROOT, 'build/web/shots/caps_user_tree.png'));
    const errs = b.errors;
    console.log(errs.length ? 'errors: ' + errs.join(' | ') : 'clean');
} finally {
    await b.close();
    server.kill();
}
