"""Limpieza de imagen: enderezado, contraste, páginas en blanco y dobles páginas.

Todo es determinístico y queda registrado en el manifiesto `clean/manifest.jsonl`;
la imagen original en `raw/` nunca se toca.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import PreprocessConfig
from .manifest import read_jsonl, write_jsonl

# Ancho de trabajo para las estimaciones (inclinación, medianil); acelera sin perder precisión
_ANALYSIS_WIDTH = 1000


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def ink_mask(gray: np.ndarray) -> np.ndarray:
    """Máscara binaria (255 = tinta) robusta a iluminación despareja de fotos de celular."""
    block = max(15, (min(gray.shape) // 40) | 1)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 15
    )


def ink_ratio(mask: np.ndarray) -> float:
    return float(np.count_nonzero(mask)) / mask.size


def _resize_to_width(img: np.ndarray, width: int) -> np.ndarray:
    if img.shape[1] <= width:
        return img
    scale = width / img.shape[1]
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def rotate(img: np.ndarray, angle: float, border: int | None = None) -> np.ndarray:
    """Rota `angle` grados (positivo = antihorario) manteniendo el tamaño."""
    if abs(angle) < 1e-6:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    if border is None:
        return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_NEAREST,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def _profile_score(mask: np.ndarray, angle: float) -> float:
    # Con los renglones horizontales, el perfil por filas alterna picos y valles marcados
    rows = rotate(mask, angle, border=0).sum(axis=1, dtype=np.float64)
    return float(np.square(np.diff(rows)).sum())


@dataclass(frozen=True)
class SkewEstimate:
    angle: float
    gain: float  # mejora relativa del perfil frente a no rotar
    confident: bool


def estimate_skew(mask: np.ndarray, max_angle: float, step: float,
                  min_gain: float = 0.05) -> SkewEstimate:
    """Ángulo (grados) que hay que rotar para dejar los renglones horizontales.

    Búsqueda gruesa a 0.5° y después fina con `step` alrededor del mejor. En fotos de
    libros abiertos los renglones se curvan por la perspectiva y no hay un único ángulo:
    si el óptimo cae en el borde del rango o casi no mejora frente a 0°, la estimación
    no es confiable y conviene no rotar (la geometría fina la resuelve la segmentación
    por renglón).
    """
    small = _resize_to_width(mask, _ANALYSIS_WIDTH)
    coarse = np.arange(-max_angle, max_angle + 1e-9, 0.5)
    best = max(coarse, key=lambda a: _profile_score(small, a))
    fine = np.arange(max(best - 0.5, -max_angle), min(best + 0.5, max_angle) + 1e-9, step)
    best = float(max(fine, key=lambda a: _profile_score(small, a)))
    base = _profile_score(small, 0.0)
    gain = _profile_score(small, best) / base - 1 if base else 0.0
    at_limit = abs(best) >= max_angle - step
    return SkewEstimate(round(best, 2), round(gain, 3), gain >= min_gain and not at_limit)


def find_gutter(gray: np.ndarray, min_contrast: float = 0.35) -> int | None:
    """Columna del medianil de una doble página, o None si no hay un valle claro.

    Busca la columna con menos tinta en la franja central (35-65 % del ancho).
    """
    small = _resize_to_width(gray, _ANALYSIS_WIDTH)
    mask = ink_mask(small)
    cols = mask.sum(axis=0, dtype=np.float64)
    cols = np.convolve(cols, np.ones(15) / 15, mode="same")
    w = len(cols)
    lo, hi = int(w * 0.35), int(w * 0.65)
    centre = cols[lo:hi]
    valley = float(centre.min())
    typical = float(np.median(cols[int(w * 0.1):int(w * 0.9)]))
    if typical == 0 or valley > typical * min_contrast:
        return None
    x = lo + int(centre.argmin())
    return round(x * gray.shape[1] / w)


def enhance(gray: np.ndarray, clip: float, tile: int) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile))
    return clahe.apply(gray)


@dataclass
class PagePart:
    image: np.ndarray
    suffix: str  # "" página simple; "a"/"b" mitades izquierda/derecha
    meta: dict


def process_page(img: np.ndarray, cfg: PreprocessConfig) -> list[PagePart]:
    gray = to_gray(img)
    mask = ink_mask(gray)
    ratio = ink_ratio(mask)
    if ratio < cfg.blank_ink_ratio:
        return [PagePart(gray, "", {"kind": "blank", "ink_ratio": round(ratio, 5)})]

    h, w = gray.shape
    halves = [(gray, "")]
    gutter = None
    if w / h >= cfg.spread_aspect:
        gutter = find_gutter(gray)
        if gutter is not None:
            halves = [(gray[:, :gutter], "a"), (gray[:, gutter:], "b")]

    parts = []
    for half, suffix in halves:
        skew = estimate_skew(ink_mask(half), cfg.deskew_max_angle, cfg.deskew_step)
        angle = skew.angle if skew.confident else 0.0
        out = rotate(half, angle)
        if cfg.clahe_clip > 0:
            out = enhance(out, cfg.clahe_clip, cfg.clahe_tile)
        parts.append(PagePart(out, suffix, {
            "kind": "spread_half" if suffix else "page",
            "ink_ratio": round(ratio, 5),
            "skew_deg": angle,
            "skew_estimate": skew.angle,
            "skew_gain": skew.gain,
            "skew_confident": skew.confident,
            "gutter_x": gutter,
        }))
    return parts


def preprocess_collection(raw_dir: Path, clean_dir: Path, cfg: PreprocessConfig,
                          pages: set[str] | None = None) -> list[dict]:
    clean_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for rec in read_jsonl(raw_dir / "manifest.jsonl"):
        if pages and rec["page_id"] not in pages:
            continue
        img = cv2.imread(str(raw_dir / rec["file"]), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"No se pudo leer {rec['file']}")
        for part in process_page(img, cfg):
            name = f"{rec['page_id']}{part.suffix}.png"
            cv2.imwrite(str(clean_dir / name), part.image)
            records.append({"page_id": rec["page_id"] + part.suffix, "source": rec["file"],
                            "file": name, **part.meta})
    # Una corrida parcial (--pages) actualiza solo esas páginas y conserva el resto
    manifest = clean_dir / "manifest.jsonl"
    done = {r["source"] for r in records}
    kept = [r for r in read_jsonl(manifest) if r["source"] not in done] if manifest.exists() else []
    write_jsonl(manifest, sorted(kept + records, key=lambda r: r["page_id"]))
    return records
