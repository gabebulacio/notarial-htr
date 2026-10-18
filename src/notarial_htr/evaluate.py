"""CER y WER de la transcripción automática contra las correcciones humanas.

Se compara la predicción actual (`text/`) con las páginas marcadas como `corregida` en
`ground_truth/`. Las páginas de evaluación (`evaluation.test_pages`) se informan aparte:
nunca se usan para entrenar, así que son las que miden de verdad.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


def edit_distance(a: list | str, b: list | str) -> int:
    """Distancia de Levenshtein (inserción, borrado y sustitución cuestan 1)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


@dataclass
class Score:
    char_errors: int = 0
    chars: int = 0
    word_errors: int = 0
    words: int = 0
    lines: int = 0
    pages: list[str] = field(default_factory=list)

    def add(self, pred: str, ref: str) -> None:
        pred, ref = _norm(pred), _norm(ref)
        self.char_errors += edit_distance(pred, ref)
        self.chars += len(ref)
        self.word_errors += edit_distance(pred.split(), ref.split())
        self.words += len(ref.split())
        self.lines += 1

    @property
    def cer(self) -> float | None:
        return self.char_errors / self.chars if self.chars else None

    @property
    def wer(self) -> float | None:
        return self.word_errors / self.words if self.words else None


def score_page(text_dir: Path, gt: dict) -> Score | None:
    """Puntaje de una página corregida (o en curso) contra la predicción actual."""
    pred_file = text_dir / f"{gt['page_id']}.json"
    if not pred_file.exists():
        return None
    pred = {line["id"]: line["text"]
            for line in json.loads(pred_file.read_text(encoding="utf-8"))["lines"]}
    page = Score(pages=[gt["page_id"]])
    for line in gt["lines"]:
        if line["id"] in pred and not line.get("not_text"):
            page.add(pred[line["id"]], line["text"])
    return page


def evaluate(text_dir: Path, gt_dir: Path, test_pages: set[str]) -> dict[str, Score]:
    scores = {"evaluación": Score(), "entrenamiento": Score()}
    per_page: dict[str, Score] = {}
    for gt_file in sorted(gt_dir.glob("p*.json")):
        gt = json.loads(gt_file.read_text(encoding="utf-8"))
        if gt["status"] != "corregida" or (page := score_page(text_dir, gt)) is None:
            continue
        bucket = scores["evaluación" if gt["page_id"] in test_pages else "entrenamiento"]
        for attr in ("char_errors", "chars", "word_errors", "words", "lines"):
            setattr(bucket, attr, getattr(bucket, attr) + getattr(page, attr))
        bucket.pages.append(gt["page_id"])
        per_page[gt["page_id"]] = page
    return {**scores, **per_page}
