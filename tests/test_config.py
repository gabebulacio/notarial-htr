from pathlib import Path

from notarial_htr.cli import _parse_pages
from notarial_htr.config import load_config

CONFIG = Path(__file__).parents[1] / "configs" / "ancasti-1794.yaml"


def test_load_collection_config(tmp_path):
    cfg = load_config(CONFIG, root=tmp_path)
    assert cfg.collection_id == "ancasti-1794"
    assert cfg.years == (1794, 1799)
    assert cfg.raw_dir == tmp_path / "data" / "ancasti-1794" / "raw"
    assert cfg.preprocess.deskew_max_angle == 4.0


def test_parse_pages():
    assert _parse_pages("1-3,9") == {"p0001", "p0002", "p0003", "p0009"}
    assert _parse_pages(None) is None
