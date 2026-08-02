from rtl_text_normalizer import (
    RTL_FORMAT_HTML,
    RTL_FORMAT_PLAIN,
    analyze_rtl_line,
    normalize_rtl_line,
    normalize_rtl_text,
    normalize_rtl_text_with_diagnostics,
)


CORRECT_PERSIAN = "گزارش اولیه گزینه‌های ورود مینو فارس به حوزه دانش‌بنیان"
REVERSED_PERSIAN = "ناینبشناد هزوح هب سراف ونیم دورو یاههنیزگ هیلوا شرازگ"


def test_correct_persian_remains_unchanged():
    assert normalize_rtl_line(CORRECT_PERSIAN) == CORRECT_PERSIAN


def test_fully_reversed_persian_line_is_repaired():
    assert normalize_rtl_line(REVERSED_PERSIAN) == CORRECT_PERSIAN


def test_reversed_line_has_high_confidence():
    analysis = analyze_rtl_line(REVERSED_PERSIAN)
    assert analysis.should_repair
    assert analysis.corruption_confidence >= 0.9


def test_mixed_persian_python_windows_remains_unchanged():
    value = "نسخه Python 3.13 برای Windows 10 نصب شد."
    assert normalize_rtl_line(value) == value


def test_mixed_persian_kpi_month_remains_unchanged():
    value = "گزارش KPI ماه July 2026 آماده است."
    assert normalize_rtl_line(value) == value


def test_urls_and_email_addresses_are_not_reversed():
    value = "https://example.com/page user@example.com"
    assert normalize_rtl_line(value) == value


def test_persian_numbers_remain_readable():
    assert normalize_rtl_line("سال ۱۴۰۵") == "سال ۱۴۰۵"
    assert normalize_rtl_line("نسخه 1.2.3") == "نسخه 1.2.3"


def test_parentheses_remain_readable():
    value = "گزارش عملکرد (نسخه نهایی)"
    assert normalize_rtl_line(value) == value


def test_duplicate_correct_and_reversed_lines_keep_only_correct_line():
    result = normalize_rtl_text_with_diagnostics(f"{CORRECT_PERSIAN}\n{REVERSED_PERSIAN}")
    assert result.text == CORRECT_PERSIAN
    assert result.diagnostics.duplicate_reversed_lines_removed == 1


def test_english_only_text_is_unchanged():
    value = "English text (version 1.2.3) stays exactly the same."
    assert normalize_rtl_text(value) == value


def test_correct_arabic_remains_logical():
    assert normalize_rtl_line("هذا تقرير عربي واضح") == "هذا تقریر عربی واضح"


def test_reversed_arabic_is_repaired():
    assert normalize_rtl_line("حضاو يبرع ريرقت اذه") == "هذا تقریر عربی واضح"


def test_common_arabic_variants_are_normalized():
    assert normalize_rtl_line("كتاب عربي") == "کتاب عربی"


def test_arabic_presentation_forms_become_base_unicode():
    assert normalize_rtl_line("ﮒﺯﺍﺭﺵ") == "گزارش"


def test_low_confidence_rtl_line_is_preserved():
    value = "آلفا بتا گاما"
    assert normalize_rtl_line(value) == value


def test_plain_markdown_adds_no_html_wrapper():
    result = normalize_rtl_text_with_diagnostics(CORRECT_PERSIAN, RTL_FORMAT_PLAIN)
    assert '<div dir="rtl"' not in result.text
    assert result.diagnostics.html_wrappers_added == 0


def test_html_mode_wraps_rtl_paragraph_but_not_url_or_english():
    value = f"{CORRECT_PERSIAN}\n\nhttps://example.com/page\n\nEnglish paragraph"
    result = normalize_rtl_text_with_diagnostics(value, RTL_FORMAT_HTML)
    assert result.text.count('<div dir="rtl" align="right">') == 1
    assert "https://example.com/page" in result.text
    assert "English paragraph" in result.text


def test_html_mode_does_not_wrap_markdown_table():
    table = "| شاخص | مقدار |\n| --- | --- |\n| سال | ۱۴۰۵ |"
    result = normalize_rtl_text_with_diagnostics(table, RTL_FORMAT_HTML)
    assert '<div dir="rtl"' not in result.text
