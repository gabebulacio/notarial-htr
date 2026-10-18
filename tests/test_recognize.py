import unicodedata

from notarial_htr.recognize import line_record


def test_nfd_output_is_recomposed_with_min_confidence():
    # El modelo predice "año" en NFD: a, n, tilde combinante, o
    pred = unicodedata.normalize("NFD", "año")
    rec = line_record("l1", pred, [0.9, 0.95, 0.6, 0.99], "NFC")
    assert rec["text"] == "año"
    assert rec["char_conf"] == [0.9, 0.6, 0.99]
    assert rec["conf"] == 0.6
    assert rec["mean_conf"] == round((0.9 + 0.6 + 0.99) / 3, 4)


def test_empty_line():
    rec = line_record("l2", "", [], "NFC")
    assert rec["text"] == "" and rec["conf"] == 0.0
