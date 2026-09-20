# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OcuRead.

    pyinstaller --clean --noconfirm ocuread.spec           (or just run build.bat)

Switches (environment variables, set for you by the build.bat flags):
    OCUREAD_DEBUG=1     console window on, name "OcuRead-debug"            (build.bat --debug)
    OCUREAD_ONEFILE=1   single OcuRead.exe instead of a folder             (build.bat --onefile)

Default is ONE-FOLDER: it starts much faster than one-file (which must unpack ~GBs of torch/paddle into a
temp folder on every launch). To make one-file permanent, set ONEFILE = True below.

Models are NOT bundled - they download on first use into the Hugging Face / PaddleX caches
(or the folder chosen in Settings > Model cache folder).

Adding an OCR backend that is imported dynamically? Add its package to OPTIONAL_PACKAGES and its pip
distribution name to METADATA_ROOTS - see the README, "Spec file notes".
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(SPECPATH, "tools"))
from spec_helpers import dependency_closure, native_libraries, top_level_modules   # noqa: E402

from PyInstaller.utils.hooks import (                                # noqa: E402
    collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata,
)

ROOT = SPECPATH                                   # folder containing this spec (provided by PyInstaller)
DEBUG = os.environ.get("OCUREAD_DEBUG") == "1"
ONEFILE = os.environ.get("OCUREAD_ONEFILE") == "1"
NAME = "OcuRead-debug" if DEBUG else "OcuRead"
ICON = "assets/icon.ico"                          # relative to the project root (build.bat runs from there)

# ---- packages whose data files / submodules must ship (skipped with a note if not installed) -----------
OPTIONAL_PACKAGES = {
    #  package      (collect data files, collect all submodules)
    "surya":        (True, True),
    "paddleocr":    (True, True),
    "paddlex":      (True, True),      # PaddleOCR 3.x runs on PaddleX: pipeline configs live here
    "doctr":        (True, True),
    "transformers": (True, False),     # tokenizer / config templates; submodules come from PyInstaller's hooks
    "tokenizers":   (True, False),
    "safetensors":  (False, True),
}
OPTIONAL_PACKAGES["paddle"] = (True, False)        # the framework itself (its DLLs are collected below)
OPTIONAL_PACKAGES["torchvision"] = (True, True)    # needed by docTR and Surya (via transformers)

# Distributions whose *metadata* must ship, together with everything they depend on (extras included).
# Libraries check their own dependencies with importlib.metadata at run time - e.g. PaddleX verifies that
# the extras of "paddlex[ocr]" are installed, and transformers decides whether PyTorch exists by reading
# torch's version - and without the metadata those checks fail inside the exe ("`OCR` requires additional
# dependencies", "PyTorch not found").  {distribution: extras}
METADATA_ROOTS = {
    "paddlex": ("ocr", "ocr-core"), "paddleocr": (), "paddlepaddle": (),
    "torch": (), "torchvision": (), "transformers": (), "tokenizers": (), "huggingface_hub": (), "safetensors": (),
    "surya-ocr": (), "python-doctr": (),
}

datas = [("assets", "assets"), ("theme", "theme")]   # icons + the .qss stylesheets
hiddenimports = [
    # GUI
    "PySide6.QtSvg", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFilter", "numpy", "tqdm", "tqdm.std",
    # OcuRead's own engines are imported through the factory
    "core.engines.normal_engine", "core.engines.llm_engine",
]
binaries = []

# PDF + ML stack: imported lazily by the engines, so static analysis can miss them. Only listed when
# installed, so an optional backend you didn't install doesn't produce "hidden import not found" noise.
for pkg in ("fitz", "pymupdf", "torch", "transformers", "surya", "paddleocr", "paddlex", "doctr"):
    if importlib.util.find_spec(pkg) is not None:
        hiddenimports.append(pkg)

for pkg, (want_data, want_subs) in OPTIONAL_PACKAGES.items():
    if importlib.util.find_spec(pkg) is None:
        print(f"[spec] optional package '{pkg}' is not installed - skipped")
        continue
    if want_data:
        datas += collect_data_files(pkg)
    if want_subs:
        hiddenimports += collect_submodules(pkg)

metadata_dists = dependency_closure(METADATA_ROOTS)
print(f"[spec] bundling metadata for {len(metadata_dists)} installed distributions")
for dist in metadata_dists:
    try:
        datas += copy_metadata(dist)
    except Exception:  # noqa: BLE001 - metadata not available for this distribution
        pass

# PaddleOCR's dependencies (opencv, pyclipper, shapely, pypdfium2 ...) are imported lazily; make sure they ship.
_SKIP = {"pip", "setuptools", "wheel", "pkg_resources", "test", "tests"}
for module in top_level_modules(dependency_closure({"paddlex": ("ocr", "ocr-core"), "paddleocr": ()})):
    if module.isidentifier() and "mypyc" not in module and module not in _SKIP and importlib.util.find_spec(module) is not None:
        hiddenimports.append(module)

if importlib.util.find_spec("paddle") is not None:
    binaries += collect_dynamic_libs("paddle")   # paddle/libs/*.dll (mkldnn, openblas ...)

# torchvision loads its compiled ops library (torchvision/_C.pyd) by FILE PATH, not by import, so PyInstaller
# never bundles it; without it docTR / Surya fail with "operator torchvision::nms does not exist".
binaries += native_libraries("torchvision")

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name=NAME,
        icon=ICON,
        console=DEBUG,          # windowed for the normal build, console for --debug
        upx=False,              # UPX corrupts torch / CUDA DLLs
        runtime_tmpdir=None,
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=NAME,
        icon=ICON,
        console=DEBUG,
        upx=False,
    )
    coll = COLLECT(
        exe, a.binaries, a.datas,
        strip=False,
        upx=False,
        upx_exclude=["*.dll", "*.pyd"],
        name=NAME,
    )
