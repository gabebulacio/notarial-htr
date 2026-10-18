"""Ajuste fino del modelo de reconocimiento sobre las correcciones humanas.

`export_training_set` arma un conjunto en PAGE XML (imagen + renglones con el texto
corregido) que `ketos train` lee directo. Quedan afuera, siempre:
- las páginas de evaluación (miden el error; si se entrenan, la medición deja de servir),
- las páginas con segmentación sospechosa hasta que se revise su layout,
- los renglones marcados «no es texto» o vacíos.

`kaggle_bundle` empaqueta ese conjunto con un cuaderno listo para correr en una GPU de
Kaggle; en CPU el ajuste fino funciona pero tarda horas.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .manifest import read_jsonl

KRAKEN_VERSION = "7.1.1"


@dataclass
class TrainingSet:
    out_dir: Path
    pages: list[str]
    lines: int
    chars: int
    skipped: dict[str, list[str]]

    @property
    def manifest(self) -> Path:
        return self.out_dir / "train.txt"


def _pts(points) -> str:
    return " ".join(f"{int(x)},{int(y)}" for x, y in points)


def page_xml(image_name: str, size: tuple[int, int], lines: list[dict]) -> str:
    """PAGE XML mínimo con un TextRegion que abarca la página y los renglones corregidos."""
    w, h = size
    body = "\n".join(
        f'      <TextLine id={quoteattr(line["id"])}>\n'
        f'        <Coords points="{_pts(line["boundary"])}"/>\n'
        f'        <Baseline points="{_pts(line["baseline"])}"/>\n'
        f'        <TextEquiv><Unicode>{escape(line["text"])}</Unicode></TextEquiv>\n'
        f'      </TextLine>'
        for line in lines
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Metadata><Creator>notarial-htr</Creator></Metadata>
  <Page imageFilename={quoteattr(image_name)} imageWidth="{w}" imageHeight="{h}">
    <TextRegion id="r_page" type="paragraph">
      <Coords points="0,0 {w},0 {w},{h} 0,{h}"/>
{body}
    </TextRegion>
  </Page>
</PcGts>
"""


def export_training_set(clean_dir: Path, layout_dir: Path, gt_dir: Path, out_dir: Path,
                        test_pages: set[str]) -> TrainingSet:
    layout = {r["page_id"]: r for r in read_jsonl(layout_dir / "manifest.jsonl")}
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    pages, n_lines, n_chars = [], 0, 0
    skipped: dict[str, list[str]] = {"evaluación": [], "segmentación sospechosa": [],
                                     "sin terminar": []}
    for f in sorted(gt_dir.glob("p*.json")):
        gt = json.loads(f.read_text(encoding="utf-8"))
        pid = gt["page_id"]
        if pid in test_pages:
            skipped["evaluación"].append(pid)
            continue
        if gt["status"] != "corregida":
            skipped["sin terminar"].append(pid)
            continue
        if layout.get(pid, {}).get("layout_suspect"):
            skipped["segmentación sospechosa"].append(pid)
            continue
        debug = json.loads((layout_dir / "debug" / f"{pid}.json").read_text(encoding="utf-8"))
        geom = {line["id"]: line for line in debug["lines"]}
        lines = [
            {**geom[line["id"]], "text": line["text"].strip()}
            for line in gt["lines"]
            if line["id"] in geom and line["text"].strip() and not line.get("not_text")
        ]
        if not lines:
            continue
        image = layout[pid]["image"]
        shutil.copy2(clean_dir / image, out_dir / image)
        (out_dir / f"{pid}.xml").write_text(page_xml(image, tuple(debug["size"]), lines),
                                            encoding="utf-8")
        pages.append(pid)
        n_lines += len(lines)
        n_chars += sum(len(line["text"]) for line in lines)
    (out_dir / "train.txt").write_text("".join(f"{p}.xml\n" for p in pages), encoding="utf-8")
    return TrainingSet(out_dir, pages, n_lines, n_chars, skipped)


def ketos_command(train_list: str, base_model: str, output: str, device: str = "cpu",
                  workers: int = 2) -> list[str]:
    """Comando de ajuste fino desde el modelo base.

    - `--resize union`: el modelo conserva sus caracteres y suma los nuevos de las normas.
    - `-u NFD`: McCATMuS se entrenó en NFD; las correcciones se guardan en NFC y ketos
      las normaliza al leerlas.
    - `-p 0.9`: 10 % de los renglones para validación interna (no son las páginas de
      evaluación, que nunca entran acá).
    - Parada temprana: corta cuando la validación deja de mejorar.
    """
    return [
        "ketos", "-d", device, "--workers", str(workers), "-s", "1794",
        "train", "-f", "page", "-t", train_list, "-p", "0.9",
        "-i", base_model, "--resize", "union", "-u", "NFD",
        "-B", "8", "--augment", "-q", "early", "--lag", "10", "--min-epochs", "15",
        "-r", "0.0001", "-o", output,
    ]


_NOTEBOOK_CELLS = [
    ("markdown", ("# notarial-htr · ajuste fino en GPU\n\nActivar **GPU** e **Internet** en "
                 "*Settings*. Agregar el dataset subido como entrada (*Add Input*).")),
    ("code", f"!pip install -q kraken=={KRAKEN_VERSION}"),
    ("code", ("import glob, os, shutil\n"
             "src = glob.glob('/kaggle/input/*/train.txt')[0]\n"
             "data = os.path.dirname(src)\n"
             "work = '/kaggle/working/train'\n"
             "shutil.copytree(data, work, dirs_exist_ok=True)\n"
             "os.chdir(work)\nprint(open('train.txt').read())")),
    ("code", "%CMD%"),
    ("code", ("import glob\nprint(sorted(glob.glob('/kaggle/working/model/*')))\n"
             "# Bajar el mejor modelo (*_best*) desde la pestaña Output y copiarlo en\n"
             "# models/<colección>/ del proyecto; después: htr recognize con ese modelo.")),
]


def kaggle_bundle(ts: TrainingSet, base_model: Path, out_zip: Path) -> Path:
    """Zip para subir como dataset de Kaggle + cuaderno que lo entrena en GPU."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    cmd = ketos_command("train.txt", base_model.name, "/kaggle/working/model",
                        device="cuda:0", workers=4)
    cells = []
    for kind, src in _NOTEBOOK_CELLS:
        src = src.replace("%CMD%", "!" + " ".join(cmd))
        cell = {"cell_type": kind, "metadata": {}, "source": src}
        if kind == "code":
            cell |= {"outputs": [], "execution_count": None}
        cells.append(cell)
    notebook = {"cells": cells, "metadata": {"kernelspec": {"name": "python3",
                "display_name": "Python 3", "language": "python"}},
                "nbformat": 4, "nbformat_minor": 5}
    nb_path = out_zip.with_suffix(".ipynb")
    nb_path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ts.out_dir.iterdir()):
            z.write(f, f.name)
        z.write(base_model, base_model.name)
    return nb_path
