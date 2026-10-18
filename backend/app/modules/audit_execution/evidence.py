"""Attachment-only evidence, structural validation and fail-closed ClamAV scanning."""

import socket
import struct
import zipfile
from pathlib import Path

from app.core.config import settings

TYPES = {
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def validate_file(stream, filename):
    extension = Path(filename).suffix.lower()
    if extension not in TYPES:
        raise ValueError("Supported evidence: PDF, CSV, XLSX, DOCX, PNG and JPEG")
    stream.seek(0)
    header = stream.read(1024)
    if not header:
        raise ValueError("Empty evidence")
    signatures = {
        ".pdf": b"%PDF-",
        ".png": b"\x89PNG\r\n\x1a\n",
        ".jpg": b"\xff\xd8\xff",
        ".jpeg": b"\xff\xd8\xff",
    }
    if extension in signatures and not header.startswith(signatures[extension]):
        raise ValueError("Evidence signature differs from filename")
    if extension == ".csv" and (b"\x00" in header or header.lstrip().startswith((b"<", b"MZ"))):
        raise ValueError("Invalid CSV evidence")
    if extension in {".xlsx", ".docx"}:
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > 5000 or sum(e.file_size for e in entries) > 128 * 1024 * 1024:
                raise ValueError("Archive exceeds evidence limits")
            for entry in entries:
                name = entry.filename.lower()
                if any(
                    x in name for x in ["vbaproject", "externallinks/", "embeddings/", "../"]
                ) or (
                    entry.file_size > 1000000
                    and entry.file_size / max(1, entry.compress_size) > 200
                ):
                    raise ValueError("Unsafe Office archive")
                if name.endswith(".rels") and b'TargetMode="External"' in archive.read(entry):
                    raise ValueError("Office external relationships prohibited")
    stream.seek(0)
    return TYPES[extension]


def scan(stream):
    config = settings()
    if not config.evidence_clamav_host:
        return "QUARANTINED"
    try:
        with socket.create_connection(
            (config.evidence_clamav_host, config.evidence_clamav_port), timeout=20
        ) as client:
            client.sendall(b"zINSTREAM\x00")
            stream.seek(0)
            while chunk := stream.read(65536):
                client.sendall(struct.pack("!I", len(chunk)) + chunk)
            client.sendall(struct.pack("!I", 0))
            reply = client.recv(4096)
            return "CLEAN" if reply.rstrip(b"\x00\n").endswith(b": OK") else "REJECTED"
    except OSError:
        return "QUARANTINED"
    finally:
        stream.seek(0)
