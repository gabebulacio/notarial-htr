"""Corrección desde el celular: un renglón por pantalla, se desliza hacia arriba.

Usa la misma API que el editor de escritorio (`/api/pages`, `/api/page/<id>`, `/crop/...`)
y guarda en el mismo formato, así que se pueden alternar los dos sin conflicto.
El orden del feed prioriza lo que más sirve al proyecto: páginas empezadas, después las de
evaluación, después el resto. Las páginas con segmentación sospechosa no entran: se
arreglan en la computadora.
"""

from __future__ import annotations

import html
import json

_INSERTS = ["^", "̄", "[...]", "[tach: ]", "[int: ]", "[rúbrica]", "=", ","]

_CSS = """
:root {
  --bg: #0f0f0e; --card: #1b1a18; --text: #f1efe9; --muted: #a3a098; --line: #34322e;
  --ok: #3fcf7c; --warn: #f2b84b; --bad: #ff6b57; --accent: #6fa3ff; --paper: #fbfaf6;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg: #f3f1ec; --card: #ffffff; --text: #1d1c1a; --muted: #6b6963; --line: #dedbd3;
    --ok: #1f9d55; --warn: #b7791f; --bad: #d23f2c; --accent: #2f6fd1; --paper: #fbfaf6;
  }
}
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
html, body { margin: 0; height: 100%; overflow-x: hidden; background: var(--bg); color: var(--text);
  font: 16px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; overscroll-behavior: none; }
#hud { position: fixed; top: 0; left: 0; right: 0; z-index: 10; padding: 10px 16px 8px;
  padding-top: max(10px, env(safe-area-inset-top));
  background: linear-gradient(var(--bg) 70%, transparent); display: grid; gap: 6px; }
.hrow { display: flex; align-items: center; gap: 10px; font-weight: 700; }
.hrow .sp { flex: 1; }
.pill { padding: 3px 10px; border-radius: 999px; background: var(--card); border: 1px solid var(--line);
  font-size: 14px; font-variant-numeric: tabular-nums; }
#streak.hot { color: var(--warn); border-color: var(--warn); }
.bar { height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; }
.bar > i { display: block; height: 100%; width: 0; background: var(--ok); transition: width .35s ease; }
#feed { height: 100dvh; width: 100%; overflow-y: scroll; overflow-x: hidden;
  scroll-snap-type: y mandatory; }
.card { height: 100dvh; scroll-snap-align: start; scroll-snap-stop: always; display: flex;
  flex-direction: column; justify-content: center; gap: 12px; padding: 86px 16px 24px;
  padding-bottom: max(24px, env(safe-area-inset-bottom)); width: 100%; }
/* En una columna flex los hijos no se achican por debajo de su contenido: la fila de
   botones ensanchaba toda la página */
.card > * { min-width: 0; max-width: 100%; }
.meta { display: flex; justify-content: space-between; color: var(--muted); font-size: 14px; }
.cropwrap { background: var(--paper); border-radius: 12px; overflow-x: auto; padding: 6px; }
.cropwrap img { display: block; width: 100%; height: auto; min-height: 60px; }
.cropwrap.zoom img { width: 220%; max-width: none; }
.pred { font: 15px/1.4 ui-monospace, "Cascadia Mono", monospace; color: var(--muted);
  word-break: break-word; }
.pred .lo { color: var(--bad); text-decoration: underline wavy; text-underline-offset: 3px; }
.pred .mid { color: var(--warn); }
textarea { width: 100%; min-height: 76px; resize: none; padding: 12px; border-radius: 12px;
  border: 1px solid var(--line); background: var(--card); color: var(--text);
  font: 19px/1.35 ui-monospace, "Cascadia Mono", monospace; }
textarea:focus { outline: 2px solid var(--accent); border-color: transparent; }
.ins { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 2px; }
.ins button { flex: none; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--line);
  background: var(--card); color: var(--text); font: 15px ui-monospace, monospace; }
.acts { display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 10px; }
.acts button { padding: 16px 8px; border-radius: 16px; border: 1px solid var(--line);
  background: var(--card); color: var(--text); font: 600 16px system-ui, sans-serif; }
.acts .yes { background: var(--ok); border-color: var(--ok); color: #06210f; font-size: 20px; }
.acts .on { border-color: var(--warn); color: var(--warn); }
.nudge { display: none; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--warn);
  color: var(--warn); font-size: 14px; }
.nudge.show { display: block; }
.card.done { opacity: .5; }
.card.big { text-align: center; align-items: center; }
.card.big h2 { font-size: 30px; margin: 0; }
.card.big p { color: var(--muted); margin: 0; max-width: 30ch; }
.card.big .num { font-size: 64px; font-weight: 800; }
.plus { position: fixed; z-index: 20; font: 800 28px system-ui; color: var(--ok); pointer-events: none;
  animation: up .8s ease-out forwards; }
@keyframes up { to { transform: translateY(-80px); opacity: 0; } }
#toast { position: fixed; left: 16px; right: 16px; bottom: 20px; z-index: 30; padding: 12px;
  border-radius: 12px; background: var(--bad); color: #fff; display: none; text-align: center; }
canvas#fx { position: fixed; inset: 0; z-index: 25; pointer-events: none; }
.hint { color: var(--muted); font-size: 13px; text-align: center; }
@media (prefers-reduced-motion: reduce) { .plus { animation: none; display: none; } }
"""

_JS = """
const INSERTS = %INSERTS%;
const feed = document.getElementById('feed');
const $ = s => document.querySelector(s);
const MILESTONE = 25, BREAK_MS = 30 * 60 * 1000;
let queue = [], pages = {}, loadingNext = false, lastFocus = null;
let session = {done: 0, streak: 0, best: 0, lastAt: 0, start: Date.now(), breakShown: 0};
let stats = {day: '', today: 0, total: 0, best: 0};
try { stats = Object.assign(stats, JSON.parse(localStorage.getItem('htr-m') || '{}')); } catch (e) {}
const today = new Date().toISOString().slice(0, 10);
if (stats.day !== today) { stats.day = today; stats.today = 0; }
function persist() { try { localStorage.setItem('htr-m', JSON.stringify(stats)); } catch (e) {} }

function esc(s) { return s.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])); }
function predHtml(t, confs) {
  return [...t].map((ch, i) => { const c = confs[i] ?? 1;
    const k = c < 0.6 ? 'lo' : c < 0.85 ? 'mid' : ''; return k ? `<span class="${k}">${esc(ch)}</span>` : esc(ch); }).join('');
}
function hud() {
  $('#streak').textContent = `🔥 ${session.streak}`;
  $('#streak').classList.toggle('hot', session.streak >= 10);
  $('#today').textContent = `✓ ${stats.today} hoy`;
  $('#lvl').textContent = `Nivel ${Math.floor(stats.total / MILESTONE) + 1}`;
  $('#xp').style.width = `${(stats.total % MILESTONE) / MILESTONE * 100}%`;
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.style.display = 'block'; setTimeout(() => t.style.display = 'none', 3500); }
function buzz(ms) { try { navigator.vibrate && navigator.vibrate(ms); } catch (e) {} }

// --- confeti ---------------------------------------------------------------------
const fx = $('#fx'), ctx = fx.getContext('2d'); let parts = [];
function confetti(n = 120) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  fx.width = innerWidth; fx.height = innerHeight;
  const colors = ['#3fcf7c', '#f2b84b', '#6fa3ff', '#ff6b57', '#c58cff'];
  for (let i = 0; i < n; i++) parts.push({x: innerWidth / 2, y: innerHeight * .35, vx: (Math.random() - .5) * 14,
    vy: -Math.random() * 13 - 4, s: Math.random() * 6 + 4, c: colors[i % colors.length], r: Math.random() * 6, life: 90});
  requestAnimationFrame(tick);
}
function tick() {
  ctx.clearRect(0, 0, fx.width, fx.height);
  parts = parts.filter(p => p.life-- > 0);
  for (const p of parts) { p.vy += .35; p.x += p.vx; p.y += p.vy; p.r += .2;
    ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c; ctx.fillRect(-p.s / 2, -p.s / 2, p.s, p.s * .6); ctx.restore(); }
  if (parts.length) requestAnimationFrame(tick);
}
function plusOne(el) {
  const r = el.getBoundingClientRect(), s = document.createElement('div');
  s.className = 'plus'; s.textContent = '+1'; s.style.left = (r.left + r.width / 2 - 14) + 'px'; s.style.top = (r.top - 10) + 'px';
  document.body.appendChild(s); setTimeout(() => s.remove(), 900);
}

// --- datos -------------------------------------------------------------------------
async function api(path, opts) {
  const r = await fetch(path, opts); if (!r.ok) throw new Error(r.status); return r.json();
}
async function buildQueue() {
  const ps = await api('/api/pages');
  const usable = ps.filter(p => !p.layout_suspect && p.status !== 'corregida');
  const rank = p => p.status === 'en_curso' ? 0 : p.test ? 1 : 2;
  queue = usable.sort((a, b) => rank(a) - rank(b) || a.page_id.localeCompare(b.page_id)).map(p => p.page_id);
  $('#left').textContent = `${usable.length} páginas por delante`;
}
async function loadNext() {
  if (loadingNext) return; loadingNext = true;
  try {
    while (queue.length) {
      const pid = queue.shift();
      const page = await api(`/api/page/${pid}`);
      pages[pid] = page;
      const pending = page.lines.filter(l => !l.reviewed);
      if (!pending.length) continue;
      feed.appendChild(introCard(page, pending.length));
      pending.forEach(l => feed.appendChild(lineCard(page, l)));
      return;
    }
    if (!feed.querySelector('.end')) feed.appendChild(bigCard('🏁', 'No queda nada en la cola',
      'Las páginas con segmentación sospechosa se revisan en la computadora.', 'end'));
  } catch (e) { toast('No se pudo cargar la página siguiente'); }
  finally { loadingNext = false; }
}
function bigCard(icon, title, text, cls = '') {
  const d = document.createElement('section'); d.className = 'card big ' + cls;
  d.innerHTML = `<div class="num">${icon}</div><h2>${esc(title)}</h2><p>${esc(text)}</p>`; return d;
}
function introCard(page, n) {
  const total = page.lines.length;
  return bigCard('📜', page.page_id + (page.test ? ' · evaluación' : ''),
    `${n} de ${total} renglones por revisar. Deslizá hacia arriba.`);
}
function pageProgress(page) { return page.lines.filter(l => l.reviewed).length; }

function needsNudge(l, text) {
  const ups = (l.prediction.match(/\\^/g) || []).length > (text.match(/\\^/g) || []).length;
  const pun = (l.prediction.match(/[,.;:=]/g) || []).length > (text.match(/[,.;:=]/g) || []).length + 1;
  if (ups) return 'El modelo vio letras voladas (^) que tu texto no tiene. ¿Confirmás?';
  if (pun) return 'El modelo vio más puntuación que tu texto. ¿El original la tiene?';
  return null;
}

function lineCard(page, l) {
  const i = page.lines.indexOf(l), d = document.createElement('section');
  d.className = 'card';
  d.innerHTML = `
    <div class="meta"><span>${page.page_id} · renglón ${i + 1}/${page.lines.length}</span><span>${Math.round(l.mean_conf * 100)}%</span></div>
    ${l.has_crop ? `<div class="cropwrap"><img loading="lazy" alt="renglón" src="/crop/${page.page_id}/${encodeURIComponent(l.id)}.png"></div>` : ''}
    <div class="pred">${predHtml(l.prediction, l.char_conf)}</div>
    <textarea spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off"></textarea>
    <div class="ins">${INSERTS.map((s, k) => `<button data-k="${k}">${s === '\\u0304' ? '◌̄' : esc(s)}</button>`).join('')}<button data-reset>↺</button></div>
    <div class="nudge"></div>
    <div class="acts"><button class="doubt">🤔 Dudoso</button><button class="nt">🚫 No es texto</button><button class="yes">✓ Listo</button></div>`;
  const ta = d.querySelector('textarea'), nudge = d.querySelector('.nudge'), dbt = d.querySelector('.doubt');
  ta.value = l.text; dbt.classList.toggle('on', l.doubtful);
  ta.addEventListener('focus', () => lastFocus = ta);
  ta.addEventListener('input', () => { l.text = ta.value; nudge.classList.remove('show'); });
  d.querySelector('.cropwrap')?.addEventListener('click', e => e.currentTarget.classList.toggle('zoom'));
  d.querySelectorAll('.ins [data-k]').forEach(b => b.addEventListener('mousedown', e => e.preventDefault()));
  d.querySelectorAll('.ins [data-k]').forEach(b => b.addEventListener('click', () => {
    const s = INSERTS[+b.dataset.k], a = ta.selectionStart ?? ta.value.length, z = ta.selectionEnd ?? a;
    ta.setRangeText(s, a, z, 'end'); if (s.endsWith(': ]')) ta.setSelectionRange(a + s.length - 1, a + s.length - 1);
    ta.focus(); ta.dispatchEvent(new Event('input'));
  }));
  d.querySelector('[data-reset]').addEventListener('click', () => { ta.value = l.prediction; ta.dispatchEvent(new Event('input')); });
  dbt.addEventListener('click', () => { l.doubtful = !l.doubtful; dbt.classList.toggle('on', l.doubtful); buzz(8); });
  d.querySelector('.nt').addEventListener('click', () => accept(page, l, d, true));
  d.querySelector('.yes').addEventListener('click', e => {
    const msg = !l.not_text && !nudge.classList.contains('show') && needsNudge(l, ta.value);
    if (msg) { nudge.textContent = msg + ' Tocá ✓ de nuevo para seguir.'; nudge.classList.add('show'); buzz([10, 40, 10]); return; }
    accept(page, l, d, false, e.currentTarget);
  });
  return d;
}

async function accept(page, l, card, notText, btn) {
  l.not_text = notText; l.reviewed = true; l.text = card.querySelector('textarea').value;
  const done = pageProgress(page) === page.lines.length;
  const body = {status: done ? 'corregida' : 'en_curso',
    lines: page.lines.map(x => ({id: x.id, text: x.text, doubtful: x.doubtful, not_text: x.not_text, reviewed: x.reviewed}))};
  try { await api(`/api/page/${page.page_id}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); }
  catch (e) { l.reviewed = false; toast('No se guardó: ¿la computadora sigue prendida?'); return; }
  const now = Date.now();
  session.streak = now - session.lastAt < 3 * 60 * 1000 ? session.streak + 1 : 1;
  session.lastAt = now; session.done++; stats.today++; stats.total++;
  stats.best = Math.max(stats.best, session.streak); persist();
  buzz(12); if (btn) plusOne(btn); hud(); card.classList.add('done');
  let next = card.nextElementSibling;
  if (done) {
    const c = bigCard('🎉', `${page.page_id} completa`, `${page.lines.length} renglones listos para entrenar el modelo.`);
    card.after(c); next = c; confetti(160); buzz([20, 60, 20, 60, 40]);
  } else if (stats.total % MILESTONE === 0) {
    const c = bigCard('⭐', `Nivel ${stats.total / MILESTONE + 1}`, `${stats.total} renglones revisados en total. Racha récord: ${stats.best}.`);
    card.after(c); next = c; confetti(90);
  }
  if (now - session.start > BREAK_MS * (session.breakShown + 1)) {
    session.breakShown++;
    const c = bigCard('☕', 'Pausa de 5 minutos', 'Con la vista cansada se leen mal las abreviaturas. Mirá algo lejos y volvé.');
    (next || card).after(c); next = c;
  }
  if (next) next.scrollIntoView({behavior: 'smooth'});
  if (feed.querySelectorAll('.card:not(.done)').length < 4) loadNext();
}

feed.addEventListener('scroll', () => {
  if (feed.scrollTop + feed.clientHeight * 3 > feed.scrollHeight) loadNext();
}, {passive: true});

(async () => {
  hud();
  try {
    await buildQueue(); await loadNext();
    // #3 salta a la tarjeta 3 (para revisar el diseño sin deslizar)
    const n = +location.hash.slice(1);
    if (n) setTimeout(() => { if (feed.children[n]) feed.scrollTop = feed.children[n].offsetTop; }, 400);
  }
  catch (e) { feed.appendChild(bigCard('⚠️', 'Sin conexión', 'Revisá que la computadora tenga el editor abierto y que estés en la misma Wi-Fi.')); }
})();
"""


def mobile_html(title: str) -> str:
    js = _JS.replace("%INSERTS%", json.dumps(_INSERTS, ensure_ascii=False))
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f0f0e">
<title>Corregir · {html.escape(title)}</title><style>{_CSS}</style></head><body>
<div id="hud">
  <div class="hrow"><span class="pill" id="streak">🔥 0</span><span class="pill" id="today">✓ 0 hoy</span>
    <span class="sp"></span><span class="pill" id="lvl">Nivel 1</span></div>
  <div class="bar"><i id="xp"></i></div>
</div>
<main id="feed">
  <section class="card big"><div class="num">✍️</div><h2>{html.escape(title)}</h2>
    <p id="left">Cargando…</p><p class="hint">Corregí el texto, tocá ✓ y deslizá. Tocá la imagen para agrandarla.</p></section>
</main>
<canvas id="fx"></canvas><div id="toast"></div>
<script>{js}</script></body></html>"""
