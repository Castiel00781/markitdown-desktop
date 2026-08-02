from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw


FIXTURE_DIRECTORY = Path(__file__).resolve().parent / "fixtures"
FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/tahoma.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)


def _font_path() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("A Windows font with Arabic/Persian coverage was not found.")


def _insert(page, point, text, *, size=13) -> None:
    page.insert_text(point, text, fontname="RTLFixture", fontsize=size)


def create_persian_pdf(destination: Path) -> None:
    document = pymupdf.open()
    font_path = _font_path()

    page = document.new_page(width=595, height=842)
    page.insert_font(fontname="RTLFixture", fontfile=font_path)
    _insert(page, (55, 70), "ناینبشناد هزوح هب سراف ونیم دورو یاههنیزگ هیلوا شرازگ", size=16)
    _insert(page, (55, 115), "نسخه Python 3.13 برای Windows 10 نصب شد.")
    _insert(page, (55, 150), "گزارش KPI ماه July 2026 آماده است.")
    _insert(page, (55, 185), "سال ۱۴۰۵ - نسخه 1.2.3")
    _insert(page, (55, 220), "گزارش عملکرد (نسخه نهایی)")
    _insert(page, (55, 255), "https://example.com/page user@example.com")

    # A small positioned table. Existing MarkItDown extraction should retain
    # rows while the app-level normalizer repairs only corrupted RTL content.
    table_rows = (
        ("مقدار", "شاخص", "ردیف"),
        ("Python 3.13", "نسخه", "۱"),
        ("۱۴۰۵", "سال", "۲"),
    )
    for row_index, row in enumerate(table_rows):
        y = 330 + row_index * 30
        for x, cell in zip((90, 280, 470), row):
            _insert(page, (x, y), cell, size=11)

    page = document.new_page(width=595, height=842)
    page.insert_font(fontname="RTLFixture", fontfile=font_path)
    logical_words = ["گزارش", "اولیه", "گزینه‌های", "ورود", "مینو", "فارس", "به", "حوزه", "دانش‌بنیان"]
    x_positions = [500, 440, 370, 315, 265, 215, 175, 125, 45]
    # Insert in physical left-to-right order. Coordinate-aware extraction can
    # reconstruct the intended logical right-to-left reading order.
    for word, x in reversed(list(zip(logical_words, x_positions))):
        _insert(page, (x, 90), word, size=12)
    _insert(page, (55, 145), "این صفحه دوم گزارش است.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(destination, garbage=4, deflate=True)
    document.close()


def create_scanned_pdf(destination: Path) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    draw.text((120, 180), "SCANNED IMAGE-ONLY PAGE", fill="black")
    image_data = BytesIO()
    image.save(image_data, format="PNG")

    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=image_data.getvalue())
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(destination, garbage=4, deflate=True)
    document.close()


if __name__ == "__main__":
    create_persian_pdf(FIXTURE_DIRECTORY / "persian_rtl_multpage.pdf")
    create_scanned_pdf(FIXTURE_DIRECTORY / "scanned_image_only.pdf")
