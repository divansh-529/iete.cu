"""Reads the Treasurer's list of paid members from an Excel or CSV file. Every problem is reported by
row and nothing is saved until the whole file is clean, so a partly loaded list can't happen."""
import csv
import io
from datetime import date, datetime
from pathlib import PurePath
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.core.errors import AppError

MAX_ROWS = 5000
MAX_ERRORS_SHOWN = 20
# Column -> the headings people actually use for it (compared without case, spaces or punctuation).
COLUMNS = {
    "holder_name": ("name", "membername", "studentname", "fullname"),
    "membership_no": ("membershipno", "membershipnumber", "membershipid"),
    "course": ("course", "branch"),
    "study_year": ("year", "yearofstudy"),
    "valid_to": ("membershipvalidupto", "membershipvalidtill", "membershipvalidity", "validupto", "validtill", "validto", "validity"),
}
HEADING = {"holder_name": "Name", "membership_no": "Membership no", "course": "Course",
           "study_year": "Year", "valid_to": "Membership valid upto"}
DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%d/%m/%y", "%d-%m-%y")


def _key(heading: object) -> str:
    return "".join(c for c in str(heading or "").lower() if c.isalnum())


def _text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():   # Excel stores 153 as 153.0
        value = int(value)
    return "" if value is None else str(value).strip()


def parse_date(value: object) -> date | None:
    """Day first, as dates are written in India. None if it can't be read."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(_text(value), fmt).date()
        except ValueError:
            continue
    return None


def _rows(filename: str, content: bytes) -> list[tuple]:
    extension = PurePath(filename.replace("\\", "/")).suffix.lower()
    if extension == ".csv":
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = content.decode("cp1252", errors="replace")
        return [tuple(r) for r in csv.reader(io.StringIO(decoded))]
    if extension == ".xlsx":
        try:
            book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                rows = []
                for row in book.worksheets[0].iter_rows(values_only=True):
                    rows.append(row)
                    if len(rows) > MAX_ROWS + 1:
                        break
                return rows
            finally:
                book.close()
        except (BadZipFile, InvalidFileException, KeyError, ValueError, IndexError):
            raise AppError(422, "FILE_CONTENT", "This file can't be read. Save it again as .xlsx or .csv and retry.")
    raise AppError(422, "FILE_TYPE", "Upload an Excel (.xlsx) or CSV file. In Excel, choose Save As and pick one of those.")


def read_members(filename: str, content: bytes) -> list[dict]:
    if not content:
        raise AppError(422, "FILE_EMPTY", "This file is empty.")
    rows = [(i, r) for i, r in enumerate(_rows(filename, content), start=1) if any(_text(c) for c in r)]
    if not rows:
        raise AppError(422, "FILE_EMPTY", "This file has no rows.")
    (_, header), body = rows[0], rows[1:]
    positions = {}
    for position, heading in enumerate(header):
        for field, names in COLUMNS.items():
            if _key(heading) in names and field not in positions:
                positions[field] = position
    missing = [HEADING[f] for f in COLUMNS if f not in positions]
    if missing:
        raise AppError(422, "MISSING_COLUMNS", f"The first row must have these column headings. Missing: {', '.join(missing)}.")
    if not body:
        raise AppError(422, "FILE_EMPTY", "This file has headings but no members.")
    if len(body) > MAX_ROWS:
        raise AppError(422, "TOO_MANY_ROWS", f"Upload at most {MAX_ROWS} members at a time.")

    members, errors, seen = [], [], {}
    for number, row in body:
        cell = lambda field: row[positions[field]] if positions[field] < len(row) else None   # noqa: E731
        member = {field: _text(cell(field)) for field in COLUMNS if field != "valid_to"}
        problems = [f"{HEADING[f]} is empty" for f, v in member.items() if not v]
        valid = cell("valid_to")
        member["valid_to"] = parse_date(valid)
        if not _text(valid):
            problems.append(f"{HEADING['valid_to']} is empty")
        elif member["valid_to"] is None:
            problems.append(f"{HEADING['valid_to']} “{_text(valid)}” isn't a date. Use day/month/year")
        too_long = [HEADING[f] for f, v in member.items() if isinstance(v, str) and len(v) > 120]
        if too_long:
            problems.append(f"{', '.join(too_long)} is too long")
        no = member["membership_no"]
        if no and no in seen:
            problems.append(f"Membership no {no} is also on row {seen[no]}")
        elif no:
            seen[no] = number
        if problems:
            errors.append({"field": f"Row {number}", "message": "; ".join(problems)})
        members.append(member)
    if errors:
        more = len(errors) - MAX_ERRORS_SHOWN
        raise AppError(422, "ROWS_INVALID", f"Nothing was saved. Fix {len(errors)} row(s) and upload again.",
                       errors[:MAX_ERRORS_SHOWN] + ([{"field": "And", "message": f"{more} more row(s)"}] if more > 0 else []))
    return members
