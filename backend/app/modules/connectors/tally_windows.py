"""Bounded native XML windows; memory follows one window, not the whole year."""

import base64
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.modules.connectors.tally import parse_export, trial_balance_rows
from app.modules.connectors.zoho import ConnectorError


def package_rows(path, options):
    with path.open("rb") as stream:
        def record():
            line = stream.readline(90 * 1024 * 1024 + 1)
            if len(line) > 90 * 1024 * 1024:
                raise ConnectorError("Tally window exceeds package record limit; use a smaller date window")
            return json.loads(line) if line else None

        header = record()
        if not isinstance(header, dict) or header.get("format") != "tally-window-package/1" or header.get("company") != options.tally_company:
            raise ConnectorError("Invalid Tally window package identity")
        start, end = date.fromisoformat(header["start_date"]), date.fromisoformat(header["end_date"])
        masters = parse_export(base64.b64decode(header["masters_xml"], validate=True), options.tally_company,
            start, end, expected_fingerprint=options.tally_company_fingerprint)
        expected = start
        seen = set()
        movements: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
        finished = False
        while (item := record()) is not None:
            first, last = date.fromisoformat(item["start_date"]), date.fromisoformat(item["end_date"])
            if finished or first != expected or first > last or last > end:
                raise ConnectorError("Tally windows overlap, omit dates, or exceed the selected period")
            result = parse_export(base64.b64decode(item["xml"], validate=True), options.tally_company,
                                  first, last, master_catalog=masters["masters"])
            for revision in result["voucher_revisions"]:
                identity = revision["guid"]
                if not identity or identity in seen:
                    raise ConnectorError("Repeated or missing voucher identity across Tally windows")
                seen.add(identity)
            for row in result["lines"]:
                if options.kind in {"gl", "journals"}:
                    yield row
                movements[row["account_code"]][0] += Decimal(row["debit"])
                movements[row["account_code"]][1] += Decimal(row["credit"])
            finished = last == end
            if not finished:
                expected = last + timedelta(days=1)
        if not finished:
            raise ConnectorError("Tally package is missing terminal period coverage")
        if options.kind == "coa":
            for name, master in masters["masters"].items():
                yield {"account_code": name, "account_name": name, "source_id": "ledger:" + name,
                       "source_group": master.get("group") or ""}
        elif options.kind == "tb":
            masters["lines"] = [{"account_code": code, "debit": str(values[0]), "credit": str(values[1])}
                                for code, values in movements.items()]
            yield from trial_balance_rows(masters)
