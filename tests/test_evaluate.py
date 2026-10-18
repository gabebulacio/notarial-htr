import json

import pytest

from notarial_htr.evaluate import Score, edit_distance, evaluate


def test_edit_distance():
    assert edit_distance("quatro", "quatro") == 0
    assert edit_distance("quatro", "cuatro") == 1
    assert edit_distance("", "abc") == 3
    assert edit_distance(["dixo", "que"], ["dixo", "q^e", "no"]) == 2


def test_score_normalizes_whitespace_and_unicode():
    s = Score()
    s.add("ãno  de", "ãno de")
    assert s.cer == 0 and s.wer == 0


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_evaluate_splits_test_and_train_pages(tmp_path):
    text, gt = tmp_path / "text", tmp_path / "gt"
    for pid, pred, ref in [("p0001", "quatro", "quatro"), ("p0002", "cuatra", "quatro")]:
        _write(text / f"{pid}.json", {"lines": [{"id": "l1", "text": pred}]})
        _write(gt / f"{pid}.json", {"page_id": pid, "status": "corregida",
                                    "lines": [{"id": "l1", "text": ref}]})
    _write(gt / "p0003.json", {"page_id": "p0003", "status": "en_curso", "lines": []})
    scores = evaluate(text, gt, test_pages={"p0002"})
    assert scores["entrenamiento"].cer == 0
    assert scores["evaluación"].cer == pytest.approx(2 / 6)
    assert scores["evaluación"].pages == ["p0002"]
