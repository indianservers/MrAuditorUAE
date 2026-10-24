"""Bounded JSON documents with no duplicate keys or non-finite numeric literals."""

import json
from decimal import Decimal


def read_json_document(content):
    if len(content) > 10 * 1024 * 1024 or b"\x00" in content:
        raise ValueError("JSON evidence exceeds limits or contains null bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON fields are not permitted")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Non-finite JSON numbers are not permitted")

    try:
        return json.loads(
            content.decode("utf-8-sig"),
            parse_float=Decimal,
            parse_constant=invalid,
            object_pairs_hook=pairs,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ValueError("Invalid, ambiguous or excessively nested JSON evidence") from None
