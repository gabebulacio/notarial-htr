import cv2
import numpy as np
import pytest

from notarial_htr.config import PreprocessConfig
from notarial_htr.preprocess import estimate_skew, find_gutter, ink_mask, process_page, rotate


def _fake_page(w=1200, h=1600, lines=20, x0=100, x1=None):
    """Página sintética: renglones de 'tinta' en blanco y negro."""
    img = np.full((h, w), 235, np.uint8)
    x1 = x1 or w - 100
    for i in range(lines):
        y = 120 + i * 70
        for x in range(x0, x1, 40):
            cv2.rectangle(img, (x, y), (x + 28, y + 18), 40, -1)
    return img


@pytest.mark.parametrize("true_angle", [-2.5, -1.0, 0.0, 1.5, 3.0])
def test_estimate_skew_recovers_rotation(true_angle):
    page = rotate(_fake_page(), true_angle)
    skew = estimate_skew(ink_mask(page), max_angle=4.0, step=0.1)
    assert skew.angle == pytest.approx(-true_angle, abs=0.3)
    assert skew.confident or true_angle == 0.0


def test_skew_beyond_range_is_not_trusted():
    # Apenas fuera del rango (lo que se ve en fotos en perspectiva); mucho más lejos, la
    # página sintética periódica vuelve a "alinear" en otro ángulo y el test no tiene sentido
    page = rotate(_fake_page(), 5.0)
    skew = estimate_skew(ink_mask(page), max_angle=4.0, step=0.1)
    assert not skew.confident


def test_blank_page_detected():
    blank = np.full((1600, 1200), 230, np.uint8)
    parts = process_page(blank, PreprocessConfig())
    assert [p.meta["kind"] for p in parts] == ["blank"]


def test_spread_split_at_gutter():
    left = _fake_page(w=1000, x0=80, x1=900)
    right = _fake_page(w=1000, x0=100, x1=920)
    spread = np.hstack([left, right])
    assert find_gutter(spread) == pytest.approx(1000, abs=80)
    parts = process_page(spread, PreprocessConfig())
    assert [p.suffix for p in parts] == ["a", "b"]


def test_single_wide_page_not_split():
    # Página apaisada pero con renglones continuos: no hay medianil
    wide = _fake_page(w=2000, x0=80, x1=1920)
    assert find_gutter(wide) is None
