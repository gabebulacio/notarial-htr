from notarial_htr.gtcheck import check_line


def kinds(text, pred, not_text=False):
    return [k for k, _ in check_line(text, pred, not_text)]


def test_flags_dropped_superscript_and_punctuation():
    assert kinds("Certifico en qto puedo y de dro debo",
                 "Certifico en q^to puedo, y de d^ro debo, q^e") == ["volada", "puntuación"]


def test_clean_line_has_no_findings():
    assert kinds("Certifico en q^to puedo, y de d^ro debo", "Cttifes en g^t pues, y e") == []


def test_empty_and_tags():
    assert kinds("", "B") == ["vacío"]
    assert kinds("", "B", not_text=True) == []
    assert kinds("dixo [tach: que] [rúbrica] [..3..]", "") == []
    assert kinds("dixo [tachado: que", "") == ["marca"]  # sin cerrar
    assert kinds("dixo [tachado: que]", "") == ["marca"]  # marca desconocida
