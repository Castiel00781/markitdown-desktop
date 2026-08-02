from pathlib import Path
import tkinter as tk

import app


def test_error_log_is_written_under_local_app_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    log_path = app.write_error_log("Test context", "Technical details")
    assert log_path.parent == tmp_path / "MarkItDownConverter" / "logs"
    assert "Technical details" in log_path.read_text(encoding="utf-8")


def test_output_folder_button_uses_os_startfile(tmp_path, monkeypatch):
    root = tk.Tk()
    root.withdraw()
    converter_app = app.ConverterApp(root)
    converter_app.last_output = tmp_path / "output.md"
    opened: list[str] = []
    monkeypatch.setattr(app.os, "startfile", lambda path: opened.append(path))
    converter_app._open_output_folder()
    root.destroy()
    assert opened == [str(tmp_path)]


def test_rtl_pdf_settings_default_to_safe_values():
    root = tk.Tk()
    root.withdraw()
    converter_app = app.ConverterApp(root)
    assert converter_app.improve_rtl_pdf.get() is True
    assert converter_app.rtl_formatting.get() == "Automatic"
    root.destroy()
