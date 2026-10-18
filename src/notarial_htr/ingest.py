"""Extracción de las imágenes originales del PDF, sin volver a comprimirlas."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from .manifest import sha256_bytes, write_jsonl


def page_id(index: int) -> str:
    """Identificador estable de página (1-based), p. ej. `p0001`."""
    return f"p{index + 1:04d}"


def extract_pdf_images(pdf_path: Path, out_dir: Path) -> list[dict]:
    """Guarda la imagen embebida de cada página tal como vino del escáner.

    Si una página no tiene exactamente una imagen (texto vectorial, collage), se
    rasteriza a 300 ppp y queda marcada en el manifiesto con `rendered: true`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            pid = page_id(i)
            images = page.get_images(full=True)
            if len(images) == 1:
                info = doc.extract_image(images[0][0])
                data, ext = info["image"], info["ext"]
                width, height, rendered = info["width"], info["height"], False
            else:
                pix = page.get_pixmap(dpi=300)
                data, ext = pix.tobytes("png"), "png"
                width, height, rendered = pix.width, pix.height, True
            name = f"{pid}.{ext}"
            (out_dir / name).write_bytes(data)
            records.append({
                "page_id": pid,
                "pdf_page": i + 1,
                "file": name,
                "width": width,
                "height": height,
                "sha256": sha256_bytes(data),
                "rendered": rendered,
            })
    write_jsonl(out_dir / "manifest.jsonl", records)
    return records
