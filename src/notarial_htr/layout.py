"""Segmentación de regiones y líneas base con Kraken, más reglas propias para fotos de
libros abiertos.

Se guardan dos versiones por página: `layout/kraken/pXXXX.xml` con la salida de Kraken
sin tocar (para auditar) y `layout/pXXXX.xml` filtrada, que es la que usan las etapas
siguientes. Las reglas trabajan solo sobre geometría y no dependen de Kraken, así se
pueden probar sin el modelo.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry import Point as ShapelyPoint
from shapely.ops import unary_union

from .config import LayoutConfig
from .manifest import read_jsonl, write_jsonl

Point = tuple[int, int]


@dataclass
class Line:
    """Vista mínima de un renglón: lo que necesitan las reglas geométricas."""
    id: str
    baseline: list[Point]
    boundary: list[Point]

    @property
    def x0(self) -> float:
        return min(p[0] for p in self.baseline)

    @property
    def x1(self) -> float:
        return max(p[0] for p in self.baseline)

    @property
    def length(self) -> float:
        b = np.asarray(self.baseline, float)
        return float(np.linalg.norm(np.diff(b, axis=0), axis=1).sum())

    def y_at_start(self) -> float:
        return float(min(self.baseline, key=lambda p: p[0])[1])

    def y_at_end(self) -> float:
        return float(max(self.baseline, key=lambda p: p[0])[1])


def text_column(lines: list[Line], long_frac: float = 0.4) -> tuple[float, float] | None:
    """Extensión horizontal del bloque principal, a partir de los renglones largos."""
    if not lines:
        return None
    longest = max(line.length for line in lines)
    long_lines = [line for line in lines if line.length >= long_frac * longest]
    x0 = float(np.percentile([line.x0 for line in long_lines], 10))
    x1 = float(np.percentile([line.x1 for line in long_lines], 90))
    return x0, x1


@dataclass(frozen=True)
class Edge:
    """Borde del papel como recta casi vertical, en píxeles de la imagen completa."""
    x1: float
    y1: float
    x2: float
    y2: float

    def x_at(self, y: float) -> float:
        if self.y2 == self.y1:
            return (self.x1 + self.x2) / 2
        return self.x1 + (y - self.y1) * (self.x2 - self.x1) / (self.y2 - self.y1)


def _robust_column(lines: list[Line], long_frac: float = 0.4) -> tuple[float, float] | None:
    # Mediana en vez de percentiles extremos: algunos renglones vienen estirados hasta el
    # borde porque Kraken los pegó a restos de la otra página
    if not lines:
        return None
    longest = max(line.length for line in lines)
    long_lines = [line for line in lines if line.length >= long_frac * longest]
    return (float(np.median([line.x0 for line in long_lines])),
            float(np.median([line.x1 for line in long_lines])))


def _brightness_step(small: np.ndarray, e: Edge, scale: float, offset_frac: float = 0.015,
                     samples: int = 20) -> float:
    """Diferencia de brillo mediana entre ambos lados de un segmento (imagen reducida).

    Un borde de papel separa la hoja de la sombra, el canto o la otra página: hay salto de
    brillo. Una regla trazada con tinta o un pliegue tienen el mismo papel a los dos lados.
    """
    h, w = small.shape
    d = max(3, int(w * offset_frac))
    half = max(2, d // 2)
    diffs = []
    for t in np.linspace(0.1, 0.9, samples):
        y = int((e.y1 + t * (e.y2 - e.y1)) * scale)
        x = int((e.x1 + t * (e.x2 - e.x1)) * scale)
        y0, y1 = max(0, y - half), min(h, y + half)
        a = small[y0:y1, max(0, x - d - half):max(0, x - d + half)]
        b = small[y0:y1, min(w, x + d - half):min(w, x + d + half)]
        if a.size and b.size:
            diffs.append(abs(float(np.median(a)) - float(np.median(b))))
    return float(np.median(diffs)) if diffs else 0.0


def paper_edges(gray: np.ndarray, lines: list[Line], max_tilt: float = 15.0,
                min_len_frac: float = 0.2,
                min_step: float = 12.0) -> tuple[Edge | None, Edge | None]:
    """Busca el borde izquierdo y derecho de la hoja fotografiada.

    Detecta segmentos rectos casi verticales (Canny + Hough) con salto de brillo entre
    ambos lados, y se queda, de cada lado, con el más cercano al bloque de texto que esté
    afuera de él. Los trazos alineados de la escritura caen dentro del bloque y no compiten.
    """
    column = _robust_column(lines)
    if column is None:
        return None, None
    scale = 800 / gray.shape[1]
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h = small.shape[0]
    edges = cv2.Canny(cv2.GaussianBlur(small, (7, 7), 0), 30, 90)
    found = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=60,
                            minLineLength=int(h * min_len_frac), maxLineGap=int(h * 0.03))
    if found is None:
        return None, None
    segs = []
    for x1, y1, x2, y2 in found.reshape(-1, 4):
        if math.degrees(math.atan2(abs(x2 - x1), abs(y2 - y1))) > max_tilt:
            continue
        e = Edge(x1 / scale, y1 / scale, x2 / scale, y2 / scale)
        if _brightness_step(small, e, scale) >= min_step:
            segs.append(e)
    margin = 0.01 * gray.shape[1]

    def mid(e: Edge) -> float:
        return (e.x1 + e.x2) / 2

    left = [e for e in segs if max(e.x1, e.x2) < column[0] - margin]
    right = [e for e in segs if min(e.x1, e.x2) > column[1] + margin]
    return (max(left, key=mid) if left else None, min(right, key=mid) if right else None)


def split_beyond_edges(lines: list[Line], left: Edge | None, right: Edge | None,
                       max_length: float = math.inf) -> tuple[list[Line], list[Line]]:
    """Descarta los renglones cortos cuyo centro cae del otro lado del borde del papel.

    Los restos de la página enfrentada son cortos porque esa página casi no se ve; un
    renglón largo del otro lado indica que el borde detectado está mal, y se conserva.
    """
    kept, dropped = [], []
    for line in lines:
        y = float(np.mean([p[1] for p in line.baseline]))
        cx = float(np.mean([p[0] for p in line.baseline]))
        out = (left is not None and cx < left.x_at(y)) or (right is not None and cx > right.x_at(y))
        (dropped if out and line.length < max_length else kept).append(line)
    return kept, dropped


def split_facing_page(lines: list[Line], width: int, edge_frac: float,
                      short_frac: float) -> tuple[list[Line], list[Line]]:
    """Separa los renglones que pertenecen a la página enfrentada o al canto.

    Un renglón se descarta si cae entero en la franja de borde de la imagen y es corto
    comparado con el bloque principal. No se exige que quede fuera del bloque: en muchas
    fotos el texto llega casi al borde y los restos de la otra página arrancan pegados.
    Las notas marginales de la propia página quedan entre la franja y el bloque.
    Pendiente: detectar el borde físico del papel en vez de usar una franja fija.
    """
    column = text_column(lines)
    if column is None:
        return lines, []
    col_width = column[1] - column[0]
    left_edge, right_edge = width * edge_frac, width * (1 - edge_frac)
    kept, dropped = [], []
    for line in lines:
        in_edge = line.x1 <= left_edge or line.x0 >= right_edge
        short = line.length < short_frac * col_width
        (dropped if in_edge and short else kept).append(line)
    return kept, dropped


def drop_contained_lines(lines: list[Line], min_inside: float = 0.6) -> tuple[list[Line], int]:
    """Quita renglones cortos que Kraken detectó dos veces, encimados sobre uno más largo:
    si la mayor parte de su línea base cae dentro del contorno del otro, sobra."""
    polys = {line.id: Polygon(line.boundary).buffer(0) for line in lines}
    dropped = set()
    for b in lines:
        pts = [ShapelyPoint(p) for p in b.baseline]
        for a in lines:
            if a is b or a.id in dropped or a.length <= b.length:
                continue
            inside = sum(polys[a.id].contains(pt) for pt in pts) / len(pts)
            if inside >= min_inside:
                dropped.add(b.id)
                break
    return [line for line in lines if line.id not in dropped], len(dropped)


def _merge_boundaries(a: list[Point], b: list[Point], gap: float) -> list[Point]:
    union = unary_union([Polygon(a).buffer(0), Polygon(b).buffer(0)])
    if isinstance(union, MultiPolygon):
        # Cierre morfológico para unir los dos trozos por el hueco entre ellos
        r = gap / 2 + 2
        union = union.buffer(r).buffer(-r)
    if isinstance(union, MultiPolygon):
        union = union.convex_hull
    return [(int(x), int(y)) for x, y in union.exterior.coords[:-1]]


def merge_split_lines(lines: list[Line], y_tol: float, gap_tol: float,
                      log: dict[str, str] | None = None) -> tuple[list[Line], int]:
    """Une renglones que Kraken partió en dos: uno empieza donde termina el otro, a la
    misma altura. Devuelve los renglones y la cantidad de uniones hechas; si se pasa
    `log`, anota qué renglón quedó absorbido por cuál."""
    lines = list(lines)
    merges = 0
    changed = True
    while changed:
        changed = False
        for a in lines:
            candidates = [
                b for b in lines
                if b is not a
                and b.x0 >= a.x1 - gap_tol * 0.25
                and b.x0 - a.x1 <= gap_tol
                and abs(b.y_at_start() - a.y_at_end()) <= y_tol
            ]
            if not candidates:
                continue
            b = min(candidates, key=lambda c: c.x0 - a.x1)
            gap = max(0.0, b.x0 - a.x1)
            merged = Line(a.id, a.baseline + b.baseline, _merge_boundaries(a.boundary, b.boundary, gap))
            lines = [merged if line is a else line for line in lines if line is not b]
            if log is not None:
                log[b.id] = a.id
                for k, v in log.items():
                    if v == b.id:
                        log[k] = a.id
            merges += 1
            changed = True
            break
    return lines, merges


def line_spacing(lines: list[Line]) -> float:
    """Interlineado típico: mediana de la diferencia de altura entre renglones vecinos."""
    ys = sorted((line.y_at_start() + line.y_at_end()) / 2 for line in lines)
    diffs = [b - a for a, b in itertools.pairwise(ys) if b - a > 5]
    return float(np.median(diffs)) if diffs else math.inf


def refine(lines: list[Line], width: int, cfg: LayoutConfig,
           edges: tuple[Edge | None, Edge | None] = (None, None),
           trace: dict | None = None) -> tuple[list[Line], dict]:
    """Aplica las reglas en orden. Si se pasa `trace`, se llena con la decisión tomada
    sobre cada renglón de Kraken y la geometría usada, para la vista de control."""
    column = _robust_column(lines)
    max_len = cfg.short_frac * (column[1] - column[0]) if column else math.inf
    kept, beyond = split_beyond_edges(lines, *edges, max_length=max_len)
    kept, strip = split_facing_page(kept, width, cfg.edge_frac, cfg.short_frac)
    dropped = beyond + strip
    before_dup = kept
    kept, duplicates = drop_contained_lines(kept)
    spacing = line_spacing(kept)
    merged, merges = kept, 0
    merge_log: dict[str, str] = {}
    if math.isfinite(spacing):
        merged, merges = merge_split_lines(kept, y_tol=cfg.merge_y_frac * spacing,
                                           gap_tol=cfg.merge_gap_frac * width, log=merge_log)
    # Papel manchado o arrugado: Kraken toma pliegues por renglones. Esas páginas van a
    # revisión manual de la segmentación en vez de seguir de largo con basura
    column = text_column(merged)
    col_width = column[1] - column[0] if column else 0
    tiny = sum(line.length < cfg.tiny_line_frac * col_width for line in merged)
    tiny_ratio = tiny / len(merged) if merged else 1.0
    suspect = tiny_ratio >= cfg.suspect_tiny_ratio
    stats = {
        "lines_kraken": len(lines),
        "lines_facing_page": len(dropped),
        "lines_beyond_edge": len(beyond),
        "paper_edges": [e is not None for e in edges],
        "lines_duplicate": duplicates,
        "lines_merged": merges,
        "lines": len(merged),
        "line_spacing_px": round(spacing, 1) if math.isfinite(spacing) else None,
        "tiny_line_ratio": round(tiny_ratio, 2),
        "layout_suspect": suspect,
    }
    if trace is not None:
        kept_ids = {line.id for line in kept}
        fates = {line.id: "beyond_edge" for line in beyond}
        fates |= {line.id: "edge_strip" for line in strip}
        fates |= {line.id: "duplicate" for line in before_dup if line.id not in kept_ids}
        fates |= {line_id: "merged" for line_id in merge_log}
        fates |= {line.id: "kept" for line in merged}
        trace.update({
            "fates": fates,
            "merged_into": merge_log,
            "column_robust": list(_robust_column(lines) or []),
            "column": list(column or []),
            "edges": [e.__dict__ if e else None for e in edges],
            "edge_strip_px": [width * cfg.edge_frac, width * (1 - cfg.edge_frac)],
        })
    return merged, stats


# --- Integración con Kraken -------------------------------------------------------

def _apply_to_segmentation(seg, lines: list[Line]):
    """Reconstruye el contenedor de Kraken con los renglones refinados."""
    by_id = {line.id: line for line in seg.lines}
    new_lines = [
        dataclasses.replace(by_id[line.id], baseline=line.baseline, boundary=line.boundary)
        for line in lines
    ]
    used = {r for line in new_lines for r in (line.regions or [])}
    regions = {
        kind: [r for r in regs if r.id in used]
        for kind, regs in (seg.regions or {}).items()
    }
    regions = {k: v for k, v in regions.items() if v}
    return dataclasses.replace(seg, lines=new_lines, regions=regions, line_orders=None)


def _write_refined(seg, gray: np.ndarray, rec: dict, layout_dir: Path,
                   cfg: LayoutConfig) -> dict:
    from kraken.serialization import serialize

    size = (gray.shape[1], gray.shape[0])
    lines = [Line(line.id, [tuple(p) for p in line.baseline], [tuple(p) for p in line.boundary])
             for line in seg.lines if line.baseline and line.boundary]
    edges = paper_edges(gray, lines) if cfg.detect_paper_edges else (None, None)
    trace: dict = {}
    refined, stats = refine(lines, size[0], cfg, edges, trace)
    out = _apply_to_segmentation(seg, refined)
    name = f"{rec['page_id']}.xml"
    (layout_dir / name).write_text(serialize(out, image_size=size, template="pagexml"),
                                   encoding="utf-8")
    _write_debug(layout_dir / "debug" / f"{rec['page_id']}.json", rec, size, seg, lines,
                 refined, out, trace, stats)
    return {"page_id": rec["page_id"], "image": rec["file"], "file": name,
            "regions": sum(len(v) for v in out.regions.values()), **stats}


def _write_debug(path: Path, rec: dict, size: tuple[int, int], seg, lines: list[Line],
                 refined: list[Line], out, trace: dict, stats: dict) -> None:
    """Geometría y decisiones de cada regla, para la vista de control (`htr viewer`)."""
    def pts(points):
        return [[int(x), int(y)] for x, y in points]

    data = {
        "page_id": rec["page_id"],
        "image": rec["file"],
        "size": list(size),
        "stats": stats,
        "kraken_lines": [
            {"id": line.id, "baseline": pts(line.baseline), "boundary": pts(line.boundary),
             "length": round(line.length), "fate": trace["fates"].get(line.id, "kept"),
             "merged_into": trace["merged_into"].get(line.id)}
            for line in lines
        ],
        "lines": [{"id": line.id, "baseline": pts(line.baseline), "boundary": pts(line.boundary)}
                  for line in refined],
        "kraken_regions": [{"id": r.id, "kind": kind, "boundary": pts(r.boundary)}
                           for kind, regs in (seg.regions or {}).items() for r in regs],
        "regions": [{"id": r.id, "kind": kind, "boundary": pts(r.boundary)}
                    for kind, regs in (out.regions or {}).items() for r in regs],
        **{k: trace[k] for k in ("column", "column_robust", "edges", "edge_strip_px")},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _update_manifest(layout_dir: Path, records: list[dict]) -> None:
    manifest = layout_dir / "manifest.jsonl"
    done = {r["page_id"] for r in records}
    kept = [r for r in read_jsonl(manifest) if r["page_id"] not in done] if manifest.exists() else []
    write_jsonl(manifest, sorted(kept + records, key=lambda r: r["page_id"]))


def _selected(rec: dict, pages: set[str] | None) -> bool:
    return rec["kind"] != "blank" and (not pages or rec["page_id"][:5] in pages)


def segment_collection(clean_dir: Path, layout_dir: Path, cfg: LayoutConfig,
                       pages: set[str] | None = None, device: str = "cpu") -> list[dict]:
    # Import diferido: Kraken trae torch y tarda en cargar; el resto del CLI no lo necesita
    from kraken import blla
    from kraken.serialization import serialize
    from PIL import Image

    raw_out = layout_dir / "kraken"
    raw_out.mkdir(parents=True, exist_ok=True)
    records = []
    for rec in read_jsonl(clean_dir / "manifest.jsonl"):
        if not _selected(rec, pages):
            continue
        im = Image.open(clean_dir / rec["file"])
        seg = blla.segment(im, device=device)
        (raw_out / f"{rec['page_id']}.xml").write_text(
            serialize(seg, image_size=im.size, template="pagexml"), encoding="utf-8")
        records.append(_write_refined(seg, np.asarray(im.convert("L")), rec, layout_dir, cfg))
    _update_manifest(layout_dir, records)
    return records


def refine_collection(clean_dir: Path, layout_dir: Path, cfg: LayoutConfig,
                      pages: set[str] | None = None) -> list[dict]:
    """Vuelve a aplicar las reglas sobre la salida guardada de Kraken, sin correr el modelo.

    Sirve para ajustar umbrales en segundos en vez de volver a segmentar todo.
    """
    from kraken.lib.xml import XMLPage
    from PIL import Image

    records = []
    for rec in read_jsonl(clean_dir / "manifest.jsonl"):
        src = layout_dir / "kraken" / f"{rec['page_id']}.xml"
        if not _selected(rec, pages) or not src.exists():
            continue
        with Image.open(clean_dir / rec["file"]) as im:
            gray = np.asarray(im.convert("L"))
        records.append(_write_refined(XMLPage(src).to_container(), gray, rec, layout_dir, cfg))
    _update_manifest(layout_dir, records)
    return records
