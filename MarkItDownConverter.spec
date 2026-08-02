from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata


datas = []
binaries = []
hiddenimports = []


def is_test_module(module_name):
    return (
        ".tests" in module_name
        or ".test." in module_name
        or module_name.endswith(".test")
        or ".test_" in module_name
        or module_name.startswith("test_")
    )


def is_test_data(data_entry):
    destination = data_entry[1].replace("\\", "/").lower()
    padded_destination = f"/{destination}/"
    return (
        "/tests/" in padded_destination
        or "/test/" in padded_destination
        or destination.endswith(("/tests", "/test"))
        or "/pymupdf/mupdf-devel/" in padded_destination
    )

# Each entry is (import name, distribution name). Availability is checked before
# collecting so optional packages that are not installed never break the build.
packaged_dependencies = [
    ("markitdown", "markitdown"),
    ("youtube_transcript_api", "youtube-transcript-api"),
    ("pymupdf", "PyMuPDF"),
    ("regex", "regex"),
    ("magika", "magika"),
    ("markdownify", "markdownify"),
    ("bs4", "beautifulsoup4"),
    ("charset_normalizer", "charset-normalizer"),
    ("defusedxml", "defusedxml"),
    ("requests", "requests"),
    ("pdfminer", "pdfminer.six"),
    ("pdfplumber", "pdfplumber"),
    ("mammoth", "mammoth"),
    ("pptx", "python-pptx"),
    ("openpyxl", "openpyxl"),
    ("pandas", "pandas"),
    ("xlrd", "xlrd"),
    ("lxml", "lxml"),
    ("olefile", "olefile"),
]

for module_name, distribution_name in packaged_dependencies:
    try:
        available = find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        available = False
    if not available:
        continue

    package_datas, package_binaries, package_hiddenimports = collect_all(module_name)
    datas += [entry for entry in package_datas if not is_test_data(entry)]
    binaries += package_binaries
    hiddenimports += [
        module for module in package_hiddenimports if not is_test_module(module)
    ]
    try:
        datas += copy_metadata(distribution_name)
    except Exception:
        # A source checkout may be importable without installed distribution metadata.
        pass

# MarkItDown exposes converters from a shared package and some dependencies load
# engines dynamically. Keep those modules explicit even if a future hook changes.
hiddenimports += collect_submodules("markitdown.converters")
hiddenimports += collect_submodules("markitdown.converter_utils")
for youtube_module in (
    "youtube_transcript_api",
    "youtube_transcript_api._api",
    "youtube_transcript_api._transcripts",
    "youtube_transcript_api._errors",
):
    try:
        if find_spec(youtube_module) is not None:
            hiddenimports.append(youtube_module)
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
for dynamic_package in (
    "certifi",
    "cobble",
    "cryptography",
    "dateutil",
    "dotenv",
    "et_xmlfile",
    "idna",
    "numpy",
    "onnxruntime",
    "PIL",
    "pypdfium2",
    "six",
    "soupsieve",
    "tzdata",
    "urllib3",
    "xlsxwriter",
):
    try:
        if find_spec(dynamic_package) is not None:
            discovered_modules = collect_submodules(dynamic_package)
            hiddenimports += [
                module
                for module in discovered_modules
                if not is_test_module(module)
                and not module.startswith("numpy._pyinstaller")
                and not module.startswith("onnxruntime.quantization")
                and not module.startswith("onnxruntime.tools")
                and not module.startswith("onnxruntime.transformers")
            ]
    except (ImportError, ModuleNotFoundError, ValueError):
        pass

hiddenimports = sorted(set(hiddenimports))

a = Analysis(
    ["app.py"],
    pathex=[str(SPECPATH)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "azure",
        "azure.ai",
        "azure.ai.contentunderstanding",
        "azure.ai.documentintelligence",
        "azure.identity",
        "openai",
        "numpy.tests",
        "onnxruntime.quantization",
        "onnxruntime.tools",
        "onnxruntime.transformers",
        "pandas.tests",
        "pytest",
        "_pytest",
        "pygments",
        "pydub",
        "speech_recognition",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MarkItDown Converter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
