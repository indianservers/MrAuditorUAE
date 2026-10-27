"""Private JSON protocol; native output never shares the result channel."""

import json
import sys
from pathlib import Path

from app.modules.intelligence.extraction_runtime import (
    CONTRACT,
    MAX_RECEIPT_BYTES,
    MAX_REQUEST_BYTES,
)


def write_receipt(path, receipt):
    partial = path.with_suffix(".partial")
    size = 0
    with partial.open("wb") as target:
        for text in json.JSONEncoder(
            ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).iterencode(receipt):
            chunk = text.encode("utf-8")
            size += len(chunk)
            if size > MAX_RECEIPT_BYTES:
                raise ValueError("Local extraction receipt exceeds its 20 MiB bound")
            target.write(chunk)
    partial.replace(path)


def main():
    content = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(content) > MAX_REQUEST_BYTES:
        raise ValueError("Local extraction request exceeds its 1 MiB bound")
    request = json.loads(content.decode("utf-8"))
    output = Path(request["output"])
    binding = dict(protocol=CONTRACT, input_sha256=request["expected_sha256"])
    try:
        from app.modules.intelligence.documents import _extract

        result = _extract(
            request["path"],
            request["media_type"],
            request["country"],
            request["options"],
            request["expected_sha256"],
        )
        write_receipt(output, {**binding, **result})
    except Exception as exc:
        write_receipt(output, {**binding, "error": type(exc).__name__, "message": str(exc)[:300]})


if __name__ == "__main__":
    main()
