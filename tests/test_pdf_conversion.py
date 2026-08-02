from pathlib import Path

import pytest

from pdf_conversion import (
    ScannedPDFError,
    convert_local_document,
    reconstruct_positioned_line,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"
PERSIAN_PDF = FIXTURES / "persian_rtl_multpage.pdf"
SCANNED_PDF = FIXTURES / "scanned_image_only.pdf"
EXPECTED = "گزارش اولیه گزینه‌های ورود مینو فارس به حوزه دانش‌بنیان"


def test_positioned_words_reconstruct_rtl_and_preserve_ltr_run():
    words = [
        (500, 10, 550, 20, "نسخه", 0, 0, 0),
        (390, 10, 435, 20, "Python", 0, 0, 1),
        (440, 10, 475, 20, "3.13", 0, 0, 2),
        (300, 10, 380, 20, "برای", 0, 0, 3),
    ]
    line, used = reconstruct_positioned_line(words)
    assert used
    assert line == "نسخه Python 3.13 برای"


def test_persian_pdf_uses_same_application_conversion_path():
    result = convert_local_document(PERSIAN_PDF)
    assert EXPECTED in result.markdown
    assert "نسخه Python 3.13 برای Windows 10 نصب شد." in result.markdown
    assert "گزارش KPI ماه July 2026 آماده است." in result.markdown
    assert "سال ۱۴۰۵" in result.markdown
    assert "گزارش عملکرد (نسخه نهایی)" in result.markdown
    assert "https://example.com/page" in result.markdown
    assert "user@example.com" in result.markdown
    assert result.pdf_diagnostics is not None
    assert result.pdf_diagnostics.repaired_lines >= 1


def test_persian_pdf_plain_mode_has_no_html_wrappers():
    result = convert_local_document(PERSIAN_PDF, rtl_formatting="Plain Markdown")
    assert '<div dir="rtl"' not in result.markdown


def test_persian_pdf_html_mode_adds_safe_wrapper():
    result = convert_local_document(PERSIAN_PDF, rtl_formatting="HTML RTL blocks")
    assert '<div dir="rtl" align="right">' in result.markdown
    assert "https://example.com/page" in result.markdown


def test_scanned_pdf_requires_ocr():
    with pytest.raises(ScannedPDFError, match="requires OCR"):
        convert_local_document(SCANNED_PDF)


def test_english_pdf_conversion_is_unaffected():
    english_pdf = Path("packages/markitdown/tests/test_files/test.pdf")
    result = convert_local_document(english_pdf)
    assert "Introduction" in result.markdown
    assert result.pdf_diagnostics is not None
    assert result.pdf_diagnostics.rtl_character_ratio == 0
