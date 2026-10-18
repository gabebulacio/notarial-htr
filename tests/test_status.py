from pathlib import Path

from notarial_htr.config import load_config
from notarial_htr.manifest import write_jsonl
from notarial_htr.status import collection_status, render

CONFIG = Path(__file__).parents[1] / "configs" / "ancasti-1794.yaml"



def test_status_counts_each_stage(tmp_path):
    cfg = load_config(CONFIG, root=tmp_path)
    write_jsonl(cfg.raw_dir / "manifest.jsonl", [{"page_id": f"p{i:04d}"} for i in range(1, 5)])
    for i in range(1, 5):
        (cfg.raw_dir / f"p{i:04d}.jpeg").write_bytes(b"x")
    cfg.clean_dir.mkdir(parents=True)
    for i in range(1, 5):
        (cfg.clean_dir / f"p{i:04d}.png").write_bytes(b"x")
    (cfg.layout_dir / "kraken").mkdir(parents=True)
    (cfg.layout_dir / "kraken" / "p0001.xml").write_text("<x/>")
    write_jsonl(cfg.layout_dir / "manifest.jsonl",
                [{"page_id": "p0001", "lines": 20, "layout_suspect": True}])

    st = collection_status(cfg)
    done = {s.name: (s.done, s.total) for s in st["stages"]}
    assert done["ingesta"] == (4, 4)
    assert done["segmentación (Kraken)"] == (1, 4)
    assert st["suspect"] == ["p0001"]
    assert "a revisar a mano (1): p0001" in render(st)
