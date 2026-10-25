"""Assemble one complete MT940 statement from explicit sequenced messages."""

import re
from decimal import Decimal

MAX_MESSAGES = 100


def _block(text, start):
    """Bounded balanced header/trailer block; never treat it as booked data."""
    if start >= len(text) or text[start] != "{":
        raise ValueError("Unsupported MT940 FIN envelope")
    depth = 0
    for index in range(start, min(len(text), start + 10000)):
        if text[index] == "{":
            depth += 1
            if depth > 8:
                break
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1], index + 1
    raise ValueError("Unsupported MT940 FIN envelope")


def split_messages(content):
    try:
        text = content.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise ValueError(
            "MT940 must be UTF-8; select a verified encoding conversion before importing"
        ) from None
    if not text:
        raise ValueError("Empty MT940 source")
    if not text.startswith("{"):
        starts = list(re.finditer(r"(?m)^:20:", text))
        if not starts or text[: starts[0].start()].strip():
            raise ValueError("MT940 source must start with a message reference")
        if len(starts) > MAX_MESSAGES:
            raise ValueError("MT940 source exceeds 100 messages")
        return [
            text[
                match.start() : starts[index + 1].start() if index + 1 < len(starts) else len(text)
            ]
            for index, match in enumerate(starts)
        ]
    messages, position = [], 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        header, position = _block(text, position)
        if not header.startswith("{1:"):
            raise ValueError("Unsupported MT940 FIN envelope")
        application, position = _block(text, position)
        if not application.startswith(("{2:I940", "{2:O940")):
            raise ValueError("FIN application header must identify MT940")
        if text.startswith("{3:", position):
            _, position = _block(text, position)
        if not text.startswith("{4:", position):
            raise ValueError("Unsupported MT940 FIN envelope")
        closing = text.find("-}", position + 3)
        if closing < 0:
            raise ValueError("Unsupported MT940 FIN envelope")
        body = text[position + 3 : closing].strip()
        if "{" in body or "}" in body:
            raise ValueError("Unsupported braces in MT940 message body")
        messages.append(body)
        if len(messages) > MAX_MESSAGES:
            raise ValueError("MT940 source exceeds 100 messages")
        position = closing + 2
        if text.startswith("{5:", position):
            _, position = _block(text, position)
    return messages


def assemble(content, data, parse_page):
    messages = split_messages(content)
    pages, field_offset = [], 0
    for physical_index, message in enumerate(messages, 1):
        # A multipart selector refers to the first logical message, not every
        # page's distinct :20: reference. Cross-check it after sequence assembly.
        rows, metadata = parse_page(
            message.encode(),
            data.model_copy(update={"statement_identifier": None}) if len(messages) > 1 else data,
            intermediate=len(messages) > 1,
        )
        for row in rows:
            row.update(
                source_message_index=physical_index,
                source_message_field=row["source_row"],
                source_row=field_offset + row["source_row"],
            )
        field_offset += metadata["field_count"]
        if field_offset > 16000:
            raise ValueError("MT940 total field bound exceeded")
        pages.append({"rows": rows, "metadata": metadata, "physical_index": physical_index})
    if len(pages) == 1:
        metadata = pages[0]["metadata"]
        metadata.update(
            message_count=1,
            message_controls=[
                {**metadata, "source_message_index": 1, "entry_count": len(pages[0]["rows"])}
            ],
            source_message_order=[1],
            source_row_basis="MT940_FIELD_ORDINAL_NOT_PHYSICAL_LINE",
            assembly_contract="mt940-sequenced-messages/1",
        )
        return pages[0]["rows"], metadata
    numbered = {}
    statement_number = None
    for page in pages:
        sequence = page["metadata"]["statement_sequence"]
        match = re.fullmatch(r"(\d{1,5})/(\d{1,5})", sequence)
        if not match or int(match[2]) < 1:
            raise ValueError("Multipart MT940 requires explicit positive statement/page numbers")
        number, page_number = int(match[1]), int(match[2])
        if statement_number is not None and statement_number != number:
            raise ValueError("Multiple MT940 statements require separate source preparation")
        statement_number = number
        if page_number in numbered:
            raise ValueError("Duplicate MT940 message sequence")
        numbered[page_number] = page
    if sorted(numbered) != list(range(1, len(pages) + 1)):
        raise ValueError("Missing MT940 message sequence")
    ordered = [numbered[index] for index in range(1, len(pages) + 1)]
    first, last = ordered[0]["metadata"], ordered[-1]["metadata"]
    if data.statement_identifier and data.statement_identifier != first["statement_id"]:
        raise ValueError("MT940 statement identifier differs from the selection")
    rows, receipts = [], []
    previous = None
    for index, page in enumerate(ordered, 1):
        metadata = page["metadata"]
        if metadata["opening_tag"] != ("60F" if index == 1 else "60M") or metadata[
            "closing_tag"
        ] != ("62F" if index == len(ordered) else "62M"):
            raise ValueError(
                "Partial or inconsistent MT940 first/intermediate/final balance sequence"
            )
        if (metadata["account"], metadata["currency"]) != (first["account"], first["currency"]):
            raise ValueError("MT940 message accounts or currencies differ")
        if previous and (
            Decimal(metadata["opening"]) != Decimal(previous["closing"])
            or metadata["from"] != previous["through"]
        ):
            raise ValueError("MT940 intermediate balance amount or date does not carry forward")
        for row in page["rows"]:
            if not first["from"] <= row["date"] <= last["through"]:
                raise ValueError("MT940 entry date lies outside the complete statement period")
            row.update(
                id=f"{first['statement_id']}:entry:{len(rows) + 1}",
                source_message_sequence=index,
                source_message_reference=metadata["statement_id"],
                source_statement_number=str(statement_number),
            )
            rows.append(row)
            if len(rows) > 5000:
                raise ValueError("Native bank source exceeds 5,000 entries")
        receipts.append(
            {
                **metadata,
                "source_message_index": page["physical_index"],
                "entry_count": len(page["rows"]),
            }
        )
        previous = metadata
    if Decimal(first["opening"]) + sum(
        (Decimal(row["amount"]) for row in rows), Decimal(0)
    ) != Decimal(last["closing"]):
        raise ValueError(
            "MT940 assembled opening plus transactions does not agree to closing balance"
        )
    return rows, {
        **first,
        "closing": last["closing"],
        "through": last["through"],
        "closing_tag": last["closing_tag"],
        "field_count": field_offset,
        "statement_number": str(statement_number),
        "message_count": len(ordered),
        "message_controls": receipts,
        "source_message_order": [page["physical_index"] for page in ordered],
        "source_row_basis": "MT940_FIELD_ORDINAL_NOT_PHYSICAL_LINE",
        "assembly_contract": "mt940-sequenced-messages/1",
    }
