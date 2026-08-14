from scripts.run_phase2_only import _is_symbol_dominant_non_text


def test_symbol_dominant_icon_ocr_is_not_review_text() -> None:
    assert _is_symbol_dominant_non_text("8=") is True
    assert _is_symbol_dominant_non_text("=") is True


def test_numeric_values_and_real_text_are_preserved() -> None:
    assert _is_symbol_dominant_non_text("8%") is False
    assert _is_symbol_dominant_non_text("120g") is False
    assert _is_symbol_dominant_non_text("è‡ªåŠ¨") is False

