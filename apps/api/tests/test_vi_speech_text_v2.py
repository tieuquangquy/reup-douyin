from src.tts_pipeline.services.speech_text import build_vietnamese_speech_text


def test_v2_normalizer_expands_temporal_numeric_and_currency_tokens():
    result = build_vietnamese_speech_text("Ngày 12/08/2026 lúc 8:30, giá 25.000đ, giảm 10%.")
    assert result.display_text == "Ngày 12/08/2026 lúc 8:30, giá 25.000đ, giảm 10%."
    assert "ngày mười hai tháng tám năm hai nghìn không trăm hai mươi sáu" in result.speech_text
    assert "tám giờ ba mươi phút" in result.speech_text
    assert "hai mươi lăm nghìn đồng" in result.speech_text
    assert "phần trăm" in result.speech_text


def test_v2_normalizer_handles_ranges_models_urls_and_glossary():
    result = build_vietnamese_speech_text(
        "RTX-4090 chạy 10–15x, OpenAI xem https://example.com/a và mail ops@example.com",
        pronunciation_glossary={"OpenAI": "ô pen ây ai"},
    )
    assert result.display_text.startswith("RTX-4090")
    assert "http" not in result.speech_text.casefold()
    assert "@" not in result.speech_text
    assert "từ mười đến mười lăm" in result.speech_text
    assert "apply_pronunciation_glossary" in result.actions
    assert "expand_url" in result.actions
    assert "expand_email" in result.actions
