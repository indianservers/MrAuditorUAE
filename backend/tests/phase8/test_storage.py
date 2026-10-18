import os
import uuid
from io import BytesIO
from pathlib import Path

from app.core.config import settings
from app.modules.lineage import storage


def test_generated_document_is_readable_across_cli_and_api_working_directories(
    monkeypatch, tmp_path
):
    relative = os.path.relpath(tmp_path / "objects", Path(storage.__file__).resolve().parents[3])
    monkeypatch.setattr(settings(), "source_storage_path", relative)
    monkeypatch.setattr(settings(), "source_s3_bucket", "")
    first = tmp_path / "cli"
    second = tmp_path / "api"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    writer = storage.ObjectStore()
    metadata = writer.put(str(uuid.uuid4()), BytesIO(b"SYNTHETIC published document"))
    monkeypatch.chdir(second)
    reader = storage.ObjectStore()
    assert reader.root == writer.root
    with reader.local(metadata["object_key"], metadata["object_version"]) as path:
        assert path.read_bytes() == b"SYNTHETIC published document"
        assert storage.hash_file(path) == metadata["sha256"]
