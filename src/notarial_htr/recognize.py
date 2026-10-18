"""Reconocimiento de texto por renglón con un modelo de Kraken (CNN + BiLSTM + CTC).

Lee la segmentación filtrada de `layout/` y escribe en `text/`:
- `pXXXX.xml`: PAGE XML con el texto de cada renglón,
- `pXXXX.txt`: texto plano, un renglón por línea,
- `pXXXX.json`: texto, confianza por carácter y por renglón, para revisión y búsqueda.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import unicodedata
from pathlib import Path

from .config import RecognitionConfig
from .manifest import read_jsonl, write_jsonl


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize(text: str, form: str) -> str:
    return unicodedata.normalize(form, text) if form else text


def line_record(line_id: str, prediction: str, confidences: list[float], form: str) -> dict:
    """Renglón reconocido con confianza por carácter, ya normalizado.

    La normalización (NFD -> NFC) puede juntar caracteres; en ese caso la confianza del
    carácter compuesto es la mínima de sus partes, para no inflarla.
    """
    chars, confs = [], []
    for ch, conf in zip(prediction, confidences, strict=False):
        if chars and unicodedata.combining(ch) and form == "NFC":
            chars[-1] += ch
            confs[-1] = min(confs[-1], conf)
        else:
            chars.append(ch)
            confs.append(conf)
    chars = [normalize(c, form) for c in chars]
    return {
        "id": line_id,
        "text": "".join(chars),
        "char_conf": [round(float(c), 4) for c in confs],
        "conf": round(float(min(confs)), 4) if confs else 0.0,
        "mean_conf": round(float(sum(confs) / len(confs)), 4) if confs else 0.0,
    }


def recognize_collection(clean_dir: Path, layout_dir: Path, text_dir: Path,
                         cfg: RecognitionConfig, pages: set[str] | None = None,
                         device: str = "cpu") -> list[dict]:
    from kraken import rpred
    from kraken.lib import models
    from kraken.lib.xml import XMLPage
    from kraken.serialization import serialize
    from PIL import Image

    model_path = Path(cfg.model)
    digest = file_sha256(model_path)
    if cfg.model_sha256 and digest != cfg.model_sha256:
        raise ValueError(f"El modelo {model_path} no coincide con el hash de la configuración")
    net = models.load_any(str(model_path), device=device)

    text_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for rec in read_jsonl(layout_dir / "manifest.jsonl"):
        if pages and rec["page_id"][:5] not in pages:
            continue
        seg = XMLPage(layout_dir / rec["file"]).to_container()
        with Image.open(clean_dir / rec["image"]) as im:
            results = list(rpred.rpred(net, im, seg)) if seg.lines else []
            size = im.size
        lines = [line_record(r.id, r.prediction, list(r.confidences), cfg.unicode_form)
                 for r in results]
        pid = rec["page_id"]
        if results:
            xml = serialize(dataclasses.replace(seg, lines=results), image_size=size,
                            template="pagexml")
            # Se normaliza el documento entero: tocar el texto de cada registro desalinearía
            # caracteres, posiciones y confianzas dentro de Kraken
            (text_dir / f"{pid}.xml").write_text(normalize(xml, cfg.unicode_form),
                                                 encoding="utf-8")
        (text_dir / f"{pid}.txt").write_text("\n".join(x["text"] for x in lines) + "\n",
                                             encoding="utf-8")
        (text_dir / f"{pid}.json").write_text(json.dumps(
            {"page_id": pid, "model": model_path.name, "model_sha256": digest, "lines": lines},
            ensure_ascii=False), encoding="utf-8")
        confs = [x["mean_conf"] for x in lines]
        records.append({
            "page_id": pid, "lines": len(lines),
            "chars": sum(len(x["text"]) for x in lines),
            "mean_conf": round(sum(confs) / len(confs), 4) if confs else None,
            "low_conf_lines": sum(c < cfg.low_conf for c in confs),
            "model": model_path.name, "model_sha256": digest[:12],
        })

    manifest = text_dir / "manifest.jsonl"
    done = {r["page_id"] for r in records}
    kept = [r for r in read_jsonl(manifest) if r["page_id"] not in done] if manifest.exists() else []
    write_jsonl(manifest, sorted(kept + records, key=lambda r: r["page_id"]))
    return records
