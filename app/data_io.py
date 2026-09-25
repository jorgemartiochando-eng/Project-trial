"""Reading HR data files (CSV or Excel) from uploads or from a local folder.

Your real data never needs to leave your computer: put the files in the
private data folder (default: data/private/, which git ignores) and the app
loads them at startup.
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Override with an environment variable, e.g. to keep data on an encrypted drive:
#   set PAY_DATA_DIR=D:\HR\pay-transparency        (Windows)
PRIVATE_DIR = Path(os.environ.get("PAY_DATA_DIR", PROJECT_ROOT / "data" / "private"))

EXTENSIONS = (".xlsx", ".xls", ".csv")


def _known_header_keys() -> set[str]:
    from .schema import COLUMN_ALIASES, EMPLOYEE_COLUMNS, JOB_EVALUATION_COLUMNS
    return set(EMPLOYEE_COLUMNS) | set(JOB_EVALUATION_COLUMNS) | set(COLUMN_ALIASES)


def _promote_header_row(raw: pd.DataFrame, scan_rows: int = 15) -> pd.DataFrame:
    """HR exports often have a title, date or blank rows above the real header.
    Use the first row (within the first `scan_rows`) that contains the most
    recognisable column names as the header."""
    from .schema import _header_key

    known = _known_header_keys()
    best_row, best_hits = 0, -1
    for i in range(min(scan_rows, len(raw))):
        hits = sum(_header_key(v) in known for v in raw.iloc[i].tolist() if pd.notna(v))
        if hits > best_hits:
            best_row, best_hits = i, hits
    header = [str(v).strip() if pd.notna(v) else f"unnamed_{j}" for j, v in enumerate(raw.iloc[best_row].tolist())]
    df = raw.iloc[best_row + 1:].reset_index(drop=True)
    df.columns = header
    df = df.dropna(how="all")  # blank lines, e.g. between blocks or at the end
    df = df.loc[:, [not (c.startswith("unnamed_") and df[c].isna().all()) for c in df.columns]]
    # Let pandas re-infer numbers and dates, as when the header is on row 1.
    return df.infer_objects()


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV (comma or semicolon) or Excel (first sheet) into a DataFrame."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        raw = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None)
    else:
        raw = _read_csv_rows(content)
    return _promote_header_row(raw)


def _read_csv_rows(content: bytes) -> pd.DataFrame:
    """Read a CSV whose rows may have different lengths (e.g. a title line above
    the header). Detects ; , or tab as separator and UTF-8 or Windows encoding."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    sample = lines[:50]
    sep = max((";", ",", "\t"), key=lambda d: sorted(ln.count(d) for ln in sample)[len(sample) // 2] if sample else 0)
    rows = list(csv.reader(lines, delimiter=sep))
    width = max((len(r) for r in rows), default=0)
    rows = [[(c.strip() or None) for c in r] + [None] * (width - len(r)) for r in rows]
    return pd.DataFrame(rows, dtype=object)


def find_file(stem: str, folder: Path = PRIVATE_DIR) -> Path | None:
    """Return folder/<stem>.xlsx|.xls|.csv, whichever exists first."""
    for ext in EXTENSIONS:
        p = folder / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def read_file(path: Path) -> pd.DataFrame:
    return read_table(path.read_bytes(), path.name)
