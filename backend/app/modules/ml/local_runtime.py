"""One reusable, bounded CPU inference process per application worker.

Only service-verified private artifacts and server-created request paths enter this protocol.
Training remains an independently cancellable subprocess.
"""

import atexit
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from app.core.config import settings

_lock = threading.Lock()
_process: subprocess.Popen | None = None


def shutdown():
    global _process
    if _process is not None:
        if _process.poll() is None:
            try:
                if _process.stdin:
                    _process.stdin.close()
                _process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                _process.kill()
                _process.wait(timeout=5)
        _process = None


atexit.register(shutdown)


def execute(
    runtime: str,
    worker: Path,
    root: Path,
    verified: dict[str, bytes],
    rows,
    scope: str = "isolated-test",
    config=None,
):
    global _process
    if not _lock.acquire(blocking=False):
        raise ValueError("ML_CAPACITY_REACHED: reusable inference worker is busy")
    try:
        cfg = settings()
        # Includes the complete private artifact receipt, not a user-supplied path.
        identity = hashlib.sha256(
            scope.encode() + b"".join(verified[name] for name in sorted(verified))
        ).hexdigest()
        directory = Path(cfg.ml_local_model_directory).resolve() / identity
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name, content in verified.items():
            target = directory / name
            if not target.exists() or target.read_bytes() != content:
                temporary = directory / (name + ".staging")
                temporary.write_bytes(content)
                temporary.replace(target)
        request, response = root / "persistent-request.json", root / "persistent-result.json"
        request.write_text(
            json.dumps(
                {
                    "operation": "infer",
                    "artifact_dir": str(directory),
                    "rows": rows,
                    "config": config,
                }
            )
        )
        if _process is None or _process.poll() is not None:
            shutdown()
            env = {
                **os.environ,
                "TF_NUM_INTRAOP_THREADS": str(cfg.ml_cpu_threads),
                "TF_NUM_INTEROP_THREADS": "1",
                "OMP_NUM_THREADS": str(cfg.ml_cpu_threads),
            }
            _process = subprocess.Popen(
                [runtime, f"--max-old-space-size={cfg.ml_worker_heap_mb}", str(worker), "--serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                env=env,
            )
        assert _process.stdin is not None
        _process.stdin.write(
            json.dumps({"request": str(request), "response": str(response)}) + "\n"
        )
        _process.stdin.flush()
        started = time.monotonic()
        while not response.is_file():
            if _process.poll() is not None:
                shutdown()
                raise ValueError("ML_INFERENCE_FAILED: persistent worker exited")
            if time.monotonic() - started > cfg.ml_worker_timeout_seconds:
                shutdown()
                raise TimeoutError("ML persistent inference exceeded wall-clock limit")
            time.sleep(0.01)
        result = json.loads(response.read_text())
        if result.get("execution_mode") == "unavailable":
            category = result.get("error_category", "ML_INFERENCE_FAILED")
            raise ValueError(
                category + ": local worker rejected inference; no fallback substituted"
            )
        return result, {}
    except (OSError, BrokenPipeError):
        shutdown()
        raise ValueError("ML_INFERENCE_FAILED: local worker communication failed") from None
    finally:
        _lock.release()
