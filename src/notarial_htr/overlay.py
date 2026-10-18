"""Vista de control de la segmentación: regiones, líneas base y lo que se descartó."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .manifest import read_jsonl

_GREY = (170, 170, 170)
_RED = (0, 0, 220)
_BLUE = (220, 120, 0)
_GREEN = (0, 140, 0)


def _load(xml: Path):
    from kraken.lib.xml import XMLPage
    return XMLPage(xml).to_container()


def draw_page(image: Path, kraken_xml: Path, refined_xml: Path, scale: float = 0.35) -> np.ndarray:
    """Gris: salida original de Kraken. Azul: regiones. Rojo: renglones que quedan."""
    gray = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    thick = max(3, img.shape[1] // 500)
    for line in _load(kraken_xml).lines:
        cv2.polylines(img, [np.array(line.baseline, np.int32)], False, _GREY, thick * 3)
    refined = _load(refined_xml)
    for region in (r for regs in refined.regions.values() for r in regs):
        cv2.polylines(img, [np.array(region.boundary, np.int32)], True, _BLUE, thick)
    for i, line in enumerate(refined.lines, 1):
        cv2.polylines(img, [np.array(line.baseline, np.int32)], False, _RED, thick)
        x, y = line.baseline[0]
        cv2.putText(img, str(i), (int(x), int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    thick * 0.5, _GREEN, thick)
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def draw_collection(clean_dir: Path, layout_dir: Path, out_dir: Path,
                    pages: set[str] | None = None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for rec in read_jsonl(layout_dir / "manifest.jsonl"):
        if pages and rec["page_id"][:5] not in pages:
            continue
        img = draw_page(clean_dir / rec["image"], layout_dir / "kraken" / rec["file"],
                        layout_dir / rec["file"])
        cv2.imwrite(str(out_dir / f"{rec['page_id']}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        n += 1
    return n
