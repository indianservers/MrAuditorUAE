import io
import uuid

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import settings
from app.infrastructure.ai_providers.adapters import MockProvider
from app.modules.ai_engine.schemas import AIRequest
from app.modules.connectors.secrets import decrypt, encrypt
from app.modules.financial_ai.schemas import OUTPUTS, Classification
from app.modules.lineage.storage import ObjectStore, hash_file


@pytest.mark.parametrize("task", list(OUTPUTS))
async def test_structured_financial_mock(task):
    identifier = str(uuid.uuid4())
    request = AIRequest(
        task_type=task,
        text='{"evidence_ids":["' + identifier + '"]}',
        model="mock-diagnostic",
        system_prompt="safe",
        max_tokens=512,
        request_id="test",
    )
    response = await MockProvider().generate(request)
    output = OUTPUTS[task].model_validate(response.output)
    assert output.requires_review is True and str(output.citations[0]) == identifier


def test_human_approval_cannot_be_fabricated():
    with pytest.raises(ValidationError):
        Classification(
            explanation="safe",
            citations=[],
            requires_review=False,
            proposed_classification="Assets",
            statement_group="Assets",
            confidence="high",
        )


def test_connector_secret_encryption(monkeypatch):
    config = settings()
    monkeypatch.setattr(config, "connector_encryption_key", Fernet.generate_key().decode())
    encoded = encrypt({"refresh_token": "sensitive"})
    assert "sensitive" not in encoded and decrypt(encoded) == {"refresh_token": "sensitive"}
    monkeypatch.setattr(config, "connector_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(ValueError):
        decrypt(encoded)


def test_private_immutable_objects(tmp_path, monkeypatch):
    monkeypatch.setattr(settings(), "source_storage_path", str(tmp_path))
    store = ObjectStore()
    tenant = str(uuid.uuid4())
    first = store.put(tenant, io.BytesIO(b"original"))
    second = store.put(tenant, io.BytesIO(b"original"))
    assert first["sha256"] == second["sha256"] and first["object_key"] != second["object_key"]
    with store.local(first["object_key"], first["object_version"]) as path:
        assert hash_file(path) == first["sha256"]
    with pytest.raises(ValueError):
        with store.local("../../secret", "bad"):
            pass
    monkeypatch.setattr(settings(), "max_upload_bytes", 1)
    with pytest.raises(ValueError):
        store.put(tenant, io.BytesIO(b"oversized"))


@pytest.mark.parametrize("versioning", ["Enabled", "Suspended"])
def test_s3_versioning_and_kms(tmp_path, monkeypatch, versioning):
    calls = []

    class S3:
        def get_bucket_versioning(self, **kwargs):
            return {"Status": versioning}

        def get_public_access_block(self, **kwargs):
            return {
                "PublicAccessBlockConfiguration": {
                    key: True
                    for key in [
                        "BlockPublicAcls",
                        "IgnorePublicAcls",
                        "BlockPublicPolicy",
                        "RestrictPublicBuckets",
                    ]
                }
            }

        def put_object(self, **kwargs):
            calls.append(kwargs)
            return {"VersionId": "test-version"}

    config = settings()
    monkeypatch.setattr(config, "source_s3_bucket", "synthetic-private-bucket")
    monkeypatch.setattr(config, "source_kms_key", "synthetic-kms-key")
    monkeypatch.setattr("app.modules.lineage.storage.boto3.client", lambda *args, **kwargs: S3())
    if versioning == "Suspended":
        with pytest.raises(ValueError):
            ObjectStore().put(str(uuid.uuid4()), io.BytesIO(b"original"))
    else:
        stored = ObjectStore().put(str(uuid.uuid4()), io.BytesIO(b"original"))
        assert (
            stored["object_version"] == "test-version"
            and calls[0]["ServerSideEncryption"] == "aws:kms"
        )


def test_generated_environment_has_valid_independent_keys(tmp_path, capsys):
    import runpy
    import shutil
    from pathlib import Path

    from cryptography.fernet import Fernet

    root = Path(__file__).resolve().parents[3]
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(root / "scripts/setup_env.py", tmp_path / "scripts/setup_env.py")
    shutil.copyfile(root / ".env.example", tmp_path / ".env.example")
    runpy.run_path(str(tmp_path / "scripts/setup_env.py"))
    content = (tmp_path / ".env").read_text()
    assert "replace-with-" not in content
    values = dict(
        line.split("=", 1)
        for line in content.splitlines()
        if "=" in line and not line.startswith("#")
    )
    Fernet(values["CONNECTOR_ENCRYPTION_KEY"].encode())
    assert (
        len(
            {
                values[k]
                for k in [
                    "JWT_SECRET",
                    "BOOTSTRAP_SECRET",
                    "POSTGRES_PASSWORD",
                    "POSTGRES_ADMIN_PASSWORD",
                    "CONNECTOR_ENCRYPTION_KEY",
                ]
            }
        )
        == 5
    )
    assert values["JWT_SECRET"] not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        runpy.run_path(str(tmp_path / "scripts/setup_env.py"))
    assert (tmp_path / ".env").read_text() == content
