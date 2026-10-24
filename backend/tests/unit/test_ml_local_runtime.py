import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.ml import local_runtime


def test_persistent_real_cpu_worker_reuses_process_and_checks_artifacts(tmp_path, monkeypatch):
    runtime = shutil.which("node")
    root = Path(__file__).resolve().parents[3] / "ml-engine"
    if not runtime or not (root / "dist/src/worker.js").is_file():
        pytest.skip("Build local TensorFlow CPU worker first")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    model = tmp_path / "model"
    script = """import {trainFoundation} from './dist/src/foundation.js';
import {syntheticPopulation} from './dist/src/fixtures.js';
import {writeFile} from 'node:fs/promises';
const rows=syntheticPopulation('journal-type');
await trainFoundation(rows,{task:'journal-type',epochs:2},process.argv[1]);
await writeFile(process.argv[2],JSON.stringify(rows.filter(r=>r.split==='test').slice(0,20)));
"""
    rows_file = tmp_path / "rows.json"
    subprocess.run(
        [runtime, "--input-type=module", "-e", script, str(model), str(rows_file)],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=30,
    )
    rows = json.loads(rows_file.read_text())
    cfg = SimpleNamespace(
        ml_local_model_directory=str(tmp_path / "private-models"),
        ml_worker_heap_mb=512,
        ml_cpu_threads=1,
        ml_worker_timeout_seconds=30,
    )
    monkeypatch.setattr(local_runtime, "settings", lambda: cfg)
    artifacts = {
        name: (model / name).read_bytes() for name in ("model.json", "weights.bin", "metadata.json")
    }
    local_runtime.shutdown()
    try:
        responses = []
        for n in range(2):
            directory = tmp_path / str(n)
            directory.mkdir()
            result, _ = local_runtime.execute(
                runtime,
                root / "dist/src/worker.js",
                directory,
                artifacts,
                rows,
                "tenant-A-private-receipt",
            )
            responses.append(result)
            if n == 0:
                pid = local_runtime._process.pid
            else:
                assert local_runtime._process.pid == pid
        assert responses[0] == responses[1]
        assert responses[0]["execution_mode"] == "trained_model"
        bad = {**artifacts, "weights.bin": b"corrupt"}
        directory = tmp_path / "bad"
        directory.mkdir()
        with pytest.raises(ValueError, match="ML_ARTIFACT_INVALID"):
            local_runtime.execute(
                runtime,
                root / "dist/src/worker.js",
                directory,
                bad,
                rows,
                "tenant-B-private-receipt",
            )
    finally:
        local_runtime.shutdown()
    assert local_runtime._process is None
