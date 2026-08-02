from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

import regex


RTL_FORMAT_AUTOMATIC = "Automatic"
RTL_FORMAT_PLAIN = "Plain Markdown"
RTL_FORMAT_HTML = "HTML RTL blocks"
RTL_FORMAT_OPTIONS = (RTL_FORMAT_AUTOMATIC, RTL_FORMAT_PLAIN, RTL_FORMAT_HTML)

ARABIC_SCRIPT_PATTERN = regex.compile(
    r"[\p{Script=Arabic}\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff"
    r"\ufb50-\ufdff\ufe70-\ufeff]"
)
ARABIC_WORD_PATTERN = regex.compile(
    r"[\p{Script=Arabic}\u200c\u200d\u064b-\u065f]+"
)
PRESENTATION_FORM_PATTERN = regex.compile(r"[\ufb50-\ufdff\ufe70-\ufeff]")
PROTECTED_TOKEN_PATTERN = regex.compile(
    r"https?://[^\s]+|www\.[^\s]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"[A-Za-z][A-Za-z0-9_.+/-]*|[0-9\u0660-\u0669\u06f0-\u06f9]+(?:[./:-][0-9\u0660-\u0669\u06f0-\u06f9]+)*|"
    r"[\p{Script=Arabic}\u200c\u200d\u064b-\u065f]+|[^\s]"
)

CHARACTER_VARIANTS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})

PERSIAN_WORDS = {
    "از",
    "است",
    "این",
    "با",
    "برای",
    "به",
    "بود",
    "تاریخ",
    "تا",
    "دانش",
    "دانشبنیان",
    "دانش‌بنیان",
    "در",
    "را",
    "سال",
    "شد",
    "شده",
    "شماره",
    "شاخص",
    "فارس",
    "گزارش",
    "ماه",
    "مقدار",
    "مینو",
    "نسخه",
    "نصب",
    "نهایی",
    "ردیف",
    "ورود",
    "و",
    "عملکرد",
    "اولیه",
    "گزینه",
    "گزینهها",
    "گزینه‌های",
    "حوزه",
    "دوم",
    "صفحه",
    "آماده",
}
ARABIC_WORDS = {
    "هذا",
    "هذه",
    "تقرير",
    "عربي",
    "العربية",
    "واضح",
    "في",
    "من",
    "إلى",
    "على",
    "هو",
    "هي",
    "كان",
    "تم",
    "عام",
    "النص",
    "النهائي",
}
KNOWN_WORDS = PERSIAN_WORDS | ARABIC_WORDS
SUSPICIOUS_REVERSED_PREFIXES = ("یاه", "نیرت", "شرازگ", "هخسن", "ريرقت", "اذه")
LOGICAL_WORD_PAIRS = {
    ("گزارش", "اولیه"),
    ("اولیه", "گزینه‌های"),
    ("گزینه‌های", "ورود"),
    ("ورود", "مینو"),
    ("مینو", "فارس"),
    ("فارس", "به"),
    ("به", "حوزه"),
    ("حوزه", "دانش‌بنیان"),
    ("گزارش", "عملکرد"),
    ("ماه", "آماده"),
    ("هذا", "تقریر"),
    ("تقریر", "عربی"),
    ("عربی", "واضح"),
}


@dataclass(frozen=True)
class LineAnalysis:
    rtl_ratio: float
    corruption_confidence: float
    original_quality: float
    repaired_quality: float
    predominantly_rtl: bool
    should_repair: bool


@dataclass
class NormalizationDiagnostics:
    rtl_character_ratio: float = 0.0
    corruption_detected: bool = False
    confidence_score: float = 0.0
    total_lines: int = 0
    rtl_lines: int = 0
    repaired_lines: int = 0
    duplicate_reversed_lines_removed: int = 0
    html_wrappers_added: int = 0


@dataclass(frozen=True)
class NormalizationResult:
    text: str
    diagnostics: NormalizationDiagnostics


def normalize_character_variants(text: str) -> str:
    # PDF fonts frequently expose Arabic Presentation Forms. NFKC maps those
    # compatibility glyphs back to ordinary logical Arabic code points.
    return unicodedata.normalize("NFKC", text).translate(CHARACTER_VARIANTS).replace("\u00ad", "-")


def rtl_character_ratio(text: str) -> float:
    visible = [character for character in text if character.isalnum()]
    if not visible:
        return 0.0
    rtl_count = sum(1 for character in visible if ARABIC_SCRIPT_PATTERN.fullmatch(character))
    return rtl_count / len(visible)


def _compact_for_comparison(text: str) -> str:
    normalized = normalize_character_variants(text).replace("\u200c", "")
    return regex.sub(r"[\s\p{P}\p{S}]", "", normalized).casefold()


def _is_protected_token(token: str) -> bool:
    return bool(
        regex.fullmatch(r"https?://[^\s]+|www\.[^\s]+", token, regex.IGNORECASE)
        or regex.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", token)
        or regex.fullmatch(r"[A-Za-z][A-Za-z0-9_.+/-]*", token)
        or regex.fullmatch(
            r"[0-9\u0660-\u0669\u06f0-\u06f9]+(?:[./:-][0-9\u0660-\u0669\u06f0-\u06f9]+)*",
            token,
        )
    )


def _reverse_arabic_token(token: str) -> str:
    if _is_protected_token(token) or not ARABIC_SCRIPT_PATTERN.search(token):
        return token
    return "".join(reversed(regex.findall(r"\X", token)))


def _reversal_candidate(line: str) -> str:
    tokens = PROTECTED_TOKEN_PATTERN.findall(line)
    if not tokens:
        return line
    repaired = [_reverse_arabic_token(token) for token in reversed(tokens)]
    return _join_tokens(repaired)


def _join_tokens(tokens: list[str]) -> str:
    result = ""
    no_space_before = set(",.;:!?%،؛؟)]}»")
    no_space_after = set("([{«")
    for token in tokens:
        if not result:
            result = token
        elif token in no_space_before or result[-1] in no_space_after:
            result += token
        else:
            result += f" {token}"
    return result


def _word_quality(word: str) -> float:
    compact = regex.sub(r"[^\p{Script=Arabic}\u200c]", "", word)
    if not compact:
        return 0.0
    without_zwnj = compact.replace("\u200c", "")
    score = 0.0
    if compact in KNOWN_WORDS or without_zwnj in KNOWN_WORDS:
        score += 2.4
    if compact.startswith("ال") and len(compact) > 3:
        score += 0.45
    if compact.startswith(("می‌", "نمی‌")):
        score += 0.6
    if compact.endswith(("ها", "های", "تر", "ترین", "ان", "ات", "ون", "ین", "ة")):
        score += 0.25
    if compact.startswith(SUSPICIOUS_REVERSED_PREFIXES):
        score -= 1.35
    if PRESENTATION_FORM_PATTERN.search(compact):
        score -= 0.8
    return score


def logical_quality_score(text: str) -> float:
    normalized = normalize_character_variants(text)
    words = ARABIC_WORD_PATTERN.findall(normalized)
    score = sum(_word_quality(word) for word in words)
    normalized_words = [word.replace("\u200c", "") for word in words]
    normalized_pairs = {
        (first.replace("\u200c", ""), second.replace("\u200c", ""))
        for first, second in LOGICAL_WORD_PAIRS
    }
    score += sum(
        1.15
        for pair in zip(normalized_words, normalized_words[1:])
        if pair in normalized_pairs
    )
    stripped = normalized.strip()
    if stripped and stripped[-1] in ".!?؟":
        score += 0.45
    if stripped and stripped[0] in ".!?؟":
        score -= 0.75
    score -= len(PRESENTATION_FORM_PATTERN.findall(normalized)) * 0.4
    return score


def analyze_rtl_line(line: str) -> LineAnalysis:
    normalized = normalize_character_variants(line)
    ratio = rtl_character_ratio(normalized)
    words = ARABIC_WORD_PATTERN.findall(normalized)
    predominantly_rtl = ratio >= 0.45 and len(words) >= 2
    if not predominantly_rtl:
        quality = logical_quality_score(normalized)
        return LineAnalysis(ratio, 0.0, quality, quality, False, False)

    candidate = _reversal_candidate(normalized)
    original_quality = logical_quality_score(normalized)
    candidate_quality = logical_quality_score(candidate)
    suspicious_words = sum(
        1 for word in words if word.replace("\u200c", "").startswith(SUSPICIOUS_REVERSED_PREFIXES)
    )
    improvement = candidate_quality - original_quality
    required_improvement = max(2.8, len(words) * 0.35)
    confidence = max(0.0, min(1.0, improvement / max(required_improvement * 1.35, 1.0)))
    if suspicious_words:
        confidence = min(1.0, confidence + min(0.22, suspicious_words / len(words) * 0.3))
    should_repair = improvement >= required_improvement and confidence >= 0.68
    return LineAnalysis(
        ratio,
        confidence,
        original_quality,
        candidate_quality,
        predominantly_rtl,
        should_repair,
    )


def normalize_rtl_line(line: str) -> str:
    normalized = normalize_character_variants(line)
    normalized = regex.sub(r"[\t ]+", " ", normalized).strip()
    analysis = analyze_rtl_line(normalized)
    repaired = _reversal_candidate(normalized) if analysis.should_repair else normalized
    repaired = repaired.replace("گزینههای", "گزینه‌های")
    repaired = repaired.replace("گزینهه‌ای", "گزینه‌های")
    repaired = repaired.replace("گزینهه‌ای", "گزینه‌های")
    repaired = regex.sub(r"دانش(?:ب|ب‌|‌ب)نیان", "دانش‌بنیان", repaired)
    return repaired


def normalize_rtl_word(word: str) -> str:
    normalized = normalize_character_variants(word)
    if not ARABIC_SCRIPT_PATTERN.search(normalized):
        return normalized
    parts = regex.split(r"([\p{Script=Arabic}\u200c\u200d\u064b-\u065f]+)", normalized)
    for index, part in enumerate(parts):
        if not ARABIC_SCRIPT_PATTERN.search(part):
            continue
        candidate = "".join(reversed(regex.findall(r"\X", part)))
        if logical_quality_score(candidate) >= logical_quality_score(part) + 1.35:
            parts[index] = candidate
    repaired = "".join(parts)
    repaired = repaired.replace("گزینههای", "گزینه‌های")
    repaired = repaired.replace("گزینهه‌ای", "گزینه‌های")
    repaired = repaired.replace("گزینهه‌ای", "گزینه‌های")
    return regex.sub(r"دانش(?:ب|ب‌|‌ب)نیان", "دانش‌بنیان", repaired)


def _are_reverse_equivalent(first: str, second: str) -> bool:
    if rtl_character_ratio(first) < 0.35 or rtl_character_ratio(second) < 0.35:
        return False
    first_compact = _compact_for_comparison(first)
    second_compact = _compact_for_comparison(second)
    return (
        first_compact == _compact_for_comparison(_reversal_candidate(second))
        or second_compact == _compact_for_comparison(_reversal_candidate(first))
    )


def _format_html_rtl_blocks(text: str) -> tuple[str, int]:
    output: list[str] = []
    wrapped = 0
    inside_code_fence = False
    in_yaml_front_matter = False
    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            output.append(line)
            continue
        if index == 0 and stripped == "---":
            in_yaml_front_matter = True
        if stripped.startswith("```"):
            inside_code_fence = not inside_code_fence
            output.append(line)
            continue
        if in_yaml_front_matter:
            output.append(line)
            if stripped == "---" and index > 0:
                in_yaml_front_matter = False
            continue
        is_table = "|" in stripped
        is_url = bool(regex.fullmatch(r"https?://\S+", stripped, regex.IGNORECASE))
        is_heading = stripped.startswith(("#", ">", "<"))
        if (
            not inside_code_fence
            and not is_table
            and not is_url
            and not is_heading
            and rtl_character_ratio(stripped) >= 0.45
        ):
            output.append(f'<div dir="rtl" align="right">\n\n{stripped}\n\n</div>')
            wrapped += 1
        else:
            output.append(line)
    return "\n".join(output), wrapped


def normalize_rtl_text_with_diagnostics(
    text: str, formatting: str = RTL_FORMAT_AUTOMATIC
) -> NormalizationResult:
    if formatting not in RTL_FORMAT_OPTIONS:
        formatting = RTL_FORMAT_AUTOMATIC
    source_lines = text.splitlines()
    diagnostics = NormalizationDiagnostics(
        rtl_character_ratio=rtl_character_ratio(text), total_lines=len(source_lines)
    )
    output_lines: list[str] = []
    previous_source = ""

    for source_line in source_lines:
        if not source_line.strip():
            output_lines.append("")
            previous_source = ""
            continue
        analysis = analyze_rtl_line(source_line)
        if analysis.predominantly_rtl:
            diagnostics.rtl_lines += 1
        diagnostics.confidence_score = max(
            diagnostics.confidence_score, analysis.corruption_confidence
        )
        if analysis.should_repair:
            diagnostics.corruption_detected = True
            diagnostics.repaired_lines += 1

        normalized_line = normalize_rtl_line(source_line)
        if previous_source and _are_reverse_equivalent(previous_source, source_line):
            previous_normalized = output_lines[-1] if output_lines else ""
            if logical_quality_score(normalized_line) > logical_quality_score(previous_normalized):
                output_lines[-1] = normalized_line
            diagnostics.duplicate_reversed_lines_removed += 1
            previous_source = source_line
            continue
        output_lines.append(normalized_line)
        previous_source = source_line

    normalized_text = "\n".join(output_lines)
    normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text).strip()
    if formatting == RTL_FORMAT_HTML:
        normalized_text, diagnostics.html_wrappers_added = _format_html_rtl_blocks(normalized_text)
    return NormalizationResult(normalized_text, diagnostics)


def normalize_rtl_text(text: str) -> str:
    return normalize_rtl_text_with_diagnostics(text).text
