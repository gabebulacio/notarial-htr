"""Tareas del proyecto, multiplataforma (Windows no trae `make`). El Makefile delega acá.

  python tasks.py setup        crea .venv e instala el paquete con torch CPU y Kraken
  python tasks.py models       baja los modelos base (McCATMuS) y verifica el hash
  python tasks.py status       avance de cada etapa (agregar --watch 10 para refrescar)
  python tasks.py ingest       PDF -> data/<colección>/raw
  python tasks.py preprocess   raw -> clean
  python tasks.py segment      clean -> layout (Kraken + filtros; ~30 s por página en CPU)
  python tasks.py refine       reaplica los filtros sobre la salida guardada de Kraken
  python tasks.py recognize    layout -> text (transcripción con confianza por carácter)
  python tasks.py correct      editor de transcripciones en el navegador (127.0.0.1:8765)
  python tasks.py evaluate     CER/WER contra las páginas corregidas (--per-page)
  python tasks.py check-gt     renglones corregidos para revisar contra las normas
  python tasks.py train        exporta correcciones para ketos (--kaggle arma zip + cuaderno)
  python tasks.py overlay      vistas de control en data/<colección>/overlay
  python tasks.py viewer       vista de control HTML por capas (agregar --open)
  python tasks.py test         pytest
  python tasks.py lint         ruff

Por defecto usa configs/ancasti-1794.yaml; otra colección con COLLECTION=configs/otra.yaml.
Los argumentos que sigan a la tarea pasan al comando: python tasks.py segment --pages 1-10
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
BIN = VENV / ("Scripts" if os.name == "nt" else "bin")
PY = BIN / ("python.exe" if os.name == "nt" else "python")
HTR = BIN / ("htr.exe" if os.name == "nt" else "htr")
CONFIG = os.environ.get("COLLECTION", "configs/ancasti-1794.yaml")
TORCH_CPU = "https://download.pytorch.org/whl/cpu"

# Modelos base: (carpeta, archivo, URL, sha256). `kraken get` no baja los archivos en
# Windows ("invalid path"), así que se bajan directo de Zenodo.
MODELS = [
    ("models/base/mccatmus", "McCATMuS_nfd_nofix_V1.mlmodel",
     "https://zenodo.org/records/13788177/files/McCATMuS_nfd_nofix_V1.mlmodel?download=1",
     "dfb911ba25fd11f93efc1b0c340957162981ecfdaac0ee1e26793d491f770244"),
    ("models/base/mccatmus", "metadata.json",
     "https://zenodo.org/records/13788177/files/metadata.json?download=1", None),
]


def run(cmd: list, cwd: Path = ROOT) -> None:
    print("$", " ".join(map(str, cmd)))
    r = subprocess.run(cmd, cwd=cwd, check=False)
    if r.returncode:
        sys.exit(r.returncode)


def py() -> str:
    return str(PY if PY.exists() else sys.executable)


def htr(command: str) -> None:
    if not HTR.exists():
        sys.exit("falta el entorno: python tasks.py setup")
    run([str(HTR), command, CONFIG, *sys.argv[2:]])


def setup() -> None:
    if not PY.exists():
        run([sys.executable, "-m", "venv", str(VENV)])
    run([py(), "-m", "pip", "install", "-q", "--upgrade", "pip"])
    # Torch CPU antes que Kraken, si no pip baja la versión con CUDA (varios GB)
    run([py(), "-m", "pip", "install", "-q", "torch>=2.9,<=2.14", "torchvision",
         "--index-url", TORCH_CPU])
    run([py(), "-m", "pip", "install", "-q", "-e", ".[layout,dev]"])


def models() -> None:
    import hashlib
    import urllib.request

    for folder, name, url, sha in MODELS:
        dest = ROOT / folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            print(f"bajando {name}")
            urllib.request.urlretrieve(url, dest)
        if sha:
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            if digest != sha:
                dest.unlink()
                sys.exit(f"hash distinto para {name}: {digest}")
        print(f"ok {dest.relative_to(ROOT)}")


def test() -> None:
    run([py(), "-m", "pytest", "-q", *sys.argv[2:]])


def lint() -> None:
    run([py(), "-m", "ruff", "check", "src", "tests", "tasks.py"])


TASKS = {
    "setup": setup,
    "models": models,
    "status": lambda: htr("status"),
    "ingest": lambda: htr("ingest"),
    "preprocess": lambda: htr("preprocess"),
    "segment": lambda: htr("segment"),
    "refine": lambda: htr("refine"),
    "recognize": lambda: htr("recognize"),
    "correct": lambda: htr("correct"),
    "evaluate": lambda: htr("evaluate"),
    "check-gt": lambda: htr("check-gt"),
    "train": lambda: htr("train"),
    "overlay": lambda: htr("overlay"),
    "viewer": lambda: htr("viewer"),
    "test": test,
    "lint": lint,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
        print(__doc__)
        sys.exit(1)
    TASKS[sys.argv[1]]()
