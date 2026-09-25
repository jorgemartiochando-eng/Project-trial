"""Reading HR data files (CSV or Excel) from uploads or from a local folder.

Your real data never needs to leave your computer: put the files in the
private data folder (default: data/private/, which git ignores) and the app
loads them at startup.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Override with an environment variable, e.g. to keep data on an encrypted drive:
#   set PAY_DATA_DIR=D:\HR\pay-transparency        (Windows)
PRIVATE_DIR = Path(os.environ.get("PAY_DATA_DIR", PROJECT_ROOT / "data" / "private"))

EXTENSIONS = (".xlsx", ".xls", ".csv")


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV (comma or semicolon) or Excel (first sheet) into a DataFrame."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content), sheet_name=0)
    return pd.read_csv(io.BytesIO(content), sep=None, engine="python", encoding="utf-8-sig")


def find_file(stem: str, folder: Path = PRIVATE_DIR) -> Path | None:
    """Return folder/<stem>.xlsx|.xls|.csv, whichever exists first."""
    for ext in EXTENSIONS:
        p = folder / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def read_file(path: Path) -> pd.DataFrame:
    return read_table(path.read_bytes(), path.name)
