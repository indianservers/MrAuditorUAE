"""One bounded OS worker per extraction, with a private, hash-bound JSON receipt."""

import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from app.modules.intelligence.extraction_process import run_worker

CONTRACT = "bounded-document-subprocess/1"
TIMEOUT_SECONDS = 120
MAX_RECEIPT_BYTES = 20 * 1024 * 1024
MAX_REQUEST_BYTES = 1024 * 1024


def input_hash(path, max_bytes):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("OCR document exceeds configured byte limit")
            digest.update(chunk)
    return digest.hexdigest()


def read_receipt(content, expected_hash):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate receipt field")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Non-finite receipt value")

    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite receipt value")
        return number

    try:
        receipt = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid,
            parse_float=finite,
        )
        if (
            not isinstance(receipt, dict)
            or receipt.get("protocol") != CONTRACT
            or receipt.get("input_sha256") != expected_hash
        ):
            raise ValueError("Wrong receipt binding")
        if set(receipt) == {"protocol", "input_sha256", "error", "message"}:
            if (
                not isinstance(receipt["error"], str)
                or not isinstance(receipt["message"], str)
                or len(receipt["message"]) > 300
            ):
                raise ValueError("Invalid failure receipt")
            return receipt
        if set(receipt) != {"protocol", "input_sha256", "result"}:
            raise ValueError("Unexpected receipt fields")
        result = receipt["result"]
        if (
            not isinstance(result, dict)
            or result.get("original_sha256") != expected_hash
            or not isinstance(result.get("fields"), dict)
            or not isinstance(result.get("documents"), list)
            or not isinstance(result.get("pages"), list)
            or not result["pages"]
            or result.get("review_status") != "UNVERIFIED"
            or result.get("human_review_required") is not True
            or result.get("network_document_transfer") is not False
        ):
            raise ValueError("Incomplete extraction receipt")
        return receipt
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        raise ValueError(
            "Local extraction returned an invalid or incorrectly bound receipt"
        ) from None


def extract(path, media_type, country, options):
    digest = input_hash(path, options["max_bytes"])
    with tempfile.TemporaryDirectory(prefix="auditos-extraction-") as directory:
        output = Path(directory) / "receipt.json"
        request = dict(
            path=str(Path(path).resolve()),
            media_type=media_type,
            country=country,
            options=options,
            expected_sha256=digest,
            output=str(output),
        )
        encoded = json.dumps(request, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise ValueError("Local extraction request exceeds its 1 MiB bound")
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            completed = run_worker(
                [sys.executable, "-m", "app.modules.intelligence.document_worker"],
                input=encoded,
                text=True,
                encoding="utf-8",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=TIMEOUT_SECONDS,
                check=False,
                cwd=Path(__file__).resolve().parents[3],
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("Local extraction exceeded its 120-second worker bound") from None
        except OSError:
            raise ValueError("Local extraction worker could not be started") from None
        if completed.returncode:
            raise ValueError(
                f"Local extraction worker exited without a successful receipt (exit code {completed.returncode})"
            )
        try:
            with output.open("rb") as source:
                content = source.read(MAX_RECEIPT_BYTES + 1)
        except OSError:
            raise ValueError("Local extraction worker exited without a receipt") from None
        if len(content) > MAX_RECEIPT_BYTES:
            raise ValueError("Local extraction receipt exceeds its 20 MiB bound")
        receipt = read_receipt(content, digest)
        if "error" in receipt:
            raise ValueError("Local extraction failed: " + receipt["message"])
        return {**receipt["result"], "local_worker_contract": CONTRACT}
