import json

from notarial_htr.manifest import write_jsonl
from notarial_htr.viewer import build_viewer

STATS = {"lines_kraken": 3, "lines": 1, "lines_beyond_edge": 1, "lines_facing_page": 1,
         "lines_duplicate": 0, "lines_merged": 1, "paper_edges": [True, False],
         "tiny_line_ratio": 0.0, "layout_suspect": False}


def _debug(page_id):
    line = {"baseline": [[10, 50], [200, 50]], "boundary": [[10, 30], [200, 30], [200, 60], [10, 60]]}
    return {
        "page_id": page_id, "image": f"{page_id}.png", "size": [300, 400], "stats": STATS,
        "kraken_lines": [{"id": "a", **line, "length": 190, "fate": "kept", "merged_into": None},
                         {"id": "b", **line, "length": 20, "fate": "beyond_edge", "merged_into": None}],
        "lines": [{"id": "a", **line}], "kraken_regions": [], "regions": [],
        "column": [10, 200], "column_robust": [10, 200],
        "edges": [{"x1": 5, "y1": 0, "x2": 5, "y2": 400}, None], "edge_strip_px": [24, 276],
    }


def test_viewer_writes_index_and_linked_pages(tmp_path):
    debug = tmp_path / "layout" / "debug"
    debug.mkdir(parents=True)
    for pid in ("p0001", "p0002"):
        (debug / f"{pid}.json").write_text(json.dumps(_debug(pid)), encoding="utf-8")
    write_jsonl(tmp_path / "clean" / "manifest.jsonl",
                [{"page_id": "p0001", "source": "p0001.jpeg", "skew_deg": 1.0,
                  "skew_confident": True}])

    index = build_viewer(tmp_path, "Prueba")
    assert "p0001.html" in index.read_text(encoding="utf-8")
    first = (tmp_path / "viewer" / "p0001.html").read_text(encoding="utf-8")
    assert '"next": "p0002.html"' in first and "../raw/p0001.jpeg" in first
    assert "rotada 1.0°" in first
