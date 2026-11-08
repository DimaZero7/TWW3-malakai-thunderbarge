// The overview under the airship screen: every chain of the barge's buildings as cards by tier, for planning where to start.
// Not the game's interface: ordinary page layout. Data: build/web/overview.json (tools/web_export.py, export_overview), nothing typed here.

const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const MISSING = {name: 'нет названия', icon: 'нет значка', cost: 'нет цены', 'effect text': 'эффект без текста', description: 'нет описания',
                 'effect text not in Russian': 'текст эффекта не по-русски'};

function turns(n) {
    const m10 = n % 10, m100 = n % 100;
    return `${n} ${m10 === 1 && m100 !== 11 ? 'ход' : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? 'хода' : 'ходов'}`;
}

function effectLine(e) {
    const value = Number.isInteger(e.value) ? e.value : Math.round(e.value * 100) / 100;
    const text = e.text ? esc(e.text) : `<code>${esc(e.effect)}</code> = ${value}`;
    const cls = ['eff'];
    if (e.ours) cls.push('ours');
    if (e.off) cls.push('off');
    if (e.hidden) cls.push('hidden');
    const notes = [];
    if (e.off) notes.push('выключено модом');
    else if (e.changed) notes.push('изменено модом');
    if (e.hidden) notes.push('скрытый эффект игры');
    if (!e.text) notes.push('нет текста');
    return `<li class="${cls.join(' ')}" title="${esc(e.effect)} · ${esc(e.scope)} · ${value}">${text}${notes.length ? ` <span class="note">(${notes.join(', ')})</span>` : ''}</li>`;
}

function openLine(o) {
    if (o.mount) return `<li><b>Крепление:</b> ${esc(o.mount_name)} (${esc(o.group_name.toLowerCase())})${o.auto ? ', встаёт сразу' : ''}</li>`;
    const money = [o.hire ? `найм ${o.hire}` : '', o.upkeep ? `содержание ${o.upkeep}/ход` : ''].filter(Boolean).join(', ');
    return `<li><b>${esc(o.group_name)}:</b> ${esc(o.name)}${money ? ` <span class="money">${money}</span>` : ''}${o.auto ? ' <span class="note">(встаёт сразу)</span>' : ''}</li>`;
}

function card(c) {
    const req = [];
    if (c.hull_needed) req.push(`корпус «${esc(c.hull_needed)}»`);
    if (c.after) req.push(`«${esc(c.after)}»`);
    for (const r of c.requires) req.push(`«${esc(r.name || r.key)}»`);
    const parts = c.parts.map(p => `<span class="part ${p.enabled ? 'on' : ''}" title="Деталь модели: ${p.enabled ? 'подключена на странице' : 'данные готовы, на странице не подключена'}">⚙ ${esc(p.name)}${p.enabled ? '' : ' · не подключена'}</span>`).join('');
    const sections = [];
    if (c.effects.length) sections.push(`<div class="sec">Эффекты</div><ul>${c.effects.map(effectLine).join('')}</ul>`);
    if (c.opens.length) sections.push(`<div class="sec">Открывает экипаж</div><ul>${c.opens.map(openLine).join('')}</ul>`);
    if (c.abilities.length) sections.push(`<div class="sec">Способности</div><ul>${c.abilities.map(a => `<li><b>${esc(a.name)}</b>: ${esc(a.about)}</li>`).join('')}</ul>`);
    if (c.units && c.units.length) sections.push(`<div class="sec">Найм отрядов</div><div class="units">${c.units.map(esc).join(', ')}</div>`);
    return `<div class="ov-card ${c.ours ? 'ours' : ''} ${c.visible ? '' : 'invisible'}">
      <div class="head">
        ${c.icon ? `<img src="${esc(c.icon)}" alt="">` : '<div class="noicon">?</div>'}
        <div><div class="name">${esc(c.name || c.short)}</div>
        <div class="meta">тир ${c.tier} · ${c.cost} зол. · ${turns(c.turns)}${c.dev ? ` · рост ${c.dev}` : ''}</div></div>
      </div>
      ${parts ? `<div class="parts">${parts}</div>` : ''}
      ${req.length ? `<div class="req">Нужно: ${req.join(', ')}</div>` : ''}
      ${c.text ? `<div class="text">${esc(c.text)}</div>` : ''}
      ${sections.join('')}
      <div class="key">${esc(c.short)}${c.ours ? ' · новая в моде' : ''}${c.visible ? '' : ' · скрыта в игре'}</div>
    </div>`;
}

export async function makeOverview(host) {
    const r = await fetch('/build/overview.json');
    if (!r.ok) { host.innerHTML = `<p class="ov-error">Нет build/web/overview.json: py -3.14 tools/web_export.py --overview</p>`; return; }
    const data = await r.json();
    const total = data.chains.reduce((n, c) => n + c.cards.length, 0);
    const incomplete = data.chains.filter(c => c.missing.length);
    let html = `<h2>Все цепочки построек барки</h2>
      <p class="ov-intro">${data.chains.length} цепочек, ${total} построек. Порядок: корпус, затем цепочки экипажа (пушки, стрелки, купола, люки, гарпун, паб), затем остальные по тиру.
      Зелёным — строки мода, зачёркнуто — эффект игры, выключенный модом. ⚙ — деталь модели, которую приносит постройка.
      ${incomplete.length ? `Неполные данные: ${incomplete.map(c => `«${esc(c.title)}» (${c.missing.map(m => MISSING[m] || m).join(', ')})`).join('; ')}.` : 'Все данные полные.'}
      ${data.units_from_schema ? '' : ' Найм отрядов не показан: нет схемы таблиц.'}</p>`;
    for (const chain of data.chains) {
        const label = chain.hull ? 'Корпус' : chain.crew.length ? chain.crew.join(', ') : chain.title;
        html += `<section class="ov-chain">
          <h3>${esc(label)} <span class="sub">${chain.hull ? '' : esc(chain.title)}${chain.ours ? ' · цепочка мода' : ''}${chain.missing.length ? ` · <span class="bad">неполные данные: ${chain.missing.map(m => MISSING[m] || m).join(', ')}</span>` : ''}</span></h3>
          <div class="ov-row">${chain.cards.map(card).join('<div class="arrow">→</div>')}</div>
        </section>`;
    }
    host.innerHTML = html;
}
