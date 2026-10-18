"""HTML del editor de transcripciones (sin dependencias externas)."""

from __future__ import annotations

import html
import json

_CSS = """
:root {
  --bg: #f6f5f2; --panel: #ffffff; --text: #1d1d1b; --muted: #6b6a66; --line: #dcdad4;
  --accent: #2f6fd1; --low: #c4361d; --ok: #1f8a4c; --warn: #b7791f; --field: #fbfaf8;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161615; --panel: #201f1d; --text: #ecebe7; --muted: #a09e98; --line: #3a3935;
    --accent: #6f9ff0; --low: #ff7a5c; --ok: #4cc47e; --warn: #f2b84b; --field: #262522;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
       font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--accent); }
header { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 8px 14px;
         align-items: center; padding: 10px 16px; background: var(--panel);
         border-bottom: 1px solid var(--line); }
header h1 { font-size: 16px; margin: 0; }
.spacer { flex: 1; }
button, select, .btn { padding: 5px 11px; border: 1px solid var(--line); border-radius: 6px;
         background: var(--panel); color: var(--text); font: inherit; cursor: pointer;
         text-decoration: none; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.saved { color: var(--muted); font-size: 13px; min-width: 120px; }
.saved.dirty { color: var(--warn); }
.saved.err { color: var(--low); }
main { display: grid; grid-template-columns: minmax(0, 1fr) 270px; gap: 16px; padding: 16px; }
aside { position: sticky; top: 104px; align-self: start; background: var(--panel);
        border: 1px solid var(--line); border-radius: 8px; padding: 12px; font-size: 13px; }
aside h2 { font-size: 12px; margin: 10px 0 6px; color: var(--muted); text-transform: uppercase;
           letter-spacing: .04em; }
aside h2:first-child { margin-top: 0; }
aside code { background: var(--field); padding: 0 4px; border-radius: 3px; }
aside dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; }
aside dt { font-family: ui-monospace, monospace; }
aside dd { margin: 0; color: var(--muted); }
.keys { display: flex; flex-wrap: wrap; gap: 6px; }
.keys button { font-family: ui-monospace, monospace; padding: 4px 8px; }
.line { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
        padding: 10px 12px; margin-bottom: 10px; }
.line.focus { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 25%, transparent); }
.line.doubt { border-left: 4px solid var(--warn); }
.line.notext { opacity: .45; }
.line.notext input.txt { text-decoration: line-through; }
.line.edited .num { color: var(--ok); }
.row { display: flex; align-items: center; gap: 10px; }
.num { font-weight: 700; color: var(--muted); min-width: 28px; font-variant-numeric: tabular-nums; }
.crop { display: block; max-width: 100%; max-height: 140px; margin: 6px 0; border-radius: 4px;
        background: #fff; }
.pred { font-family: ui-monospace, "Cascadia Mono", monospace; font-size: 14px; color: var(--muted);
        white-space: pre-wrap; word-break: break-word; }
.pred .lo { color: var(--low); text-decoration: underline wavy; text-underline-offset: 3px; }
.pred .mid { color: var(--warn); }
input.txt { width: 100%; padding: 8px 10px; font: 17px/1.4 ui-monospace, "Cascadia Mono", monospace;
            background: var(--field); color: var(--text); border: 1px solid var(--line);
            border-radius: 6px; margin-top: 6px; }
input.txt:focus { outline: none; border-color: var(--accent); }
.meta { margin-left: auto; display: flex; gap: 10px; align-items: center; color: var(--muted);
        font-size: 13px; }
.meta label { display: flex; gap: 4px; align-items: center; cursor: pointer; }
table { border-collapse: collapse; width: 100%; background: var(--panel); }
th, td { padding: 7px 10px; border-bottom: 1px solid var(--line); text-align: right;
         font-variant-numeric: tabular-nums; }
th:first-child, td:first-child, th.l, td.l { text-align: left; }
th { cursor: pointer; user-select: none; }
.st { padding: 1px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--line); }
.st.corregida { color: var(--ok); border-color: var(--ok); }
.st.en_curso { color: var(--warn); border-color: var(--warn); }
.wrap { padding: 16px; overflow-x: auto; }
.chip { padding: 2px 8px; border: 1px solid var(--line); border-radius: 999px; font-size: 12px;
        color: var(--muted); }
.chip.test { color: var(--accent); border-color: var(--accent); }
.evalbar { flex-basis: 100%; display: flex; flex-wrap: wrap; gap: 4px 22px; align-items: center;
           font-size: 13px; color: var(--muted); padding-top: 8px; border-top: 1px solid var(--line); }
.evalbar .grp { display: flex; gap: 8px; align-items: center; font-variant-numeric: tabular-nums; }
.evalbar .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.evalbar b { color: var(--text); font-weight: 600; }
.evalbar .hint { font-size: 12px; }
.meter { width: 64px; height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; }
.meter i { display: block; height: 100%; background: var(--accent); }
@media (max-width: 860px) { main { grid-template-columns: 1fr; } aside { position: static; } }
"""

_EVAL_JS = """
function pct(x) { return x == null ? '—' : (x * 100).toFixed(1) + '%'; }
async function loadScores(pid) {
  const el = document.getElementById('evalbar');
  try {
    const s = await (await fetch(pid ? `/api/scores/${pid}` : '/api/scores')).json();
    const t = s.test, tr = s.train, done = s.test_total ? t.pages / s.test_total : 0;
    let h = `<span class="grp"><span class="lbl">Evaluación</span>
        ${t.lines ? `CER <b>${pct(t.cer)}</b> WER <b>${pct(t.wer)}</b>` : 'sin páginas corregidas'}
        <span class="meter" title="páginas de evaluación corregidas"><i style="width:${(done * 100).toFixed(0)}%"></i></span>
        ${t.pages}/${s.test_total} págs · ${t.lines} renglones</span>
      <span class="grp"><span class="lbl">Entrenamiento</span>
        ${tr.lines ? `CER <b>${pct(tr.cer)}</b> WER <b>${pct(tr.wer)}</b>` : 'sin páginas corregidas'}
        · ${tr.pages} págs · ${tr.lines} renglones</span>`;
    if (s.page) {
      const partial = s.page.status !== 'corregida';
      h += `<span class="grp"><span class="lbl">Esta página</span>
        CER <b>${pct(s.page.cer)}</b> WER <b>${pct(s.page.wer)}</b>
        ${partial ? '<span class="hint" title="Los renglones sin revisar cuentan como acertados; la página entra en los totales al marcarla corregida">(parcial)</span>' : ''}</span>`;
    }
    el.innerHTML = h;
  } catch (e) { el.textContent = 'no se pudieron calcular las métricas'; }
}
"""

_NORMS = """
<h2>Normas (capa diplomática)</h2>
<dl>
  <dt>q^e</dt><dd>letras voladas entre <code>^</code></dd>
  <dt>an̄s</dt><dd>lineta: signo combinante sobre la letra</dd>
  <dt>[...]</dt><dd>tramo ilegible; <code>[..3..]</code> letras estimadas</dd>
  <dt>[tach: x]</dt><dd>tachado</dd>
  <dt>[int: x]</dt><dd>agregado entre renglones</dd>
  <dt>[rúbrica]</dt><dd>rúbrica sin texto</dd>
</dl>
<p>Ortografía, mayúsculas, uniones y puntuación tal cual el original. Nombres propios:
lo que se ve, sin modernizar. Si dudás, marcá <b>dudoso</b>. Si el renglón es un pliegue,
una mancha o un resto de otra página, marcá <b>no es texto</b>: queda fuera del entrenamiento
y de la medición.</p>
"""

_INSERTS = ["^", "̄", "[...]", "[tach: ]", "[int: ]", "[rúbrica]", "=", "ꝗ", "ſ"]

_EDITOR_JS = """
const PID = %PID%;
const INSERTS = %INSERTS%;
const box = document.getElementById('lines');
const savedEl = document.getElementById('saved');
const statusSel = document.getElementById('status');
let page, dirty = false, timer = null, lastFocus = null;

function esc(s) { return s.replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c])); }
function predHtml(text, confs) {
  return [...text].map((ch, i) => {
    const c = confs[i] ?? 1;
    const cls = c < 0.6 ? 'lo' : c < 0.85 ? 'mid' : '';
    return cls ? `<span class="${cls}" title="${(c * 100).toFixed(0)}%">${esc(ch)}</span>` : esc(ch);
  }).join('');
}
function setSaved(text, cls = '') { savedEl.textContent = text; savedEl.className = 'saved ' + cls; }
function markDirty() { dirty = true; setSaved('cambios sin guardar', 'dirty'); clearTimeout(timer); timer = setTimeout(save, 1500); }

async function load() {
  page = await (await fetch(`/api/page/${PID}`)).json();
  statusSel.value = page.status === 'pendiente' ? 'en_curso' : page.status;
  box.innerHTML = '';
  page.lines.forEach((l, i) => {
    const d = document.createElement('div');
    d.className = 'line' + (l.doubtful ? ' doubt' : '') + (l.edited ? ' edited' : '') + (l.not_text ? ' notext' : '');
    d.innerHTML = `
      <div class="row"><span class="num">${i + 1}</span>
        <span class="pred">${predHtml(l.prediction, l.char_conf)}</span>
        <div class="meta"><span>${(l.mean_conf * 100).toFixed(0)}%</span>
          <label><input type="checkbox" class="doubt"> dudoso</label>
          <label><input type="checkbox" class="notext"> no es texto</label>
          <button class="copy" title="Volver a la lectura del modelo">↺</button></div></div>
      ${l.has_crop ? `<img class="crop" loading="lazy" src="/crop/${PID}/${encodeURIComponent(l.id)}.png" alt="renglón ${i + 1}">` : ''}
      <input class="txt" spellcheck="false" autocomplete="off">`;
    const inp = d.querySelector('.txt'), cb = d.querySelector('.doubt');
    const nt = d.querySelector('input.notext');
    inp.value = l.text; cb.checked = l.doubtful; nt.checked = l.not_text;
    inp.addEventListener('input', () => { l.text = inp.value; markDirty(); });
    inp.addEventListener('focus', () => { lastFocus = inp; document.querySelectorAll('.line.focus').forEach(x => x.classList.remove('focus')); d.classList.add('focus'); });
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === 'ArrowDown') { e.preventDefault(); focusLine(i + (e.shiftKey ? -1 : 1)); }
      if (e.key === 'ArrowUp') { e.preventDefault(); focusLine(i - 1); }
    });
    cb.addEventListener('change', () => { l.doubtful = cb.checked; d.classList.toggle('doubt', cb.checked); markDirty(); });
    nt.addEventListener('change', () => { l.not_text = nt.checked; d.classList.toggle('notext', nt.checked); markDirty(); });
    d.querySelector('.copy').addEventListener('click', () => { inp.value = l.prediction; l.text = l.prediction; markDirty(); inp.focus(); });
    box.appendChild(d);
  });
  setSaved(page.status === 'pendiente' ? 'sin correcciones todavía' : 'guardado');
  document.getElementById('testchip').hidden = !page.test;
  focusLine(0);
}
function focusLine(i) {
  const inputs = box.querySelectorAll('.txt');
  if (i < 0 || i >= inputs.length) return;
  inputs[i].focus(); inputs[i].scrollIntoView({block: 'center', behavior: 'smooth'});
}
async function save(status) {
  clearTimeout(timer);
  const body = {status: status || statusSel.value, lines: page.lines.map(l => ({id: l.id, text: l.text, doubtful: l.doubtful, not_text: l.not_text}))};
  try {
    const r = await fetch(`/api/page/${PID}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const j = await r.json();
    if (!j.ok) throw new Error(j.error);
    dirty = false; statusSel.value = j.status;
    setSaved(`guardado · ${j.edited} renglones editados`);
    page.lines.forEach((l, i) => box.children[i].classList.toggle('edited', l.text !== l.prediction));
    loadScores(PID);
  } catch (e) { setSaved('error al guardar: ' + e.message, 'err'); }
}
document.getElementById('done').addEventListener('click', () => save('corregida'));
statusSel.addEventListener('change', () => save());
document.querySelectorAll('[data-ins]').forEach(b => b.addEventListener('mousedown', e => {
  e.preventDefault();
  const inp = lastFocus; if (!inp) return;
  const s = INSERTS[+b.dataset.ins], a = inp.selectionStart, z = inp.selectionEnd;
  inp.setRangeText(s, a, z, 'end');
  if (s.endsWith(': ]')) inp.setSelectionRange(a + s.length - 1, a + s.length - 1);
  inp.dispatchEvent(new Event('input'));
}));
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); }
  if (e.altKey && e.key === 'ArrowRight' && NAV.next) location.href = NAV.next;
  if (e.altKey && e.key === 'ArrowLeft' && NAV.prev) location.href = NAV.prev;
});
window.addEventListener('beforeunload', e => { if (dirty) { save(); e.preventDefault(); } });
let NAV = {};
fetch('/api/pages').then(r => r.json()).then(ps => {
  const ids = ps.map(p => p.page_id), i = ids.indexOf(PID);
  NAV = {prev: i > 0 ? `/p/${ids[i - 1]}` : null, next: i + 1 < ids.length ? `/p/${ids[i + 1]}` : null};
  if (NAV.prev) document.getElementById('prev').href = NAV.prev; else document.getElementById('prev').hidden = true;
  if (NAV.next) document.getElementById('next').href = NAV.next; else document.getElementById('next').hidden = true;
});
load();
loadScores(PID);
"""

_INDEX_JS = """
let rows = [], key = 'mean_conf', asc = true;
const tb = document.querySelector('tbody');
function render() {
  const only = document.getElementById('pend').checked;
  const list = rows.filter(r => !only || r.status !== 'corregida')
    .sort((a, b) => ((a[key] ?? 0) > (b[key] ?? 0) ? 1 : -1) * (asc ? 1 : -1));
  tb.innerHTML = list.map(r => `<tr>
    <td><a href="/p/${r.page_id}">${r.page_id}</a>${r.test ? ' <span class="chip test" title="página de evaluación: no se usa para entrenar">eval</span>' : ''}</td>
    <td class="l"><span class="st ${r.status}">${r.status.replace('_', ' ')}</span></td>
    <td>${r.lines}</td><td>${r.edited}</td>
    <td>${r.mean_conf == null ? '' : (r.mean_conf * 100).toFixed(1) + '%'}</td>
    <td>${r.low_conf_lines}</td><td>${r.layout_suspect ? 'revisar' : ''}</td></tr>`).join('');
  const done = rows.filter(r => r.status === 'corregida').length;
  document.getElementById('prog').textContent = `${done} de ${rows.length} corregidas`;
}
document.querySelectorAll('th[data-k]').forEach(th => th.addEventListener('click', () => {
  asc = key === th.dataset.k ? !asc : true; key = th.dataset.k; render();
}));
document.getElementById('pend').addEventListener('change', render);
fetch('/api/pages').then(r => r.json()).then(d => { rows = d; render(); });
loadScores();
"""


def index_html(title: str) -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corrección · {html.escape(title)}</title><style>{_CSS}</style></head><body>
<header><h1>{html.escape(title)}</h1><span class="chip" id="prog"></span><span class="spacer"></span>
<label><input type="checkbox" id="pend"> ocultar corregidas</label>
<div class="evalbar" id="evalbar"></div></header>
<div id="lan" hidden style="margin:16px;padding:14px;border:1px solid var(--line);border-radius:8px;background:var(--panel);gap:16px;align-items:center;flex-wrap:wrap">
<div id="qr" style="background:#fff;padding:8px;border-radius:6px"></div>
<div><b>Corregir desde el celular</b><br><span class="saved">Escaneá el código con la cámara (misma Wi-Fi).
La clave cambia cada vez que se arranca el editor; no compartas el enlace.</span><br>
<code id="lanurl" style="word-break:break-all"></code></div></div>
<div class="wrap"><table><thead><tr>
<th data-k="page_id">Página</th><th class="l" data-k="status">Estado</th><th data-k="lines">Renglones</th>
<th data-k="edited">Editados</th><th data-k="mean_conf">Confianza media</th>
<th data-k="low_conf_lines">Renglones dudosos</th><th data-k="layout_suspect">Segmentación</th>
</tr></thead><tbody></tbody></table>
<p class="saved">Ordenado por confianza: las páginas donde el modelo duda más arriba.</p></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script>{_EVAL_JS}{_INDEX_JS}
fetch('/api/lan').then(r => r.json()).then(d => {{
  if (!d.url) return;
  const box = document.getElementById('lan'); box.hidden = false; box.style.display = 'flex';
  document.getElementById('lanurl').textContent = d.url;
  if (window.QRCode) new QRCode(document.getElementById('qr'), {{text: d.url, width: 168, height: 168}});
}});
</script></body></html>"""


def editor_html(pid: str, title: str) -> str:
    keys = "".join(
        f'<button data-ins="{i}" title="insertar">{html.escape(s if s != chr(0x304) else "◌̄")}</button>'
        for i, s in enumerate(_INSERTS))
    js = (_EDITOR_JS.replace("%PID%", json.dumps(pid))
          .replace("%INSERTS%", json.dumps(_INSERTS, ensure_ascii=False)))
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{pid} · Corrección</title><style>{_CSS}</style></head><body>
<header><h1>{pid}</h1>
<span class="chip test" id="testchip" hidden title="No se usa para entrenar: mide el error real">página de evaluación</span>
<span class="saved" id="saved"></span><span class="spacer"></span>
<select id="status"><option value="en_curso">en curso</option><option value="corregida">corregida</option></select>
<button class="primary" id="done">Marcar corregida</button>
<a class="btn" id="prev">← anterior</a><a class="btn" href="/">páginas</a><a class="btn" id="next">siguiente →</a>
<div class="evalbar" id="evalbar"></div>
</header>
<main><div id="lines"></div>
<aside><h2>Insertar</h2><div class="keys">{keys}</div>
{_NORMS}
<h2>Teclado</h2>
<dl><dt>Enter / ↓</dt><dd>renglón siguiente</dd><dt>Shift+Enter / ↑</dt><dd>anterior</dd>
<dt>Ctrl+S</dt><dd>guardar (también se guarda solo)</dd><dt>Alt+← →</dt><dd>otra página</dd></dl>
<p>Debajo del número va la lectura del modelo: en <span style="color:var(--low)">rojo</span>
lo que tiene menos de 60 % de confianza, en <span style="color:var(--warn)">ámbar</span> menos de 85 %.</p>
</aside></main>
<script>{_EVAL_JS}{js}</script></body></html>"""
