from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PreprocessConfig:
    deskew_max_angle: float = 4.0
    deskew_step: float = 0.1
    blank_ink_ratio: float = 0.004
    spread_aspect: float = 1.15
    clahe_clip: float = 2.0
    clahe_tile: int = 16


@dataclass(frozen=True)
class LayoutConfig:
    # Detectar el borde físico del papel y descartar lo que queda del otro lado
    detect_paper_edges: bool = True
    # Franja de cada borde de la imagen donde puede aparecer la página enfrentada
    edge_frac: float = 0.08
    # Un renglón de borde se descarta si mide menos que esta fracción del bloque
    short_frac: float = 0.25
    # Unión de renglones partidos: tolerancia vertical (en interlineados) y hueco máximo
    merge_y_frac: float = 0.35
    merge_gap_frac: float = 0.06
    # Segmentación sospechosa: al menos esta proporción de renglones "muy cortos" (menos de
    # `tiny_line_frac` del ancho del bloque). Los pliegues y manchas dan muchos trazos cortos;
    # las listas de aranceles, con columnas, quedan por debajo (~0.43 en p0063)
    suspect_tiny_ratio: float = 0.5
    tiny_line_frac: float = 0.15


@dataclass(frozen=True)
class RecognitionConfig:
    # Modelo de Kraken (.mlmodel/.safetensors); el hash fija la versión exacta usada
    model: str = "models/base/mccatmus/McCATMuS_nfd_nofix_V1.mlmodel"
    model_sha256: str | None = None
    # McCATMuS predice en NFD; el resto del proyecto trabaja en NFC
    unicode_form: str = "NFC"
    # Confianza media por renglón por debajo de la cual el renglón va a revisión
    low_conf: float = 0.8


@dataclass(frozen=True)
class Config:
    collection_id: str
    title: str
    source_pdf: Path
    data_dir: Path
    years: tuple[int, int] | None = None
    place: str | None = None
    record_type: str | None = None
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    # Correcciones humanas: dentro del repo y versionadas (ver correct.py)
    ground_truth_dir: Path | None = None
    # Páginas que nunca se usan para entrenar: miden el error real del modelo
    test_pages: tuple[str, ...] = ()

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def clean_dir(self) -> Path:
        return self.data_dir / "clean"

    @property
    def layout_dir(self) -> Path:
        return self.data_dir / "layout"

    @property
    def text_dir(self) -> Path:
        return self.data_dir / "text"


def load_config(path: str | Path, root: str | Path | None = None) -> Config:
    """Lee la configuración de una colección.

    `data_dir` relativo se resuelve contra `root` (por defecto, el directorio actual)
    para que los datos queden fuera de `configs/`.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    col = raw["collection"]
    root = Path(root) if root else Path.cwd()
    data_dir = Path(raw["data_dir"])
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    years = tuple(col["years"]) if col.get("years") else None
    return Config(
        collection_id=col["id"],
        title=col["title"],
        source_pdf=Path(raw["source"]["pdf"]),
        data_dir=data_dir,
        years=years,
        place=col.get("place"),
        record_type=col.get("record_type"),
        preprocess=PreprocessConfig(**raw.get("preprocess", {})),
        layout=LayoutConfig(**raw.get("layout", {})),
        recognition=RecognitionConfig(**raw.get("recognition", {})),
        ground_truth_dir=root / raw.get("ground_truth_dir", f"ground_truth/{col['id']}"),
        test_pages=tuple(raw.get("evaluation", {}).get("test_pages", [])),
    )
