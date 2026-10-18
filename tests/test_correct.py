import json

import cv2
import numpy as np
import pytest

from notarial_htr.correct import Store
from notarial_htr.manifest import write_jsonl

BOUNDARY = [[10, 10], [200, 10], [200, 60], [10, 60]]


@pytest.fixture
def store(tmp_path):
    clean, layout, text, gt = (tmp_path / d for d in ("clean", "layout", "text", "gt"))
    clean.mkdir()
    cv2.imwrite(str(clean / "p0001.png"), np.full((100, 300), 220, np.uint8))
    write_jsonl(layout / "manifest.jsonl", [{"page_id": "p0001", "image": "p0001.png",
                                             "layout_suspect": False}])
    (layout / "debug").mkdir()
    (layout / "debug" / "p0001.json").write_text(json.dumps(
        {"lines": [{"id": "l1", "boundary": BOUNDARY}, {"id": "l2", "boundary": BOUNDARY}]}))
    text.mkdir()
    (text / "p0001.json").write_text(json.dumps({"model": "m", "lines": [
        {"id": "l1", "text": "quatro", "char_conf": [1] * 6, "mean_conf": 0.9},
        {"id": "l2", "text": "bida", "char_conf": [1] * 4, "mean_conf": 0.7}]}))
    write_jsonl(text / "manifest.jsonl", [{"page_id": "p0001", "lines": 2, "mean_conf": 0.8,
                                           "low_conf_lines": 1}])
    return Store(clean, layout, text, gt, "Prueba")


def test_save_marks_edited_lines_and_reloads(store):
    out = store.save("p0001", {"status": "corregida", "lines": [
        {"id": "l1", "text": "quatro"}, {"id": "l2", "text": "vida", "doubtful": True}]})
    assert out == {"ok": True, "status": "corregida", "edited": 1}
    page = store.page("p0001")
    assert [line["text"] for line in page["lines"]] == ["quatro", "vida"]
    assert page["lines"][1]["doubtful"] and page["lines"][1]["prediction"] == "bida"
    assert store.pages()[0]["status"] == "corregida"


def test_save_rejects_unknown_line_and_status(store):
    with pytest.raises(ValueError):
        store.save("p0001", {"lines": [{"id": "otro", "text": "x"}]})
    with pytest.raises(ValueError):
        store.save("p0001", {"status": "lista", "lines": []})


def test_crop_returns_png(store):
    png = store.crop("p0001", "l1")
    assert png[:4] == b"\x89PNG"
    assert store.crop("p0001", "no-existe") is None


def test_scores_split_test_and_train_and_report_partial_page(store):
    store.test_pages = frozenset({"p0001"})
    assert store.scores()["test"]["lines"] == 0
    store.save("p0001", {"status": "en_curso", "lines": [
        {"id": "l1", "text": "quatro"}, {"id": "l2", "text": "vida"}]})
    s = store.scores("p0001")
    assert s["test"]["lines"] == 0 and s["test_total"] == 1  # en curso: no entra en los totales
    assert s["page"]["status"] == "en_curso" and s["page"]["cer"] == pytest.approx(1 / 10)
    store.save("p0001", {"status": "corregida", "lines": [
        {"id": "l1", "text": "quatro"}, {"id": "l2", "text": "vida"}]})
    s = store.scores()
    assert s["test"]["pages"] == 1 and s["train"]["pages"] == 0
    assert store.pages()[0]["test"] and store.page("p0001")["test"]


def test_not_text_lines_are_saved_and_left_out_of_scores(store):
    store.save("p0001", {"status": "corregida", "lines": [
        {"id": "l1", "text": "quatro"}, {"id": "l2", "text": "bida", "not_text": True}]})
    assert store.page("p0001")["lines"][1]["not_text"] is True
    s = store.scores("p0001")
    assert s["page"]["lines"] == 1 and s["page"]["chars"] == 6


def test_reviewed_is_kept_across_desktop_saves(store):
    store.save("p0001", {"status": "en_curso", "lines": [
        {"id": "l1", "text": "quatro", "reviewed": True}, {"id": "l2", "text": "bida"}]})
    # El editor de escritorio no manda `reviewed`: no debe borrar lo revisado en el celular
    store.save("p0001", {"status": "en_curso", "lines": [
        {"id": "l1", "text": "quatro"}, {"id": "l2", "text": "vida"}]})
    assert [line["reviewed"] for line in store.page("p0001")["lines"]] == [True, False]
    store.save("p0001", {"status": "corregida", "lines": [
        {"id": "l1", "text": "quatro"}, {"id": "l2", "text": "vida"}]})
    assert all(line["reviewed"] for line in store.page("p0001")["lines"])


def test_lan_requires_token_from_other_devices(store):
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from notarial_htr.correct import make_handler

    handler = make_handler(store, token="secreto")
    handler._local = lambda self: False  # simular un pedido desde el celular
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(f"{base}/api/pages")
        assert err.value.code == 403
        with urllib.request.urlopen(f"{base}/api/pages?t=secreto") as r:
            assert r.status == 200 and "htr_t=secreto" in r.headers["Set-Cookie"]
        req = urllib.request.Request(f"{base}/m", headers={"Cookie": "htr_t=secreto"})
        with urllib.request.urlopen(req) as r:
            assert b"id=\"feed\"" in r.read()
    finally:
        server.shutdown()
