from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_DIRECTORY / "MarkItDownConverter.spec"
FINAL_EXECUTABLE = PROJECT_DIRECTORY / "dist" / "MarkItDown Converter.exe"


def run(command: list[str]) -> None:
    print(f"> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=PROJECT_DIRECTORY, check=True)


def main() -> None:
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError(
            f"Python 3.13 is required; this interpreter is {sys.version.split()[0]}. "
            "Run this script with: py -3.13 build.py"
        )
    print(f"Using Python: {sys.executable}")

    rtl_requirements = {
        "pymupdf": "PyMuPDF>=1.24",
        "regex": "regex>=2024.0",
    }
    missing_rtl_requirements = [
        requirement
        for module_name, requirement in rtl_requirements.items()
        if importlib.util.find_spec(module_name) is None
    ]
    if missing_rtl_requirements:
        print("Installing required Persian/Arabic PDF dependencies...")
        run([sys.executable, "-m", "pip", "install", *missing_rtl_requirements])

    try:
        import pymupdf
        import regex
    except Exception as exc:
        raise RuntimeError(
            "PyMuPDF and regex are required for Persian/Arabic PDF normalization."
        ) from exc
    print(f"PyMuPDF import: {Path(pymupdf.__file__).resolve()}")
    print(f"regex import: {Path(regex.__file__).resolve()}")

    try:
        import markitdown
        from markitdown import MarkItDown
    except Exception as exc:
        raise RuntimeError(
            "MarkItDown could not be imported with Python 3.13. Install the local "
            "MarkItDown package and its local-format dependencies first."
        ) from exc
    print(f"MarkItDown import: {Path(markitdown.__file__).resolve()}")
    print(f"MarkItDown API: {MarkItDown.__name__}")

    try:
        import youtube_transcript_api
        import youtube_transcript_api._api
        import youtube_transcript_api._errors
        import youtube_transcript_api._transcripts
    except Exception as exc:
        raise RuntimeError(
            "youtube_transcript_api could not be imported with Python 3.13. "
            "Install the local MarkItDown youtube-transcription extra first."
        ) from exc
    print(f"youtube_transcript_api import: {Path(youtube_transcript_api.__file__).resolve()}")

    if importlib.util.find_spec("PyInstaller") is None:
        print("PyInstaller is not installed; installing it with Python 3.13...")
        run([sys.executable, "-m", "pip", "install", "PyInstaller"])
    else:
        print("PyInstaller is already installed.")

    for directory_name in ("build", "dist"):
        directory = PROJECT_DIRECTORY / directory_name
        if directory.exists():
            print(f"Removing old {directory_name} directory...")
            shutil.rmtree(directory)

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_FILE),
        ]
    )

    if not FINAL_EXECUTABLE.is_file():
        raise RuntimeError(f"Build finished without creating: {FINAL_EXECUTABLE}")
    print(f"Build successful. Final executable: {FINAL_EXECUTABLE}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
