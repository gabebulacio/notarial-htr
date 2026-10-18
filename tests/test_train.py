import json

import cv2
import numpy as np

from notarial_htr.manifest import write_jsonl
from notarial_htr.train import export_training_set, ketos_command

LINE = {"baseline": [[10, 50], [200, 50]],
        "boundary": [[10, 30], [200, 30], [200, 60], [10, 60]]}


def _setup(tmp_path):
    clean, layout, gt = tmp_path / "clean", tmp_path / "layout", tmp_path / "gt"
    clean.mkdir()
    (layout / "debug").mkdir(parents=True)
    gt.mkdir()
    pages = {"p0001": (False, "corregida"), "p0002": (False, "corregida"),
             "p0003": (True, "corregida"), "p0004": (False, "en_curso")}
    write_jsonl(layout / "manifest.jsonl",
                [{"page_id": p, "image": f"{p}.png", "layout_suspect": s}
                 for p, (s, _) in pages.items()])
    for pid, (_, status) in pages.items():
        cv2.imwrite(str(clean / f"{pid}.png"), np.full((100, 300), 220, np.uint8))
        (layout / "debug" / f"{pid}.json").write_text(json.dumps(
            {"size": [300, 100], "lines": [{"id": i, **LINE} for i in ("a", "b", "c")]}))
        (gt / f"{pid}.json").write_text(json.dumps({"page_id": pid, "status": status, "lines": [
            {"id": "a", "text": "Certifico en q^to puedo"},
            {"id": "b", "text": "B", "not_text": True},
            {"id": "c", "text": "  "}]}))
    return clean, layout, gt


def test_export_keeps_only_clean_corrected_training_lines(tmp_path):
    clean, layout, gt = _setup(tmp_path)
    ts = export_training_set(clean, layout, gt, tmp_path / "out", test_pages={"p0002"})
    assert ts.pages == ["p0001"] and ts.lines == 1
    assert ts.skipped == {"evaluación": ["p0002"], "segmentación sospechosa": ["p0003"],
                          "sin terminar": ["p0004"]}
    xml = (tmp_path / "out" / "p0001.xml").read_text(encoding="utf-8")
    assert "<Unicode>Certifico en q^to puedo</Unicode>" in xml and 'imageFilename="p0001.png"' in xml
    assert (tmp_path / "out" / "p0001.png").exists()
    assert (tmp_path / "out" / "train.txt").read_text() == "p0001.xml\n"


def test_exported_page_parses_in_kraken(tmp_path):
    import pytest
    xml_mod = pytest.importorskip("kraken.lib.xml")
    clean, layout, gt = _setup(tmp_path)
    export_training_set(clean, layout, gt, tmp_path / "out", test_pages=set())
    seg = xml_mod.XMLPage(tmp_path / "out" / "p0001.xml").to_container()
    assert [line.text for line in seg.lines] == ["Certifico en q^to puedo"]


def test_ketos_command_fine_tunes_from_base():
    cmd = ketos_command("train.txt", "base.mlmodel", "out", device="cuda:0")
    assert cmd[:3] == ["ketos", "-d", "cuda:0"]
    assert ["-i", "base.mlmodel"] == cmd[cmd.index("-i"):cmd.index("-i") + 2]
    assert "union" in cmd and "NFD" in cmd
