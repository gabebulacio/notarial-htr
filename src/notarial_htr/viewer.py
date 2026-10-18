"""Vista de control en HTML: qué detectó cada algoritmo, página por página.

Genera `data/<colección>/viewer/index.html` y una página HTML por imagen, con los datos
embebidos (se abre directo desde el disco, sin servidor). Lee lo que dejan `htr refine` o
`htr segment` en `layout/debug/` y los manifiestos de preproceso y segmentación.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .manifest import read_jsonl

_CSS = """
:root {
  --bg: #f6f5f2; --panel: #ffffff; --text: #1d1d1b; --muted: #6b6a66; --line: #dcdad4;
  --kept: #1f8a4c; --baseline: #d1342f; --beyond: #d1342f; --strip: #e08a1e;
  --dup: #8a4fd1; --merged: #138a9e; --region: #2f6fd1; --kraken: #8d8b85;
  --edge: #00a3c4; --column: #b0359a; --suspect: #c4361d;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161615; --panel: #201f1d; --text: #ecebe7; --muted: #a09e98; --line: #3a3935;
    --kept: #4cc47e; --baseline: #ff6b5e; --beyond: #ff6b5e; --strip: #f2a646;
    --dup: #b088f0; --merged: #3cc3d6; --region: #6f9ff0; --kraken: #8d8b85;
    --edge: #2ed3f0; --column: #e06acb; --suspect: #ff7a5c;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
       font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--region); }
header { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 8px 16px;
         align-items: center; padding: 10px 16px; background: var(--panel);
         border-bottom: 1px solid var(--line); }
header h1 { font-size: 16px; margin: 0; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { padding: 2px 8px; border: 1px solid var(--line); border-radius: 999px; font-size: 12px;
        color: var(--muted); white-space: nowrap; }
.chip.bad { color: var(--suspect); border-color: var(--suspect); font-weight: 600; }
.nav { display: flex; gap: 8px; margin-left: auto; }
.nav a, .nav button { padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px;
        background: var(--panel); color: var(--text); text-decoration: none; cursor: pointer;
        font: inherit; }
main { display: grid; grid-template-columns: 260px 1fr; gap: 16px; padding: 16px; }
aside { position: sticky; top: 64px; align-self: start; background: var(--panel);
        border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
aside h2 { font-size: 13px; margin: 12px 0 6px; color: var(--muted); text-transform: uppercase;
           letter-spacing: .04em; }
aside h2:first-child { margin-top: 0; }
label.layer { display: flex; align-items: center; gap: 8px; padding: 3px 0; cursor: pointer; }
.sw { width: 14px; height: 14px; border-radius: 3px; flex: none; border: 2px solid; }
.count { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }
.stage { position: relative; background: var(--panel); border: 1px solid var(--line);
         border-radius: 8px; overflow: auto; }
.stage img, .stage svg { display: block; width: 100%; height: auto; }
.stage svg { position: absolute; inset: 0; }
.stage.raw svg { display: none; }
#tip { position: fixed; pointer-events: none; z-index: 10; background: var(--panel);
       border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; font-size: 12px;
       box-shadow: 0 4px 14px rgba(0,0,0,.15); display: none; max-width: 280px; }
.hint { color: var(--muted); font-size: 12px; margin-top: 10px; }
svg .l-bound { stroke-width: 1.5; vector-effect: non-scaling-stroke; }
svg .l-base { fill: none; stroke-width: 2.5; vector-effect: non-scaling-stroke; }
svg .thin { fill: none; stroke-width: 1.5; vector-effect: non-scaling-stroke; }
svg .thick { fill: none; stroke-width: 4; vector-effect: non-scaling-stroke; }
svg text { font: 600 34px system-ui, sans-serif; paint-order: stroke; stroke: var(--panel);
           stroke-width: 6px; }
table { border-collapse: collapse; width: 100%; background: var(--panel); }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--line); text-align: right;
         font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
tr.suspect td:first-child a { color: var(--suspect); font-weight: 600; }
.wrap { padding: 16px; overflow-x: auto; }
@media (max-width: 760px) {
  main { grid-template-columns: 1fr; }
  aside { position: static; }
}
"""

_PAGE_JS = """
const D = DATA;
const NS = 'http://www.w3.org/2000/svg';
const svg = document.getElementById('ov');
const [W, H] = D.size;
svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
const tip = document.getElementById('tip');
const groups = {};
function g(name) {
  if (!groups[name]) { groups[name] = document.createElementNS(NS, 'g'); svg.appendChild(groups[name]); }
  return groups[name];
}
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  parent.appendChild(e); return e;
}
const pts = p => p.map(q => q.join(',')).join(' ');
function hover(e, text) {
  e.addEventListener('mousemove', ev => {
    tip.style.display = 'block'; tip.innerHTML = text;
    tip.style.left = (ev.clientX + 14) + 'px'; tip.style.top = (ev.clientY + 14) + 'px';
  });
  e.addEventListener('mouseleave', () => tip.style.display = 'none');
}
const FATE = {
  beyond_edge: ['beyond', 'Descartado: del otro lado del borde del papel'],
  edge_strip: ['strip', 'Descartado: resto corto en la franja de borde'],
  duplicate: ['dup', 'Descartado: duplicado encimado sobre otro renglón'],
  merged: ['merged', 'Unido a otro renglón partido'],
  kept: ['kraken', 'Kraken (se conservó)'],
};
// Zonas y geometría de las reglas
const [s0, s1] = D.edge_strip_px;
el('rect', {x: 0, y: 0, width: s0, height: H, fill: 'var(--strip)', 'fill-opacity': .10}, g('strip_zone'));
el('rect', {x: s1, y: 0, width: W - s1, height: H, fill: 'var(--strip)', 'fill-opacity': .10}, g('strip_zone'));
for (const [i, x] of (D.column || []).entries()) {
  el('line', {x1: x, y1: 0, x2: x, y2: H, stroke: 'var(--column)', class: 'thin', 'stroke-dasharray': '10 8'}, g('column'));
}
for (const e of D.edges) {
  if (!e) continue;
  const at = y => e.y2 === e.y1 ? (e.x1 + e.x2) / 2 : e.x1 + (y - e.y1) * (e.x2 - e.x1) / (e.y2 - e.y1);
  el('line', {x1: at(0), y1: 0, x2: at(H), y2: H, stroke: 'var(--edge)', class: 'thick', 'stroke-dasharray': '18 10'}, g('edges'));
  el('line', {x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, stroke: 'var(--edge)', class: 'thick'}, g('edges'));
}
for (const r of D.kraken_regions) {
  const p = el('polygon', {points: pts(r.boundary), fill: 'none', stroke: 'var(--kraken)', class: 'thin', 'stroke-dasharray': '6 6'}, g('kraken_regions'));
  hover(p, `<b>Región Kraken</b> ${r.id}<br>${r.kind}`);
}
for (const r of D.regions) {
  const p = el('polygon', {points: pts(r.boundary), fill: 'var(--region)', 'fill-opacity': .05, stroke: 'var(--region)', class: 'thin'}, g('regions'));
  hover(p, `<b>Región</b> ${r.id}<br>${r.kind}`);
}
// Renglones de Kraken, coloreados por la decisión que tomaron las reglas
for (const l of D.kraken_lines) {
  const [key, label] = FATE[l.fate] || FATE.kept;
  const layer = l.fate === 'kept' ? 'kraken_lines' : l.fate;
  const color = `var(--${key})`;
  const p = el('polygon', {points: pts(l.boundary), fill: color, 'fill-opacity': l.fate === 'kept' ? 0 : l.fate === 'merged' ? .08 : .28,
                          stroke: color, class: 'l-bound', 'stroke-dasharray': l.fate === 'kept' ? '4 4' : ''}, g(layer));
  el('polyline', {points: pts(l.baseline), stroke: color, class: 'l-base'}, g(layer));
  hover(p, `<b>${label}</b><br>${l.id}<br>largo ${l.length} px` + (l.merged_into ? `<br>unido a ${l.merged_into}` : ''));
}
// Resultado final
D.lines.forEach((l, i) => {
  const p = el('polygon', {points: pts(l.boundary), fill: 'var(--kept)', 'fill-opacity': .10, stroke: 'var(--kept)', class: 'l-bound'}, g('lines'));
  el('polyline', {points: pts(l.baseline), stroke: 'var(--baseline)', class: 'l-base'}, g('lines'));
  const [x, y] = l.baseline[0];
  el('text', {x: x - 10, y: y - 12, fill: 'var(--kept)', 'text-anchor': 'end'}, g('numbers')).textContent = i + 1;
  hover(p, `<b>Renglón ${i + 1}</b><br>${l.id}`);
});
// Interruptores de capas, recordados entre páginas
const KEY = 'htr-viewer-layers';
let saved = {};
try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
document.querySelectorAll('input[data-layer]').forEach(cb => {
  const name = cb.dataset.layer;
  if (name in saved) cb.checked = saved[name];
  const apply = () => { if (groups[name]) groups[name].style.display = cb.checked ? '' : 'none'; };
  cb.addEventListener('change', () => {
    apply(); saved[name] = cb.checked;
    try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {}
  });
  apply();
  const n = document.querySelector(`[data-count="${name}"]`);
  if (n && groups[name]) n.textContent = groups[name].querySelectorAll('polygon, line').length || '';
});
// Foto original sin rotar (las capas se ocultan porque la geometría es la de la imagen limpia)
const stage = document.getElementById('stage');
const img = document.getElementById('img');
const rawBtn = document.getElementById('raw');
rawBtn.addEventListener('click', () => {
  const raw = stage.classList.toggle('raw');
  img.src = raw ? D.raw_src : D.clean_src;
  rawBtn.textContent = raw ? 'Ver segmentación' : 'Ver foto original';
});
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowLeft' && D.prev) location.href = D.prev;
  if (e.key === 'ArrowRight' && D.next) location.href = D.next;
  if (e.key === 'o') rawBtn.click();
});
"""

_LAYERS = [
    # (capa, etiqueta, variable de color, visible por defecto)
    ("lines", "Renglones finales", "kept", True),
    ("numbers", "Orden de lectura", "kept", True),
    ("regions", "Regiones finales", "region", False),
    ("beyond_edge", "Del otro lado del borde", "beyond", True),
    ("edge_strip", "Franja de borde", "strip", True),
    ("duplicate", "Duplicados", "dup", True),
    ("merged", "Partes unidas", "merged", True),
    ("kraken_lines", "Renglones Kraken (originales)", "kraken", False),
    ("kraken_regions", "Regiones Kraken", "kraken", False),
    ("edges", "Borde del papel detectado", "edge", True),
    ("strip_zone", "Zona de la franja de borde", "strip", False),
    ("column", "Bloque de texto (columna)", "column", False),
]


def _chip(text: str, bad: bool = False) -> str:
    return f'<span class="chip{" bad" if bad else ""}">{html.escape(text)}</span>'


def _page_html(data: dict, pre: dict, prev: str | None, nxt: str | None) -> str:
    st = data["stats"]
    chips = [
        _chip(f"Kraken {st['lines_kraken']} renglones"),
        _chip(f"final {st['lines']}"),
        _chip(f"borde {st['lines_beyond_edge']} · franja "
              f"{st['lines_facing_page'] - st['lines_beyond_edge']}"),
        _chip(f"duplicados {st['lines_duplicate']} · unidos {st['lines_merged']}"),
        _chip("bordes del papel: " + " / ".join(
            ("izq" if i == 0 else "der") + (" sí" if found else " no")
            for i, found in enumerate(st.get("paper_edges", [False, False])))),
        _chip(f"cortos {st['tiny_line_ratio']:.0%}", st["layout_suspect"]),
    ]
    if st["layout_suspect"]:
        chips.append(_chip("revisar segmentación a mano", True))
    if pre:
        skew = (f"rotada {pre['skew_deg']}°" if pre.get("skew_confident")
                else f"sin rotar (estimado {pre.get('skew_estimate')}°, poco confiable)")
        chips.append(_chip(skew))
    layers = "\n".join(
        f'<label class="layer"><input type="checkbox" data-layer="{key}"'
        f'{" checked" if on else ""}><span class="sw" style="border-color:var(--{color});'
        f'background:color-mix(in srgb, var(--{color}) 25%, transparent)"></span>{label}'
        f'<span class="count" data-count="{key}"></span></label>'
        for key, label, color, on in _LAYERS
    )
    payload = json.dumps({**data, "prev": prev, "next": nxt}, ensure_ascii=False)
    nav = "".join([
        f'<a href="{prev}">← anterior</a>' if prev else "",
        '<a href="index.html">índice</a>',
        f'<a href="{nxt}">siguiente →</a>' if nxt else "",
    ])
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{data['page_id']} · Vista de control</title>
<style>{_CSS}</style></head>
<body>
<header>
  <h1>{data['page_id']}</h1>
  <div class="chips">{''.join(chips)}</div>
  <div class="nav"><button id="raw">Ver foto original</button>{nav}</div>
</header>
<main>
  <aside>
    <h2>Capas</h2>
    {layers}
    <p class="hint">Pasá el mouse por un renglón para ver qué regla lo afectó.
    Teclas: ← → cambian de página, <b>o</b> alterna con la foto original.</p>
  </aside>
  <div class="stage" id="stage">
    <img id="img" src="{html.escape(data['clean_src'])}" alt="{data['page_id']}">
    <svg id="ov" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none"></svg>
  </div>
</main>
<div id="tip"></div>
<script>const DATA = {payload};
{_PAGE_JS}</script>
</body></html>
"""


def _index_html(title: str, rows: list[dict]) -> str:
    def row(r: dict) -> str:
        st = r["stats"]
        pre = r.get("pre") or {}
        return (
            f'<tr class="{"suspect" if st["layout_suspect"] else ""}" '
            f'data-suspect="{int(st["layout_suspect"])}">'
            f'<td><a href="{r["page_id"]}.html">{r["page_id"]}</a></td>'
            f'<td>{st["lines_kraken"]}</td><td>{st["lines"]}</td>'
            f'<td>{st["lines_beyond_edge"]}</td>'
            f'<td>{st["lines_facing_page"] - st["lines_beyond_edge"]}</td>'
            f'<td>{st["lines_duplicate"]}</td><td>{st["lines_merged"]}</td>'
            f'<td>{"".join("✓" if e else "·" for e in st.get("paper_edges", []))}</td>'
            f'<td>{st["tiny_line_ratio"]:.0%}</td>'
            f'<td>{pre.get("skew_deg", "")}</td>'
            f'<td>{"revisar" if st["layout_suspect"] else ""}</td></tr>'
        )

    suspect = sum(r["stats"]["layout_suspect"] for r in rows)
    body = "\n".join(row(r) for r in rows)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vista de control</title>
<style>{_CSS}</style></head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
  <div class="chips">{_chip(f"{len(rows)} páginas segmentadas")}{_chip(f"{suspect} a revisar", bool(suspect))}</div>
  <div class="nav"><label><input type="checkbox" id="only"> solo a revisar</label></div>
</header>
<div class="wrap">
<table>
<thead><tr><th>Página</th><th>Kraken</th><th>Final</th><th>Borde</th><th>Franja</th>
<th>Duplic.</th><th>Unidos</th><th>Bordes izq/der</th><th>Cortos</th><th>Rotación °</th><th></th></tr></thead>
<tbody>{body}</tbody>
</table>
</div>
<script>
document.getElementById('only').addEventListener('change', e => {{
  document.querySelectorAll('tbody tr').forEach(tr => {{
    tr.style.display = e.target.checked && tr.dataset.suspect !== '1' ? 'none' : '';
  }});
}});
</script>
</body></html>
"""


def build_viewer(data_dir: Path, title: str, pages: set[str] | None = None) -> Path:
    """Escribe la vista de control y devuelve la ruta del índice."""
    debug_dir = data_dir / "layout" / "debug"
    out = data_dir / "viewer"
    out.mkdir(parents=True, exist_ok=True)
    clean_manifest = data_dir / "clean" / "manifest.jsonl"
    pre = {r["page_id"]: r for r in read_jsonl(clean_manifest)} if clean_manifest.exists() else {}

    files = sorted(debug_dir.glob("p*.json"))
    if pages:
        files = [f for f in files if f.stem[:5] in pages]
    rows = []
    for i, f in enumerate(files):
        data = json.loads(f.read_text(encoding="utf-8"))
        info = pre.get(data["page_id"], {})
        data["clean_src"] = f"../clean/{data['image']}"
        data["raw_src"] = f"../raw/{info['source']}" if info.get("source") else data["clean_src"]
        prev = f"{files[i - 1].stem}.html" if i > 0 else None
        nxt = f"{files[i + 1].stem}.html" if i + 1 < len(files) else None
        (out / f"{data['page_id']}.html").write_text(_page_html(data, info, prev, nxt),
                                                     encoding="utf-8")
        rows.append({"page_id": data["page_id"], "stats": data["stats"], "pre": info})
    index = out / "index.html"
    index.write_text(_index_html(title, rows), encoding="utf-8")
    return index
