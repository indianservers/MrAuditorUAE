"""Attachment-only evidence, structural validation and fail-closed ClamAV scanning."""

import socket
import struct
import zipfile
from pathlib import Path

from app.core.config import settings

TYPES = {
    ".txt": "text/plain",
    ".ecr": "text/plain",
    ".json": "application/json",
    ".xml": "application/xml",
    ".mt940": "text/plain",
    ".sta": "text/plain",
    ".sif": "text/csv",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".zip": "application/zip",
}


def validate_file(stream, filename):
    extension = Path(filename).suffix.lower()
    if extension not in TYPES:
        raise ValueError(
            "Supported evidence: PDF, CSV, JSON, XML, UTF-8 TXT/ECR, MT940/STA, SIF, XLSX, DOCX, images and bounded document ZIP"
        )
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
    if extension in {".tif", ".tiff"} and not header.startswith((b"II*\x00", b"MM\x00*")):
        raise ValueError("Evidence signature differs from filename")
    if extension == ".zip":
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            entries = [e for e in archive.infolist() if not e.is_dir()]
            if (
                not entries
                or len(entries) > 20
                or sum(e.file_size for e in entries) > 100 * 1024 * 1024
            ):
                raise ValueError("Document ZIP limits exceeded")
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                if (
                    ".." in name.split("/")
                    or name.startswith("/")
                    or ":" in name
                    or Path(name).suffix.lower()
                    not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
                    or entry.file_size / max(1, entry.compress_size) > 200
                ):
                    raise ValueError("Unsafe document ZIP")
    if extension == ".csv" and (b"\x00" in header or header.lstrip().startswith((b"<", b"MZ"))):
        raise ValueError("Invalid CSV evidence")
    if extension in {".txt", ".ecr", ".json", ".xml", ".mt940", ".sta", ".sif"}:
        stream.seek(0)
        content = stream.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024 or b"\x00" in content:
            raise ValueError("Structured evidence exceeds limits or contains null bytes")
        if extension in {".txt", ".ecr"}:
            try:
                decoded = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValueError("Text evidence must use UTF-8 encoding") from None
            if any(ord(ch) < 32 and ch not in "\r\n\t" for ch in decoded):
                raise ValueError("Text evidence contains unsupported control characters")
        elif extension == ".json":
            from app.core.json_documents import read_json_document

            if not isinstance(read_json_document(content), (dict, list)):
                raise ValueError("JSON evidence must contain an object or array")
        elif extension == ".xml":
            from defusedxml import ElementTree as safe_xml

            try:
                safe_xml.fromstring(
                    content, forbid_dtd=True, forbid_entities=True, forbid_external=True
                )
            except Exception:
                raise ValueError("Invalid or unsafe XML evidence") from None
        elif extension == ".sif" and not content.lstrip(b"\xef\xbb\xbf").startswith(
            (b"EDR,", b"SCR,")
        ):
            raise ValueError("Invalid SIF evidence record signature")
        elif extension in {".mt940", ".sta"} and not content.lstrip(
            b"\xef\xbb\xbf\r\n "
        ).startswith((b":20:", b"{1:")):
            raise ValueError("Invalid MT940 evidence record signature")
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
