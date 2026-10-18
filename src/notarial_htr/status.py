"""Estado de cada etapa de una colección, leído del disco (sirve con una corrida en curso)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .manifest import read_jsonl

# Si el último archivo de una etapa es más nuevo que esto, la etapa se considera en curso
_ACTIVE_SECONDS = 180


@dataclass
class StageStatus:
    name: str
    done: int
    total: int
    last: str | None = None
    active: bool = False
    seconds_per_page: float | None = None

    @property
    def eta_minutes(self) -> float | None:
        if not self.active or not self.seconds_per_page:
            return None
        return (self.total - self.done) * self.seconds_per_page / 60


def _files(folder: Path, pattern: str) -> list[Path]:
    return sorted(folder.glob(pattern)) if folder.exists() else []


def _stage(name: str, files: list[Path], total: int) -> StageStatus:
    if not files:
        return StageStatus(name, 0, total)
    by_time = sorted(files, key=lambda f: f.stat().st_mtime)
    last = by_time[-1]
    active = time.time() - last.stat().st_mtime < _ACTIVE_SECONDS and len(files) < total
    # Ritmo con los últimos 10 archivos: refleja la corrida actual, no las anteriores
    recent = [f.stat().st_mtime for f in by_time[-10:]]
    spp = (recent[-1] - recent[0]) / (len(recent) - 1) if len(recent) > 1 else None
    return StageStatus(name, len(files), total, last.stem, active, spp)


def collection_status(cfg: Config) -> dict:
    raw_manifest = cfg.raw_dir / "manifest.jsonl"
    total = sum(1 for _ in read_jsonl(raw_manifest)) if raw_manifest.exists() else 0
    clean_manifest = cfg.clean_dir / "manifest.jsonl"
    clean_total = sum(1 for _ in read_jsonl(clean_manifest)) if clean_manifest.exists() else total

    stages = [
        _stage("ingesta", [f for f in _files(cfg.raw_dir, "p*.*") if f.suffix != ".jsonl"], total),
        _stage("preproceso", _files(cfg.clean_dir, "p*.png"), total),
        _stage("segmentación (Kraken)", _files(cfg.layout_dir / "kraken", "p*.xml"), clean_total),
        _stage("filtros", _files(cfg.layout_dir, "p*.xml"), clean_total),
        _stage("reconocimiento", _files(cfg.text_dir, "p*.json"), clean_total),
        _stage("vistas de control", _files(cfg.data_dir / "overlay", "p*.jpg"), clean_total),
    ]

    layout_manifest = cfg.layout_dir / "manifest.jsonl"
    layout = list(read_jsonl(layout_manifest)) if layout_manifest.exists() else []
    return {
        "collection": cfg.collection_id,
        "pages": total,
        "stages": stages,
        "suspect": [r["page_id"] for r in layout if r.get("layout_suspect")],
        "lines": sum(r.get("lines", 0) for r in layout),
        "layout_pages": len(layout),
    }


def _bar(done: int, total: int, width: int = 28) -> str:
    filled = round(width * done / total) if total else 0
    return "█" * filled + "░" * (width - filled)


def render(status: dict) -> str:
    out = [f"{status['collection']} · {status['pages']} páginas", ""]
    for s in status["stages"]:
        pct = 100 * s.done / s.total if s.total else 0
        line = f"  {s.name:<22} {_bar(s.done, s.total)} {s.done:>4}/{s.total:<4} {pct:5.1f}%"
        if s.active:
            line += f"  en curso, va por {s.last}"
            if s.eta_minutes is not None:
                line += f" (~{s.seconds_per_page:.0f} s/pág, faltan ~{s.eta_minutes:.0f} min)"
        out.append(line)
    out.append("")
    if status["layout_pages"]:
        out.append(f"  renglones en el manifiesto de segmentación: {status['lines']} "
                   f"en {status['layout_pages']} páginas")
    if status["suspect"]:
        out.append(f"  a revisar a mano ({len(status['suspect'])}): {', '.join(status['suspect'])}")
    return "\n".join(out)


def to_json(status: dict) -> str:
    data = dict(status)
    data["stages"] = [s.__dict__ | {"eta_minutes": s.eta_minutes} for s in status["stages"]]
    return json.dumps(data, ensure_ascii=False, indent=2)
