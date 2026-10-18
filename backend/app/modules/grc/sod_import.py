import csv
import io

from app.modules.grc.schemas import AccessAssignment


def parse(content: bytes):
    if not content or len(content) > 4 * 1024 * 1024:
        raise ValueError("ERP access CSV requires 1 byte to 4 MiB")
    source = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    required = {"principal", "permission", "scope", "valid_from"}
    if (
        not source.fieldnames
        or not required <= set(source.fieldnames)
        or set(source.fieldnames) - required - {"valid_to"}
    ):
        raise ValueError("CSV columns: principal, permission, scope, valid_from, optional valid_to")
    rows, seen = [], set()
    for index, row in enumerate(source):
        if index >= 10000 or None in row:
            raise ValueError(
                "Partition ERP access files above 10000 rows; inconsistent columns rejected"
            )
        item = AccessAssignment.model_validate({**row, "valid_to": row.get("valid_to") or None})
        if item.valid_to and item.valid_to < item.valid_from:
            raise ValueError("Access validity end precedes start")
        key = (item.principal, item.permission, item.scope, item.valid_from, item.valid_to)
        if key in seen:
            raise ValueError("Duplicate access assignment")
        seen.add(key)
        rows.append(item.model_dump(mode="json"))
    if not rows:
        raise ValueError("Access CSV has no assignments")
    return rows
