import cv2
import numpy as np

from notarial_htr.config import PreprocessConfig
from notarial_htr.manifest import read_jsonl, write_jsonl
from notarial_htr.preprocess import preprocess_collection


def _raw_collection(raw_dir, n=3):
    raw_dir.mkdir(parents=True)
    records = []
    for i in range(1, n + 1):
        img = np.full((400, 300), 230, np.uint8)
        cv2.putText(img, "texto", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 2, 30, 4)
        name = f"p{i:04d}.png"
        cv2.imwrite(str(raw_dir / name), img)
        records.append({"page_id": f"p{i:04d}", "file": name})
    write_jsonl(raw_dir / "manifest.jsonl", records)


def test_partial_run_keeps_other_pages(tmp_path):
    raw, clean = tmp_path / "raw", tmp_path / "clean"
    _raw_collection(raw)
    preprocess_collection(raw, clean, PreprocessConfig())
    preprocess_collection(raw, clean, PreprocessConfig(), pages={"p0002"})
    ids = [r["page_id"] for r in read_jsonl(clean / "manifest.jsonl")]
    assert ids == ["p0001", "p0002", "p0003"]
