"""Control de las correcciones contra las normas de transcripción.

No corrige nada: señala renglones para volver a mirar con la imagen al lado. Las pistas
salen de comparar con la lectura del modelo (si el modelo vio una volada o una coma y la
corrección no la tiene, conviene confirmarlo) y de la sintaxis de las marcas.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_PUNCT = re.compile(r"[,.;:=]")
_TAG = re.compile(r"\[([^\]]*)\]")
_ALLOWED_TAG = re.compile(r"^(\.\.\.|\.\.\d+\.\.|tach: .+|int: .+|rúbrica)$")


@dataclass
class Finding:
    page_id: str
    line: int
    kind: str
    detail: str


def check_line(text: str, prediction: str, not_text: bool) -> list[tuple[str, str]]:
    out = []
    if not_text:
        return out
    if not text.strip():
        out.append(("vacío", "renglón vacío sin marcar como «no es texto»"))
    if prediction.count("^") > text.count("^"):
        out.append(("volada", "el modelo leyó letras voladas (^) que la corrección no tiene"))
    if len(_PUNCT.findall(prediction)) > len(_PUNCT.findall(text)) + 1:
        out.append(("puntuación", "el modelo leyó más signos de puntuación que la corrección"))
    if text.count("[") != text.count("]"):
        out.append(("marca", "corchetes sin cerrar"))
    for tag in _TAG.findall(text):
        if not _ALLOWED_TAG.match(tag):
            out.append(("marca", f"marca desconocida [{tag}]"))
    return out


def check_collection(gt_dir: Path, suspect_pages: set[str]) -> list[Finding]:
    findings = []
    for f in sorted(gt_dir.glob("p*.json")):
        gt = json.loads(f.read_text(encoding="utf-8"))
        pid = gt["page_id"]
        if pid in suspect_pages and gt["status"] == "corregida":
            junk = sum(not line.get("not_text") for line in gt["lines"]
                       if len(line["text"].strip()) <= 2)
            if junk:
                findings.append(Finding(pid, 0, "segmentación",
                                        f"página con segmentación dudosa: {junk} renglones de 0-2 "
                                        "caracteres sin marcar «no es texto»"))
        for i, line in enumerate(gt["lines"], 1):
            for kind, detail in check_line(line["text"], line.get("prediction", ""),
                                           line.get("not_text", False)):
                findings.append(Finding(pid, i, kind, detail))
    return findings
