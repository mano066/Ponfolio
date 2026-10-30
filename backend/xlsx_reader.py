"""Minimal XLSX reader, standard library only.

Kite Console exports .xlsx, and the app ships a frozen embedded Python. Adding
openpyxl or pandas' Excel engine to that runtime would grow the installer for
one file format, so this reads the format directly: an .xlsx is a zip of XML,
and the two parts that matter are the sheet grid and the shared string table.

What is deliberately NOT implemented: formulas (the cached value is read
instead), styles, dates as serial numbers (Kite writes dates as text), merged
cells beyond their anchor value, and streaming for huge sheets. A Console
export is a few hundred rows, so the whole sheet is materialised.
"""

from __future__ import annotations

import re
import zipfile
from typing import Dict, List
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# A Console export is small; this only exists so a wrong file cannot exhaust
# memory (a zip bomb, or someone's 200MB report).
MAX_CELLS = 500_000


class XlsxError(ValueError):
    """The upload is not a readable xlsx workbook."""


def _column_index(ref: str) -> int:
    """'A1' -> 0, 'B7' -> 1, 'AA3' -> 26."""
    match = re.match(r"([A-Za-z]+)", ref or "")
    if not match:
        return 0
    index = 0
    for char in match.group(1).upper():
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in si.iter(f"{NS}t"))
            for si in root.findall(f"{NS}si")]


def _cell_value(cell: ET.Element, shared: List[str]) -> str:
    kind = cell.get("t")
    if kind == "s":                                  # shared string
        value = cell.find(f"{NS}v")
        if value is None or value.text is None:
            return ""
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError):
            return ""
    if kind == "inlineStr":
        inline = cell.find(f"{NS}is")
        return ("".join(n.text or "" for n in inline.iter(f"{NS}t"))
                if inline is not None else "")
    value = cell.find(f"{NS}v")                      # number, bool, or cached
    return value.text or "" if value is not None else ""


def sheets(blob: bytes) -> Dict[str, List[List[str]]]:
    """Every worksheet in the workbook, as ``{sheet part name: rows}``.

    Cells come back as strings — Console writes dates and quantities as text
    and the callers parse what they need, so no type is guessed here. Rows are
    ragged: trailing empty cells are not padded.
    """
    try:
        archive = zipfile.ZipFile(_as_stream(blob))
    except (zipfile.BadZipFile, OSError) as exc:
        raise XlsxError(
            "Not a readable .xlsx file. Export it again from Kite Console, or "
            "upload the CSV version instead."
        ) from exc

    with archive:
        names = [n for n in archive.namelist()
                 if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        if not names:
            raise XlsxError("The workbook has no worksheets.")
        shared = _shared_strings(archive)
        out: Dict[str, List[List[str]]] = {}
        budget = MAX_CELLS
        for name in sorted(names, key=_sheet_order):
            rows: List[List[str]] = []
            root = ET.fromstring(archive.read(name))
            for row in root.iter(f"{NS}row"):
                cells: Dict[int, str] = {}
                for cell in row.findall(f"{NS}c"):
                    budget -= 1
                    if budget <= 0:
                        raise XlsxError("The workbook is too large to read.")
                    cells[_column_index(cell.get("r", "A1"))] = \
                        _cell_value(cell, shared)
                width = max(cells) + 1 if cells else 0
                rows.append([cells.get(i, "") for i in range(width)])
            out[name] = rows
        return out


def _sheet_order(name: str) -> tuple:
    """sheet2 must not sort before sheet10 — order by the trailing number."""
    match = re.search(r"(\d+)", name.rsplit("/", 1)[-1])
    return (int(match.group(1)) if match else 0, name)


def _as_stream(blob: bytes):
    import io
    return io.BytesIO(blob)


def find_row(rows: List[List[str]], *required: str, limit: int = 60) -> int:
    """Index of the first row containing every one of ``required``.

    Console puts a client-id block and a title above each table, and the
    number of preamble rows differs between the tradebook and the P&L export,
    so the header is located by its content rather than by a fixed offset.
    Returns -1 when the table is not present.
    """
    wanted = [r.strip().lower() for r in required]
    for index, row in enumerate(rows[:limit]):
        cells = [str(c).strip().lower() for c in row]
        if all(any(w == c or w in c for c in cells) for w in wanted):
            return index
    return -1


def header_map(row: List[str]) -> Dict[str, int]:
    """``{normalised column name: index}`` for a header row."""
    out: Dict[str, int] = {}
    for index, cell in enumerate(row):
        key = re.sub(r"[^a-z0-9]+", "_", str(cell).strip().lower()).strip("_")
        if key and key not in out:
            out[key] = index
    return out


def cell(row: List[str], index: int) -> str:
    """Bounds-safe read: Console rows are ragged."""
    return str(row[index]).strip() if 0 <= index < len(row) else ""


def number(value, default: float = 0.0) -> float:
    """Parse a Console number: may carry commas, a currency symbol or blanks."""
    text = re.sub(r"[,\s₹]", "", str(value or ""))
    if not text or text in {"-", "--"}:
        return default
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        out = float(text)
    except ValueError:
        return default
    if out != out or abs(out) == float("inf"):
        return default
    return -out if negative else out


def period_from_title(rows: List[List[str]]) -> Dict[str, str]:
    """The ``from YYYY-MM-DD to YYYY-MM-DD`` range Console writes in the title.

    The period is what makes monthly imports safe to accumulate: it is the key
    a statement is stored under, so re-uploading a month replaces it instead
    of doubling it, and an overlapping range can be refused. Reading it from
    the file also means the user never re-types the dates they already chose
    in Console.
    """
    for row in rows[:20]:
        for value in row:
            match = re.search(
                r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})",
                str(value), re.I)
            if match:
                return {"from": match.group(1), "to": match.group(2),
                        "title": str(value).strip()}
    return {"from": "", "to": "", "title": ""}
