from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markitdown import MarkItDown

from rtl_text_normalizer import (
    NormalizationDiagnostics,
    RTL_FORMAT_AUTOMATIC,
    logical_quality_score,
    normalize_rtl_word,
    normalize_rtl_text_with_diagnostics,
    rtl_character_ratio,
)


class ScannedPDFError(RuntimeError):
    pass


@dataclass
class PDFConversionDiagnostics:
    rtl_character_ratio: float = 0.0
    corruption_detected: bool = False
    confidence_score: float = 0.0
    extraction_backend_selected: str = "MarkItDown (pdfminer/pdfplumber)"
    alternate_backend_attempted: bool = False
    word_coordinate_reconstruction_used: bool = False
    repaired_lines: int = 0
    duplicate_reversed_lines_removed: int = 0
    html_wrappers_added: int = 0
    scanned_or_image_only: bool = False
    backend_scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentConversionResult:
    markdown: str
    pdf_diagnostics: PDFConversionDiagnostics | None = None


def _has_meaningful_text(text: str) -> bool:
    return sum(character.isalnum() for character in text) >= 8


def _normalization_quality(text: str, diagnostics: NormalizationDiagnostics) -> float:
    score = logical_quality_score(text)
    score += min(len(text), 5000) / 50000
    score -= diagnostics.repaired_lines * 0.05
    characters = list(text)
    glued_script_transitions = sum(
        1
        for first, second in zip(characters, characters[1:])
        if not first.isspace()
        and not second.isspace()
        and (
            (rtl_character_ratio(first) > 0 and second.isascii() and second.isalnum())
            or (first.isascii() and first.isalnum() and rtl_character_ratio(second) > 0)
        )
    )
    score -= glued_script_transitions * 2.0
    return score


def _is_latin_or_number(token: str) -> bool:
    has_latin = any("A" <= character <= "Z" or "a" <= character <= "z" for character in token)
    has_number = any(character.isdigit() for character in token)
    has_rtl = rtl_character_ratio(token) > 0
    return not has_rtl and (has_latin or has_number)


def _restore_ltr_runs(tokens: list[str]) -> list[str]:
    restored = tokens[:]
    index = 0
    while index < len(restored):
        if not _is_latin_or_number(restored[index]):
            index += 1
            continue
        end = index + 1
        has_latin = any(character.isascii() and character.isalpha() for character in restored[index])
        while end < len(restored) and _is_latin_or_number(restored[end]):
            has_latin = has_latin or any(
                character.isascii() and character.isalpha() for character in restored[end]
            )
            end += 1
        if has_latin and end - index > 1:
            restored[index:end] = reversed(restored[index:end])
        index = end
    return restored


def reconstruct_positioned_line(words: list[tuple[Any, ...]]) -> tuple[str, bool]:
    if not words:
        return "", False
    raw_tokens = [normalize_rtl_word(str(word[4])) for word in words]
    line_text = " ".join(raw_tokens)
    if rtl_character_ratio(line_text) < 0.45:
        ordered = sorted(words, key=lambda word: float(word[0]))
        return " ".join(normalize_rtl_word(str(word[4])) for word in ordered), False
    left_to_right = " ".join(
        normalize_rtl_word(str(word[4])) for word in sorted(words, key=lambda word: float(word[0]))
    )
    right_to_left_words = sorted(words, key=lambda word: float(word[0]), reverse=True)
    right_to_left_tokens = _restore_ltr_runs(
        [normalize_rtl_word(str(word[4])) for word in right_to_left_words]
    )
    right_to_left = " ".join(right_to_left_tokens)
    if logical_quality_score(left_to_right) > logical_quality_score(right_to_left) + 0.2:
        return left_to_right, True
    return right_to_left, True


def extract_with_pymupdf(pdf_path: Path) -> tuple[str, bool]:
    import pymupdf

    pages: list[str] = []
    coordinate_reconstruction_used = False
    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            words = page.get_text("words", sort=False)
            line_groups: list[list[tuple[Any, ...]]] = []
            for word in sorted(words, key=lambda item: (float(item[1]), float(item[0]))):
                if not line_groups:
                    line_groups.append([word])
                    continue
                current_top = sum(float(item[1]) for item in line_groups[-1]) / len(line_groups[-1])
                tolerance = max(3.0, (float(word[3]) - float(word[1])) * 0.35)
                if abs(float(word[1]) - current_top) <= tolerance:
                    line_groups[-1].append(word)
                else:
                    line_groups.append([word])
            lines: list[str] = []
            for group in line_groups:
                line, used_coordinates = reconstruct_positioned_line(group)
                if line.strip():
                    lines.append(line.strip())
                coordinate_reconstruction_used = coordinate_reconstruction_used or used_coordinates
            if lines:
                pages.append(f"<!-- Page {page_number} -->\n\n" + "\n".join(lines))
    return "\n\n".join(pages), coordinate_reconstruction_used


def _diagnostics_from_normalization(
    normalization: NormalizationDiagnostics,
) -> PDFConversionDiagnostics:
    return PDFConversionDiagnostics(
        rtl_character_ratio=normalization.rtl_character_ratio,
        corruption_detected=normalization.corruption_detected,
        confidence_score=normalization.confidence_score,
        repaired_lines=normalization.repaired_lines,
        duplicate_reversed_lines_removed=normalization.duplicate_reversed_lines_removed,
        html_wrappers_added=normalization.html_wrappers_added,
    )


def convert_pdf_document(
    pdf_path: Path,
    *,
    improve_rtl: bool = True,
    rtl_formatting: str = RTL_FORMAT_AUTOMATIC,
) -> DocumentConversionResult:
    converter = MarkItDown()
    baseline = converter.convert(pdf_path).text_content

    if not _has_meaningful_text(baseline):
        alternate, coordinates_used = extract_with_pymupdf(pdf_path)
        if not _has_meaningful_text(alternate):
            raise ScannedPDFError("This PDF appears to be scanned and requires OCR.")
        baseline = alternate
        baseline_backend = "PyMuPDF positioned words"
    else:
        coordinates_used = False
        baseline_backend = "MarkItDown (pdfminer/pdfplumber)"

    if not improve_rtl or rtl_character_ratio(baseline) < 0.12:
        return DocumentConversionResult(
            baseline,
            PDFConversionDiagnostics(
                rtl_character_ratio=rtl_character_ratio(baseline),
                extraction_backend_selected=baseline_backend,
                word_coordinate_reconstruction_used=coordinates_used,
            ),
        )

    baseline_result = normalize_rtl_text_with_diagnostics(baseline, rtl_formatting)
    diagnostics = _diagnostics_from_normalization(baseline_result.diagnostics)
    diagnostics.extraction_backend_selected = baseline_backend
    diagnostics.word_coordinate_reconstruction_used = coordinates_used
    baseline_score = _normalization_quality(baseline_result.text, baseline_result.diagnostics)
    diagnostics.backend_scores[baseline_backend] = baseline_score

    selected_text = baseline_result.text
    if baseline_result.diagnostics.corruption_detected:
        diagnostics.alternate_backend_attempted = True
        alternate, alternate_coordinates = extract_with_pymupdf(pdf_path)
        diagnostics.word_coordinate_reconstruction_used = (
            diagnostics.word_coordinate_reconstruction_used or alternate_coordinates
        )
        alternate_result = normalize_rtl_text_with_diagnostics(alternate, rtl_formatting)
        alternate_score = _normalization_quality(alternate_result.text, alternate_result.diagnostics)
        diagnostics.backend_scores["PyMuPDF positioned words"] = alternate_score
        # The alternate must be materially better before sacrificing
        # MarkItDown's stronger Markdown table and paragraph preservation.
        if _has_meaningful_text(alternate) and alternate_score > baseline_score + 3.0:
            selected_text = alternate_result.text
            diagnostics = _diagnostics_from_normalization(alternate_result.diagnostics)
            diagnostics.extraction_backend_selected = "PyMuPDF positioned words"
            diagnostics.alternate_backend_attempted = True
            diagnostics.word_coordinate_reconstruction_used = alternate_coordinates
            diagnostics.backend_scores[baseline_backend] = baseline_score
            diagnostics.backend_scores["PyMuPDF positioned words"] = alternate_score

    return DocumentConversionResult(selected_text, diagnostics)


def convert_local_document(
    input_path: Path,
    *,
    improve_rtl_pdf: bool = True,
    rtl_formatting: str = RTL_FORMAT_AUTOMATIC,
) -> DocumentConversionResult:
    if input_path.suffix.casefold() == ".pdf":
        return convert_pdf_document(
            input_path,
            improve_rtl=improve_rtl_pdf,
            rtl_formatting=rtl_formatting,
        )
    converter = MarkItDown()
    result = converter.convert(input_path)
    return DocumentConversionResult(result.text_content)
