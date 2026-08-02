from __future__ import annotations

import os
import queue
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from urllib.parse import parse_qs, urlparse

from markitdown import MarkItDown

from pdf_conversion import PDFConversionDiagnostics, ScannedPDFError, convert_local_document
from rtl_text_normalizer import RTL_FORMAT_AUTOMATIC, RTL_FORMAT_OPTIONS


APP_NAME = "MarkItDown Converter"
APP_VERSION = "1.2.0"
SUPPORTED_FILE_TYPES = [
    (
        "Supported Documents",
        "*.pdf *.docx *.pptx *.xlsx *.xls *.html *.htm *.txt *.csv *.json *.xml",
    ),
    ("PDF Files", "*.pdf"),
    ("Word Documents", "*.docx"),
    ("PowerPoint Presentations", "*.pptx"),
    ("Excel Workbooks", "*.xlsx *.xls"),
    ("Web Pages", "*.html *.htm"),
    ("Text and Data Files", "*.txt *.csv *.json *.xml"),
    ("All Files", "*.*"),
]
YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


class TranscriptContentMissingError(RuntimeError):
    pass


def _log_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "MarkItDownConverter" / "logs"


def write_error_log(context: str, details: str) -> Path:
    log_directory = _log_directory()
    log_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    log_path = log_directory / f"error-{timestamp}.log"
    log_path.write_text(
        f"{APP_NAME}\nApplication version: {APP_VERSION}\n"
        f"Time: {datetime.now().astimezone().isoformat()}\n"
        f"Context: {context}\n\n{details}",
        encoding="utf-8",
    )
    return log_path


def write_startup_log() -> Path:
    try:
        import markitdown

        markitdown_status = f"OK ({getattr(markitdown, '__version__', 'unknown')})"
    except BaseException as error:
        markitdown_status = f"FAILED ({type(error).__name__}: {error})"
    try:
        import youtube_transcript_api

        youtube_status = f"OK ({Path(youtube_transcript_api.__file__).resolve()})"
    except BaseException as error:
        youtube_status = f"FAILED ({type(error).__name__}: {error})"
    dependency_statuses: list[str] = []
    for module_name in ("pymupdf", "regex"):
        try:
            module = __import__(module_name)
            dependency_statuses.append(
                f"{module_name} import status: OK ({getattr(module, '__version__', 'unknown')})"
            )
        except BaseException as error:
            dependency_statuses.append(
                f"{module_name} import status: FAILED ({type(error).__name__}: {error})"
            )

    log_directory = _log_directory()
    log_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    log_path = log_directory / f"startup-{timestamp}.log"
    extraction_path = getattr(sys, "_MEIPASS", "Not running from a bundled executable")
    log_path.write_text(
        f"{APP_NAME}\n"
        f"Application version: {APP_VERSION}\n"
        f"Time: {datetime.now().astimezone().isoformat()}\n"
        f"Python runtime version: {sys.version}\n"
        f"MarkItDown import status: {markitdown_status}\n"
        f"youtube_transcript_api import status: {youtube_status}\n"
        + "\n".join(dependency_statuses)
        + "\n"
        + f"Executable path: {Path(sys.executable).resolve()}\n"
        + f"Temporary extraction path: {extraction_path}\n",
        encoding="utf-8",
    )
    return log_path


def write_pdf_diagnostic_log(input_file: Path, diagnostics: PDFConversionDiagnostics) -> Path:
    log_directory = _log_directory()
    log_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    log_path = log_directory / f"pdf-{timestamp}.log"
    scores = ", ".join(
        f"{backend}={score:.3f}" for backend, score in diagnostics.backend_scores.items()
    ) or "Not compared"
    log_path.write_text(
        f"{APP_NAME}\nApplication version: {APP_VERSION}\n"
        f"Time: {datetime.now().astimezone().isoformat()}\n"
        f"Input PDF: {input_file}\n"
        f"Detected RTL character ratio: {diagnostics.rtl_character_ratio:.4f}\n"
        f"Corruption detected: {diagnostics.corruption_detected}\n"
        f"Confidence score: {diagnostics.confidence_score:.4f}\n"
        f"Extraction backend selected: {diagnostics.extraction_backend_selected}\n"
        f"Alternate backend attempted: {diagnostics.alternate_backend_attempted}\n"
        f"Word-coordinate reconstruction used: {diagnostics.word_coordinate_reconstruction_used}\n"
        f"Repaired lines: {diagnostics.repaired_lines}\n"
        f"Duplicate reversed lines removed: {diagnostics.duplicate_reversed_lines_removed}\n"
        f"HTML RTL wrappers added: {diagnostics.html_wrappers_added}\n"
        f"Scanned or image-only: {diagnostics.scanned_or_image_only}\n"
        f"Backend quality scores: {scores}\n",
        encoding="utf-8",
    )
    return log_path


def normalize_youtube_url(value: str) -> str | None:
    url = value.strip()
    if not url:
        return None
    if "://" not in url:
        url = f"https://{url}"
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com"}:
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.path.rstrip("/") == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(path_parts) >= 2 and path_parts[0].lower() == "shorts":
            video_id = path_parts[1]
    if not YOUTUBE_ID_PATTERN.fullmatch(video_id):
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


def sanitize_filename(title: str) -> str:
    clean_title = re.sub(r"\s+-\s+YouTube\s*$", "", title, flags=re.IGNORECASE)
    clean_title = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", clean_title)
    clean_title = re.sub(r"\s+", " ", clean_title).strip(" .")
    if not clean_title:
        return "youtube-transcript"
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{number}" for number in range(1, 10))
    reserved.update(f"LPT{number}" for number in range(1, 10))
    if clean_title.upper() in reserved:
        clean_title = f"_{clean_title}"
    return clean_title[:120].rstrip(" .") or "youtube-transcript"


def youtube_error_message(error: BaseException) -> str:
    error_name = type(error).__name__.lower()
    error_text = str(error).lower()
    combined = f"{error_name} {error_text}"
    if "invalidvideoid" in combined:
        return "The YouTube URL contains an invalid video ID."
    if any(name in combined for name in ("videounavailable", "videounplayable", "agerestricted")):
        return "The YouTube video does not exist or is not available to this application."
    if "transcriptsdisabled" in combined:
        return "Transcripts are disabled for this YouTube video."
    if "notranscriptfound" in combined or isinstance(error, TranscriptContentMissingError):
        return "No transcript is available for this YouTube video."
    if any(name in combined for name in ("requestblocked", "ipblocked", "too many requests", "status code: 429")):
        return "YouTube blocked the transcript request. Try again later or from another network."
    if any(
        name in combined
        for name in ("connectionerror", "connecttimeout", "readtimeout", "name resolution", "failed to establish")
    ):
        return "YouTube could not be reached. Check the internet connection and try again."
    if any(name in combined for name in ("couldnotretrievetranscript", "youtuberequestfailed")):
        return "The requested transcript could not be retrieved from YouTube."
    return "The YouTube transcript could not be retrieved. Try again later."


class ConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("760x620")
        self.root.minsize(660, 600)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status = tk.StringVar(value="Select a document to begin.")
        self.improve_rtl_pdf = tk.BooleanVar(
            value=os.environ.get("MARKITDOWN_CONVERTER_IMPROVE_RTL", "1") != "0"
        )
        requested_rtl_format = os.environ.get(
            "MARKITDOWN_CONVERTER_RTL_FORMAT", RTL_FORMAT_AUTOMATIC
        )
        self.rtl_formatting = tk.StringVar(
            value=requested_rtl_format
            if requested_rtl_format in RTL_FORMAT_OPTIONS
            else RTL_FORMAT_AUTOMATIC
        )
        self.youtube_url = tk.StringVar()
        self.youtube_output = tk.StringVar()
        self.youtube_status = tk.StringVar(value="Paste a YouTube URL to begin.")
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.converting = False
        self.youtube_converting = False
        self.youtube_output_user_selected = False
        self.last_output: Path | None = None
        self.local_smoke_test = bool(os.environ.get("MARKITDOWN_CONVERTER_SMOKE_INPUT"))
        self.youtube_smoke_test = bool(os.environ.get("MARKITDOWN_CONVERTER_YOUTUBE_SMOKE_URL"))
        self.smoke_test = self.local_smoke_test or self.youtube_smoke_test

        self._configure_style()
        self._build_interface()
        self.youtube_url.trace_add("write", self._suggest_youtube_output)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._handle_tk_exception
        self.root.after(100, self._poll_results)

        if self.local_smoke_test:
            self.root.after(250, self._start_local_smoke_test)
        elif self.youtube_smoke_test:
            self.root.after(250, self._start_youtube_smoke_test)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Status.TLabel", foreground="#333333")
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 9, "bold"))

    def _build_interface(self) -> None:
        container = ttk.Frame(self.root, padding=(18, 14, 18, 14))
        container.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text=APP_NAME, style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        self._build_local_section(container)
        self._build_youtube_section(container)

    def _build_local_section(self, container: ttk.Frame) -> None:
        section = ttk.LabelFrame(
            container, text="Local file", padding=(12, 10), style="Section.TLabelframe"
        )
        section.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        section.columnconfigure(1, weight=1)

        ttk.Label(section, text="Input file:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.input_entry = ttk.Entry(section, textvariable=self.input_path)
        self.input_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.input_button = ttk.Button(section, text="Browse Input", command=self._browse_input, width=16)
        self.input_button.grid(row=0, column=2, padx=(10, 0), pady=4)

        ttk.Label(section, text="Output file:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        self.output_entry = ttk.Entry(section, textvariable=self.output_path)
        self.output_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self.output_button = ttk.Button(section, text="Browse Output", command=self._browse_output, width=16)
        self.output_button.grid(row=1, column=2, padx=(10, 0), pady=4)

        rtl_options = ttk.Frame(section)
        rtl_options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(7, 1))
        self.improve_rtl_check = ttk.Checkbutton(
            rtl_options,
            text="Improve Persian/Arabic PDF text",
            variable=self.improve_rtl_pdf,
        )
        self.improve_rtl_check.grid(row=0, column=0, sticky="w")
        ttk.Label(rtl_options, text="RTL Markdown formatting:").grid(
            row=0, column=1, padx=(22, 7)
        )
        self.rtl_format_combo = ttk.Combobox(
            rtl_options,
            textvariable=self.rtl_formatting,
            values=RTL_FORMAT_OPTIONS,
            state="readonly",
            width=18,
        )
        self.rtl_format_combo.grid(row=0, column=2, sticky="w")

        self.progress = ttk.Progressbar(section, mode="indeterminate")
        self.progress.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        ttk.Label(
            section, textvariable=self.status, style="Status.TLabel", anchor="w", wraplength=685
        ).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        button_bar = ttk.Frame(section)
        button_bar.grid(row=5, column=0, columnspan=3, sticky="e")
        self.open_button = ttk.Button(
            button_bar,
            text="Open Output Folder",
            command=self._open_output_folder,
            state="disabled",
        )
        self.open_button.grid(row=0, column=0, padx=(0, 8))
        self.convert_button = ttk.Button(button_bar, text="Convert", command=self._begin_conversion, width=14)
        self.convert_button.grid(row=0, column=1)

    def _build_youtube_section(self, container: ttk.Frame) -> None:
        section = ttk.LabelFrame(
            container, text="YouTube transcript", padding=(12, 10), style="Section.TLabelframe"
        )
        section.grid(row=2, column=0, sticky="ew")
        section.columnconfigure(1, weight=1)

        ttk.Label(section, text="YouTube URL:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.youtube_url_entry = ttk.Entry(section, textvariable=self.youtube_url)
        self.youtube_url_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.youtube_paste_button = ttk.Button(
            section, text="Paste URL", command=self._paste_youtube_url, width=16
        )
        self.youtube_paste_button.grid(row=0, column=2, padx=(10, 0), pady=4)

        ttk.Label(section, text="Output file:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        self.youtube_output_entry = ttk.Entry(section, textvariable=self.youtube_output)
        self.youtube_output_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self.youtube_output_button = ttk.Button(
            section, text="Select Output", command=self._browse_youtube_output, width=16
        )
        self.youtube_output_button.grid(row=1, column=2, padx=(10, 0), pady=4)

        self.youtube_progress = ttk.Progressbar(section, mode="indeterminate")
        self.youtube_progress.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        ttk.Label(
            section,
            textvariable=self.youtube_status,
            style="Status.TLabel",
            anchor="w",
            wraplength=685,
        ).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.youtube_convert_button = ttk.Button(
            section, text="Convert YouTube", command=self._begin_youtube_conversion, width=18
        )
        self.youtube_convert_button.grid(row=4, column=0, columnspan=3, sticky="e")

    def _browse_input(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root, title="Select a document", filetypes=SUPPORTED_FILE_TYPES
        )
        if not selected:
            return
        input_file = Path(selected)
        self.input_path.set(str(input_file))
        self.output_path.set(str(input_file.with_suffix(".md")))
        self.status.set("Ready to convert.")

    def _browse_output(self) -> None:
        current_output = self.output_path.get().strip()
        current_input = self.input_path.get().strip()
        suggested = Path(current_output or current_input or "output.md")
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save Markdown as",
            initialdir=str(suggested.parent) if str(suggested.parent) != "." else None,
            initialfile=suggested.name if suggested.suffix else f"{suggested.name}.md",
            defaultextension=".md",
            filetypes=[("Markdown Files", "*.md"), ("All Files", "*.*")],
        )
        if selected:
            self.output_path.set(selected)

    def _paste_youtube_url(self) -> None:
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            self._youtube_validation_error("The clipboard does not contain text.")
            return
        self.youtube_url.set(value)
        self.youtube_status.set("Ready to retrieve the transcript.")

    def _suggest_youtube_output(self, *_args: object) -> None:
        if not self.youtube_url.get().strip() or self.youtube_output.get().strip():
            return
        documents = Path.home() / "Documents"
        destination = documents if documents.is_dir() else Path.home()
        self.youtube_output.set(str(destination / "youtube-transcript.md"))
        self.youtube_output_user_selected = False

    def _browse_youtube_output(self) -> None:
        current = self.youtube_output.get().strip()
        documents = Path.home() / "Documents"
        suggested = Path(current) if current else (documents if documents.is_dir() else Path.home()) / "youtube-transcript.md"
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save YouTube transcript as",
            initialdir=str(suggested.parent),
            initialfile=suggested.name,
            defaultextension=".md",
            filetypes=[("Markdown Files", "*.md"), ("All Files", "*.*")],
        )
        if selected:
            self.youtube_output.set(selected)
            self.youtube_output_user_selected = True

    def _validated_paths(self) -> tuple[Path, Path] | None:
        input_text = self.input_path.get().strip()
        output_text = self.output_path.get().strip()
        if not input_text:
            self._validation_error("Select an input file.")
            return None
        if not output_text:
            self._validation_error("Select an output file.")
            return None

        input_file = Path(input_text).expanduser()
        output_file = Path(output_text).expanduser()
        if not output_file.suffix:
            output_file = output_file.with_suffix(".md")
            self.output_path.set(str(output_file))
        if not input_file.exists() or not input_file.is_file():
            self._validation_error("The selected input file does not exist or is not a file.")
            return None
        if not self._valid_output_path(output_file, self._validation_error):
            return None
        try:
            same_file = input_file.resolve() == output_file.resolve()
        except OSError:
            same_file = os.path.normcase(str(input_file.absolute())) == os.path.normcase(str(output_file.absolute()))
        if same_file:
            self._validation_error("The output file must be different from the input file.")
            return None
        return input_file, output_file

    def _validated_youtube_values(self) -> tuple[str, Path] | None:
        raw_url = self.youtube_url.get().strip()
        if not raw_url:
            self._youtube_validation_error("Paste a YouTube URL.")
            return None
        youtube_url = normalize_youtube_url(raw_url)
        if youtube_url is None:
            self._youtube_validation_error(
                "Enter a valid YouTube watch, youtu.be, or YouTube Shorts URL."
            )
            return None
        output_text = self.youtube_output.get().strip()
        if not output_text:
            self._youtube_validation_error("Select where the YouTube Markdown file should be saved.")
            return None
        output_file = Path(output_text).expanduser()
        if not output_file.suffix:
            output_file = output_file.with_suffix(".md")
            self.youtube_output.set(str(output_file))
        if not self._valid_output_path(output_file, self._youtube_validation_error):
            return None
        return youtube_url, output_file

    def _valid_output_path(self, output_file: Path, show_error) -> bool:
        if not output_file.parent.exists() or not output_file.parent.is_dir():
            show_error("The output folder does not exist.")
            return False
        if output_file.exists() and not output_file.is_file():
            show_error("The output path is not a file.")
            return False
        return True

    def _validation_error(self, message: str) -> None:
        self.status.set(message)
        if not self.smoke_test:
            messagebox.showerror(APP_NAME, message, parent=self.root)

    def _youtube_validation_error(self, message: str) -> None:
        self.youtube_status.set(message)
        if not self.smoke_test:
            messagebox.showerror(APP_NAME, message, parent=self.root)

    def _begin_conversion(self, *, skip_overwrite: bool = False) -> None:
        if self.converting:
            return
        paths = self._validated_paths()
        if paths is None:
            if self.local_smoke_test:
                self.root.after(100, self.root.destroy)
            return
        input_file, output_file = paths
        if output_file.exists() and not skip_overwrite and not self._confirm_overwrite(output_file):
            self.status.set("Conversion cancelled.")
            return

        self.converting = True
        self.last_output = None
        for widget in (
            self.convert_button,
            self.input_button,
            self.output_button,
            self.input_entry,
            self.output_entry,
            self.open_button,
            self.improve_rtl_check,
            self.rtl_format_combo,
        ):
            widget.configure(state="disabled")
        self.progress.start(12)
        if input_file.suffix.casefold() == ".pdf" and self.improve_rtl_pdf.get():
            self.status.set("Analyzing Persian/Arabic text order...")
        else:
            self.status.set(f"Converting {input_file.name}...")
        threading.Thread(
            target=self._convert_worker,
            args=(
                input_file,
                output_file,
                self.improve_rtl_pdf.get(),
                self.rtl_formatting.get(),
            ),
            name="MarkItDownConversion",
            daemon=True,
        ).start()

    def _begin_youtube_conversion(self, *, skip_overwrite: bool = False) -> None:
        if self.youtube_converting:
            return
        values = self._validated_youtube_values()
        if values is None:
            if self.youtube_smoke_test:
                self.root.after(100, self.root.destroy)
            return
        youtube_url, output_file = values
        if output_file.exists() and not skip_overwrite and not self._confirm_overwrite(output_file):
            self.youtube_status.set("YouTube conversion cancelled.")
            return

        self.youtube_converting = True
        for widget in (
            self.youtube_convert_button,
            self.youtube_paste_button,
            self.youtube_output_button,
            self.youtube_url_entry,
            self.youtube_output_entry,
        ):
            widget.configure(state="disabled")
        self.youtube_progress.start(12)
        self.youtube_status.set("Retrieving YouTube transcript...")
        threading.Thread(
            target=self._youtube_worker,
            args=(youtube_url, output_file, self.youtube_output_user_selected),
            name="YouTubeTranscriptConversion",
            daemon=True,
        ).start()

    def _confirm_overwrite(self, output_file: Path) -> bool:
        return messagebox.askyesno(
            APP_NAME,
            f"The output file already exists:\n\n{output_file}\n\nOverwrite it?",
            parent=self.root,
        )

    def _convert_worker(
        self,
        input_file: Path,
        output_file: Path,
        improve_rtl_pdf: bool,
        rtl_formatting: str,
    ) -> None:
        try:
            result = convert_local_document(
                input_file,
                improve_rtl_pdf=improve_rtl_pdf,
                rtl_formatting=rtl_formatting,
            )
            output_file.write_text(result.markdown, encoding="utf-8")
            diagnostic_log = None
            if result.pdf_diagnostics is not None:
                diagnostic_log = write_pdf_diagnostic_log(input_file, result.pdf_diagnostics)
            self.result_queue.put(
                ("local_success", (output_file, result.pdf_diagnostics, diagnostic_log))
            )
        except BaseException as error:
            user_message = (
                "This PDF appears to be scanned and requires OCR."
                if isinstance(error, ScannedPDFError)
                else "The document could not be converted. Check that the file is valid and supported."
            )
            self.result_queue.put(
                ("local_error", (user_message, traceback.format_exc()))
            )

    def _youtube_worker(self, youtube_url: str, output_file: Path, output_was_selected: bool) -> None:
        try:
            import youtube_transcript_api  # noqa: F401 - verifies the bundled dependency at runtime

            converter = MarkItDown()
            result = converter.convert(youtube_url)
            markdown_text = result.text_content
            if not re.search(r"(?im)^### Transcript\s*$", markdown_text):
                raise TranscriptContentMissingError(
                    "MarkItDown returned YouTube metadata without transcript content."
                )

            final_output = output_file
            title = (result.title or "").strip()
            if title and not output_was_selected and output_file.name.lower() == "youtube-transcript.md":
                title_output = output_file.with_name(f"{sanitize_filename(title)}.md")
                if not title_output.exists():
                    final_output = title_output
            final_output.write_text(markdown_text, encoding="utf-8")
            self.result_queue.put(("youtube_success", (final_output, title)))
        except BaseException as error:
            self.result_queue.put(
                ("youtube_error", (youtube_error_message(error), traceback.format_exc()))
            )

    def _poll_results(self) -> None:
        try:
            result_type, payload = self.result_queue.get_nowait()
        except queue.Empty:
            if self.root.winfo_exists():
                self.root.after(100, self._poll_results)
            return

        if result_type == "local_success":
            self._finish_conversion()
            output_file, pdf_diagnostics, _diagnostic_log = payload
            output_file = Path(output_file)
            self.last_output = output_file
            self.open_button.configure(state="normal")
            backend_text = (
                f" ({pdf_diagnostics.extraction_backend_selected})"
                if pdf_diagnostics is not None and pdf_diagnostics.rtl_character_ratio >= 0.12
                else ""
            )
            self.status.set(f"Conversion complete{backend_text}: {output_file}")
            if self.local_smoke_test:
                self.root.after(200, self.root.destroy)
            else:
                messagebox.showinfo(
                    APP_NAME, f"Conversion completed successfully.\n\n{output_file}", parent=self.root
                )
        elif result_type == "local_error":
            self._finish_conversion()
            user_message, details = payload
            self._show_operation_error(
                "Document conversion",
                str(user_message),
                str(details),
                self.status,
            )
        elif result_type == "youtube_success":
            self._finish_youtube_conversion()
            output_file, title = payload
            self.youtube_output.set(str(output_file))
            self.youtube_status.set(f"YouTube transcript saved: {output_file}")
            if self.youtube_smoke_test:
                self.root.after(200, self.root.destroy)
            else:
                title_text = f"\n\nVideo: {title}" if title else ""
                messagebox.showinfo(
                    APP_NAME,
                    f"YouTube transcript saved successfully.{title_text}\n\n{output_file}",
                    parent=self.root,
                )
        elif result_type == "youtube_error":
            self._finish_youtube_conversion()
            user_message, details = payload
            self._show_operation_error(
                "YouTube transcript conversion",
                str(user_message),
                str(details),
                self.youtube_status,
            )

        if not self.smoke_test and self.root.winfo_exists():
            self.root.after(100, self._poll_results)

    def _finish_conversion(self) -> None:
        self.converting = False
        self.progress.stop()
        for widget in (
            self.convert_button,
            self.input_button,
            self.output_button,
            self.input_entry,
            self.output_entry,
            self.improve_rtl_check,
        ):
            widget.configure(state="normal")
        self.rtl_format_combo.configure(state="readonly")

    def _finish_youtube_conversion(self) -> None:
        self.youtube_converting = False
        self.youtube_progress.stop()
        for widget in (
            self.youtube_convert_button,
            self.youtube_paste_button,
            self.youtube_output_button,
            self.youtube_url_entry,
            self.youtube_output_entry,
        ):
            widget.configure(state="normal")

    def _open_output_folder(self) -> None:
        if self.last_output is None:
            return
        try:
            os.startfile(str(self.last_output.parent))
        except BaseException:
            self._show_operation_error(
                "Opening the output folder",
                "The output folder could not be opened.",
                traceback.format_exc(),
                self.status,
            )

    def _show_operation_error(
        self, context: str, user_message: str, details: str, status_variable: tk.StringVar
    ) -> None:
        try:
            log_path = write_error_log(context, details)
            message = f"{user_message}\n\nTechnical details were saved to:\n{log_path}"
        except BaseException:
            message = f"{user_message}\n\nThe technical error log could not be saved."
        status_variable.set(user_message)
        if self.smoke_test:
            self.root.after(100, self.root.destroy)
        else:
            messagebox.showerror(APP_NAME, message, parent=self.root)

    def _handle_tk_exception(
        self, exc_type: type[BaseException], exc: BaseException, tb: object
    ) -> None:
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        self._show_operation_error(
            "Application interface",
            "An unexpected interface error occurred.",
            details,
            self.status,
        )

    def _on_close(self) -> None:
        if (self.converting or self.youtube_converting) and not self.smoke_test:
            close = messagebox.askyesno(
                APP_NAME,
                "A conversion is still running. Close the application?",
                parent=self.root,
            )
            if not close:
                return
        self.root.destroy()

    def _start_local_smoke_test(self) -> None:
        self.input_path.set(os.environ.get("MARKITDOWN_CONVERTER_SMOKE_INPUT", ""))
        self.output_path.set(os.environ.get("MARKITDOWN_CONVERTER_SMOKE_OUTPUT", ""))
        self._begin_conversion(skip_overwrite=True)

    def _start_youtube_smoke_test(self) -> None:
        self.youtube_url.set(os.environ.get("MARKITDOWN_CONVERTER_YOUTUBE_SMOKE_URL", ""))
        self.youtube_output.set(os.environ.get("MARKITDOWN_CONVERTER_YOUTUBE_SMOKE_OUTPUT", ""))
        self.youtube_output_user_selected = True
        self._begin_youtube_conversion(skip_overwrite=True)


def main() -> None:
    write_startup_log()
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        details = traceback.format_exc()
        try:
            log_path = write_error_log("Application startup", details)
            message = f"The application could not start. Details were saved to:\n\n{log_path}"
        except BaseException:
            message = "The application could not start, and the error log could not be saved."
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_NAME, message, parent=root)
            root.destroy()
        except BaseException:
            pass
