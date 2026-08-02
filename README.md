# MarkItDown Converter

MarkItDown Converter is a lightweight Windows 10 desktop interface for
Microsoft MarkItDown v0.1.7. The standalone executable runs without Python,
pip, a terminal, a virtual environment, or any additional installation.

## Use

1. Double-click `dist\MarkItDown Converter.exe`.
2. Select an input document with **Browse Input**.
3. Change the suggested `.md` destination if needed.
4. Select **Convert**.
5. Select **Open Output Folder** after conversion.

For a YouTube transcript:

1. Paste a YouTube watch, `youtu.be`, or Shorts URL.
2. Select **Paste URL**, or type the URL directly.
3. Choose the Markdown destination with **Select Output**.
4. Select **Convert YouTube**.

The input picker supports PDF, DOCX, PPTX, XLSX, XLS, HTML, HTM, TXT, CSV,
JSON, XML, and all files. Conversion runs in the background and writes the
result with UTF-8 encoding. Local document conversion does not require an
internet connection and does not modify the input file.

YouTube conversion retrieves an available transcript or subtitle through
MarkItDown and `youtube-transcript-api`; it does not download the video. This
feature requires internet access and remains subject to transcript availability
and YouTube request blocking.

## Persian And Arabic PDFs

**Improve Persian/Arabic PDF text** is enabled by default. For PDF input, the
application first uses MarkItDown's existing pdfminer/pdfplumber conversion,
analyzes Arabic-script ordering, and only attempts PyMuPDF positioned-word
extraction when the baseline appears corrupted or empty. It compares both
results conservatively and keeps the higher-quality result.

The **RTL Markdown formatting** setting provides:

- **Automatic**: logical-order Unicode in plain Markdown for compatibility.
- **Plain Markdown**: logical-order Unicode without HTML wrappers.
- **HTML RTL blocks**: safe Persian/Arabic paragraphs receive `dir="rtl"`
  blocks; code, URLs, English text, tables, and YAML remain unwrapped.

The saved text always uses normal logical Unicode. Arabic presentation glyphs
are converted to base characters; `arabic-reshaper` is not used. Image-only or
scanned PDFs show a clear OCR-required message. OCR is intentionally not
bundled.

Unexpected-error logs are stored in:

```text
%LOCALAPPDATA%\MarkItDownConverter\logs\
```

## Developer Build

The build uses the globally installed Python 3.13 environment and does not
create a virtual environment. Run:

```bat
build.bat
```

Alternatively, run `py -3.13 build.py`. The script:

1. Verifies Python 3.13 compatibility.
2. Verifies that MarkItDown imports with Python 3.13.
3. Installs PyInstaller with Python 3.13 if it is missing.
4. Removes old `build` and `dist` folders.
5. Builds `MarkItDownConverter.spec` in one-file, windowed mode.
6. Verifies and prints the final executable path.

The expected output is:

```text
dist\MarkItDown Converter.exe
```

The spec collects MarkItDown converter modules, package data and metadata,
Magika model data, `youtube-transcript-api`, PyMuPDF, `regex`, and installed
dependencies for supported formats. Azure services, audio transcription, and
OCR dependencies are excluded from the application build.
