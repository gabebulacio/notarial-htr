import pytest

pytest.importorskip("shapely")

import cv2
import numpy as np

from notarial_htr.config import LayoutConfig
from notarial_htr.layout import (
    Edge,
    Line,
    drop_contained_lines,
    merge_split_lines,
    paper_edges,
    refine,
    split_beyond_edges,
    split_facing_page,
)

WIDTH = 2000


def _line(i, x0, x1, y):
    return Line(f"l{i}", [(x0, y), (x1, y)],
                [(x0, y - 40), (x1, y - 40), (x1, y + 10), (x0, y + 10)])


def _page_lines():
    # Bloque principal de 15 renglones entre x=250 y x=1800, interlineado 90 px
    return [_line(i, 250, 1800, 200 + 90 * i) for i in range(15)]


def test_facing_page_fragments_dropped():
    lines = _page_lines() + [
        _line(100, 5, 120, 400),      # restos de la página enfrentada a la izquierda
        _line(101, 1900, 1995, 700),  # y a la derecha
    ]
    kept, dropped = split_facing_page(lines, WIDTH, edge_frac=0.08, short_frac=0.25)
    assert {line.id for line in dropped} == {"l100", "l101"}
    assert len(kept) == 15


def test_marginal_note_of_the_page_is_kept():
    # Nota al margen: fuera del bloque pero lejos del borde de la imagen
    note = _line(200, 180, 240, 500)
    kept, dropped = split_facing_page(_page_lines() + [note], WIDTH, 0.08, 0.25)
    assert note in kept and not dropped


def test_split_line_is_merged():
    lines = _page_lines()
    a, b = _line(300, 250, 900, 2000), _line(301, 930, 1800, 2006)
    merged, n = merge_split_lines(lines + [a, b], y_tol=30, gap_tol=120)
    assert n == 1
    joined = next(line for line in merged if line.id == "l300")
    assert joined.x0 == 250 and joined.x1 == 1800
    assert len(merged) == 16


def test_lines_on_different_rows_not_merged():
    merged, n = merge_split_lines(_page_lines(), y_tol=30, gap_tol=120)
    assert n == 0 and len(merged) == 15


def test_refine_reports_stats():
    lines = _page_lines() + [_line(100, 5, 120, 400)]
    _, stats = refine(lines, WIDTH, LayoutConfig())
    assert stats["lines_kraken"] == 16
    assert stats["lines_facing_page"] == 1
    assert stats["lines"] == 15
    assert stats["line_spacing_px"] == pytest.approx(90)
    assert stats["layout_suspect"] is False


def test_fragment_touching_the_text_block_is_still_dropped():
    # El texto llega casi al borde y el resto de la otra página arranca pegado
    lines = _page_lines() + [_line(102, 1860, 1930, 900)]
    _, dropped = split_facing_page(lines, WIDTH, 0.08, 0.25)
    assert [line.id for line in dropped] == ["l102"]


def test_duplicate_line_on_top_of_another_is_dropped():
    lines = _page_lines() + [_line(400, 900, 1300, 200 + 90 * 3)]
    kept, n = drop_contained_lines(lines)
    assert n == 1 and "l400" not in {line.id for line in kept}


def test_crumpled_page_is_flagged():
    # Pocos renglones reales y muchos trazos cortos de pliegues y manchas
    noise = [_line(500 + i, 400 + (i % 7) * 180, 520 + (i % 7) * 180, 160 + 37 * i)
             for i in range(40)]
    _, stats = refine(_page_lines()[:5] + noise, WIDTH, LayoutConfig())
    assert stats["layout_suspect"] is True


def test_columnar_list_is_not_flagged():
    # Lista de aranceles: concepto largo y monto corto en el mismo renglón
    lines = [_line(i, 250, 1300, 200 + 90 * i) for i in range(15)]
    amounts = [_line(100 + i, 1650, 1800, 200 + 90 * i) for i in range(10)]
    _, stats = refine(lines + amounts, WIDTH, LayoutConfig())
    assert stats["layout_suspect"] is False


def _photo_with_edge(edge_top=150, edge_bottom=110):
    """Foto sintética: hoja clara sobre la página enfrentada, separadas por una sombra
    inclinada (perspectiva), con renglones de 'texto' a ambos lados."""
    h, w = 2600, WIDTH
    img = np.full((h, w), 225, np.uint8)
    pts = np.array([[0, 0], [edge_top, 0], [edge_bottom, h], [0, h]], np.int32)
    cv2.fillPoly(img, [pts], 175)
    cv2.line(img, (edge_top, 0), (edge_bottom, h), 60, 6)
    for i in range(15):
        y = 200 + 90 * i
        for x in range(250, 1800, 60):
            cv2.rectangle(img, (x, y - 25), (x + 40, y), 40, -1)
    return img


def test_paper_edge_found_and_used():
    img = _photo_with_edge()
    fragments = [_line(600, 10, 90, 500), _line(601, 20, 80, 1500)]
    lines = _page_lines() + fragments
    left, right = paper_edges(img, lines)
    assert left is not None and right is None
    assert left.x_at(0) == pytest.approx(150, abs=15)
    assert left.x_at(2600) == pytest.approx(110, abs=15)
    kept, dropped = split_beyond_edges(lines, left, right)
    assert {line.id for line in dropped} == {"l600", "l601"}
    assert len(kept) == 15


def test_slanted_edge_is_followed():
    # Borde inclinado: en y=0 está en x=300, en y=1000 en x=100
    edge = Edge(300, 0, 100, 1000)
    near_top, near_bottom = _line(1, 200, 280, 50), _line(2, 200, 280, 950)
    kept, dropped = split_beyond_edges([near_top, near_bottom], edge, None)
    assert dropped == [near_top] and kept == [near_bottom]


def test_ruled_ink_line_is_not_a_paper_edge():
    # Regla de tinta a la derecha del texto (columna de importes): mismo papel a ambos lados
    img = np.full((2600, WIDTH), 225, np.uint8)
    cv2.line(img, (1880, 50), (1880, 2550), 50, 5)
    for i in range(15):
        y = 200 + 90 * i
        for x in range(250, 1800, 60):
            cv2.rectangle(img, (x, y - 25), (x + 40, y), 40, -1)
    _, right = paper_edges(img, _page_lines())
    assert right is None


def test_trace_records_each_decision():
    split_a, split_b = _line(300, 250, 900, 2000), _line(301, 930, 1800, 2006)
    lines = _page_lines() + [_line(100, 5, 120, 400), split_a, split_b,
                             _line(400, 900, 1300, 200 + 90 * 3)]
    trace = {}
    refine(lines, WIDTH, LayoutConfig(), trace=trace)
    fates = trace["fates"]
    assert fates["l100"] == "edge_strip"
    assert fates["l400"] == "duplicate"
    assert fates["l301"] == "merged" and trace["merged_into"]["l301"] == "l300"
    assert fates["l300"] == "kept" and fates["l0"] == "kept"
    assert len(fates) == len(lines)
