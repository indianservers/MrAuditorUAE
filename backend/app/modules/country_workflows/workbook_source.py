"""Value-only worksheets into existing canonical contracts; no inferred columns."""

import csv
import hashlib
import io
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.country_workflows.sources import MAX_BYTES, parse_csv
from app.modules.ingestion.parser import spreadsheet_rows


def parse_workbook(content, data, defaults=None, *, expected_sha256):
    if len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Workbook byte limit or original evidence hash verification failed")
    if not data.workbook_sheet:
        raise ValueError("Select the original worksheet explicitly")
    receipt: dict[str, Any] = {}
    positions, types = [], []
    output = io.StringIO(newline="")
    writer = csv.writer(output)

    def headers(fields):
        if (
            not fields
            or len(set(fields)) != len(fields)
            or any(not f or len(f) > 120 for f in fields)
        ):
            raise ValueError("Workbook requires distinct non-empty bounded headers")
        writer.writerow(fields)

    with tempfile.TemporaryDirectory(prefix="auditos-workflow-sheet-") as directory:
        path = Path(directory) / "original.xlsx"
        path.write_bytes(content)
        for number, row in spreadsheet_rows(
            path,
            data.workbook_sheet,
            validate_headers=headers,
            max_rows=5000,
            receipt=receipt,
            exact_numbers=True,
        ):
            dates = receipt["date_columns_by_row"].pop(number, [])
            numeric = receipt["numeric_columns_by_row"].pop(number, [])
            for name in dates:
                value = datetime.fromisoformat(row[name])
                if value.time() != datetime.min.time() or value.tzinfo is not None:
                    raise ValueError(
                        "Workbook date cells must contain dates without time or timezone"
                    )
                row[name] = value.date().isoformat()
            writer.writerow(row.values())
            if output.tell() > MAX_BYTES:
                raise ValueError("Serialized workbook exceeds the 10 MiB canonical source bound")
            positions.append(number)
            types.append({"numeric_columns": numeric, "date_columns": dates})
    result = parse_csv(output.getvalue().encode("utf-8"), data, defaults)
    for row, number, storage in zip(result["rows"], positions, types, strict=True):
        row.update(
            source_worksheet=receipt["sheet"], source_row=number, source_cell_storage=storage
        )
    result["parser_version"] = "country-workbook-1"
    result["workbook_metadata"] = {
        "format": "XLSX_VALUE_ONLY_CANONICAL_FIELDS",
        "original_sha256": expected_sha256,
        "worksheet": receipt["sheet"],
        "original_headers": receipt["raw_headers"],
        "unselected_worksheets": [
            name for name in receipt["available_worksheets"] if name != receipt["sheet"]
        ],
        "excel_epoch": receipt["excel_epoch"],
        "assessment": data.workbook_assessment.strip(),
        "numeric_basis": "ORIGINAL_NUMERIC_XML_NOT_FORMATTED_DISPLAY",
        "population_basis": "SELECTED_WORKSHEET_NOT_WORKBOOK_COMPLETENESS",
    }
    return result
