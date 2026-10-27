import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest
from reportlab.pdfgen.canvas import Canvas

from app.modules.intelligence import extraction_runtime as runtime
from app.modules.intelligence.document_worker import write_receipt
from app.modules.intelligence.documents import _extract, extract_document


def assert_stopped(pid):
    try:
        process = psutil.Process(pid)
        if process.status() != psutil.STATUS_ZOMBIE:
            process.wait(timeout=2)
    except psutil.NoSuchProcess:
        pass


def pdf(path):
    output = Canvas(str(path))
    output.drawString(40, 780, "Invoice No: SYNTHETIC-WORKER")
    output.save()
    return path


def success(digest):
    return dict(
        protocol=runtime.CONTRACT,
        input_sha256=digest,
        result=dict(
            original_sha256=digest,
            fields={},
            documents=[],
            pages=[{}],
            review_status="UNVERIFIED",
            human_review_required=True,
            network_document_transfer=False,
        ),
    )


def test_real_extraction_works_in_the_daemon_context_that_failed_before(monkeypatch, tmp_path):
    monkeypatch.setitem(multiprocessing.current_process()._config, "daemon", True)
    result = extract_document(pdf(tmp_path / "synthetic.pdf"), "application/pdf", "AE")
    assert result["fields"]["invoice_number"] == "SYNTHETIC-WORKER"
    assert result["local_worker_contract"] == runtime.CONTRACT
    assert result["review_status"] == "UNVERIFIED"


def test_unicode_source_paths_do_not_depend_on_the_child_console_encoding(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    monkeypatch.setenv("PYTHONUTF8", "0")
    folder = tmp_path / "شركة भारत"
    folder.mkdir()
    path = pdf(folder / "synthetic.pdf")
    result = extract_document(path, "application/pdf", "IN")
    assert result["original_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["fields"]["invoice_number"] == "SYNTHETIC-WORKER"


@pytest.mark.parametrize(
    "change",
    [
        "protocol",
        "input-hash",
        "original-hash",
        "pages",
        "fields",
        "documents",
        "review-status",
        "review-required",
        "network",
        "mixed-result",
        "unexpected-field",
    ],
)
def test_invalid_or_incorrectly_bound_receipts_never_become_results(change):
    receipt = success("a" * 64)
    if change == "protocol":
        receipt["protocol"] = "legacy"
    elif change == "input-hash":
        receipt["input_sha256"] = "b" * 64
    elif change == "original-hash":
        receipt["result"]["original_sha256"] = "b" * 64
    elif change == "pages":
        receipt["result"]["pages"] = []
    elif change == "fields":
        receipt["result"]["fields"] = []
    elif change == "documents":
        receipt["result"]["documents"] = {}
    elif change == "review-status":
        receipt["result"]["review_status"] = "REVIEWED"
    elif change == "review-required":
        receipt["result"]["human_review_required"] = False
    elif change == "network":
        receipt["result"]["network_document_transfer"] = True
    elif change == "mixed-result":
        receipt.update(error="ValueError", message="failed")
    else:
        receipt["unexpected"] = True
    with pytest.raises(ValueError, match="invalid or incorrectly bound"):
        runtime.read_receipt(json.dumps(receipt).encode(), "a" * 64)


@pytest.mark.parametrize(
    "content",
    [
        b"not JSON",
        b"\xff",
        b'{"protocol":1,"protocol":2}',
        b'{"value":NaN}',
        b'{"value":1e999}',
        b"[]",
    ],
)
def test_malformed_ambiguous_or_nonfinite_json_fails_closed(content):
    with pytest.raises(ValueError, match="invalid or incorrectly bound"):
        runtime.read_receipt(content, "a" * 64)


def test_private_result_file_avoids_native_stdout_and_is_removed_after_success(
    tmp_path, monkeypatch
):
    path = pdf(tmp_path / "source.pdf")
    outputs = []

    def run(args, **kwargs):
        assert args[1:] == ["-m", "app.modules.intelligence.document_worker"]
        assert kwargs["timeout"] == 120 and kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL and kwargs["encoding"] == "utf-8"
        assert kwargs["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        request = json.loads(kwargs["input"])
        output = Path(request["output"])
        outputs.append(output)
        write_receipt(output, success(request["expected_sha256"]))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime, "run_worker", run)
    result = extract_document(path, "application/pdf", "AE")
    assert result["local_worker_contract"] == runtime.CONTRACT
    assert not outputs[0].parent.exists()


@pytest.mark.parametrize(
    "failure", ["timeout", "start", "exit", "missing", "oversized", "partial", "provider"]
)
def test_timeout_start_crash_missing_partial_or_failed_receipts_never_publish(
    failure, tmp_path, monkeypatch
):
    path = pdf(tmp_path / "source.pdf")
    outputs = []

    def run(args, **kwargs):
        request = json.loads(kwargs["input"])
        output = Path(request["output"])
        outputs.append(output)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 120)
        if failure == "start":
            raise OSError("synthetic startup failure")
        if failure == "exit":
            return SimpleNamespace(returncode=17)
        if failure == "oversized":
            output.write_bytes(b"x" * 100)
        elif failure == "partial":
            output.with_suffix(".partial").write_bytes(b"incomplete")
        elif failure == "provider":
            write_receipt(
                output,
                dict(
                    protocol=runtime.CONTRACT,
                    input_sha256=request["expected_sha256"],
                    error="ValueError",
                    message="Synthetic unsupported document",
                ),
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime, "run_worker", run)
    if failure == "oversized":
        monkeypatch.setattr(runtime, "MAX_RECEIPT_BYTES", 99)
    with pytest.raises(ValueError):
        extract_document(path, "application/pdf", "AE")
    assert not outputs[0].parent.exists()


def test_hung_os_worker_is_actually_killed_and_reaped(tmp_path, monkeypatch):
    path = pdf(tmp_path / "source.pdf")
    pidfile = tmp_path / "pid.txt"
    real_run = runtime.run_worker

    def hung(args, **kwargs):
        kwargs["timeout"] = 1
        code = "import os,time; from pathlib import Path; Path(__import__('sys').argv[1]).write_text(str(os.getpid())); time.sleep(30)"
        return real_run([sys.executable, "-c", code, str(pidfile)], **kwargs)

    monkeypatch.setattr(runtime, "run_worker", hung)
    with pytest.raises(ValueError, match="worker bound"):
        extract_document(path, "application/pdf", "AE")
    assert pidfile.exists()
    assert_stopped(int(pidfile.read_text(encoding="utf-8")))


def test_successful_launcher_does_not_leave_a_running_descendant(tmp_path):
    from app.modules.intelligence.extraction_process import run_worker

    pidfile = tmp_path / "background-pid.txt"
    child = "import os,time; from pathlib import Path; Path(__import__('sys').argv[1]).write_text(str(os.getpid())); time.sleep(30)"
    parent = "import subprocess,sys,time; from pathlib import Path; subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); p=Path(sys.argv[2]); end=time.monotonic()+5\nwhile not p.exists() and time.monotonic()<end: time.sleep(.01)\nassert p.exists()"
    completed = run_worker(
        [sys.executable, "-c", parent, child, str(pidfile)],
        input="",
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert completed.returncode == 0 and pidfile.exists()
    pid = int(pidfile.read_text(encoding="utf-8"))
    assert_stopped(pid)


@pytest.mark.skipif(os.name != "nt", reason="Windows suspended-start and job-assignment control")
def test_job_assignment_failure_never_resumes_document_processing(tmp_path, monkeypatch):
    from app.modules.intelligence import extraction_process

    marker = tmp_path / "must-not-run.txt"
    assigned = []

    class BrokenJob:
        def assign_and_resume(self, pid):
            assigned.append(pid)
            raise OSError("Synthetic job assignment rejection")

        def terminate(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(extraction_process, "WindowsJob", BrokenJob)
    with pytest.raises(OSError, match="assignment rejection"):
        extraction_process.run_worker(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('unexpected')",
                str(marker),
            ],
            input="",
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    assert assigned and not marker.exists() and not psutil.pid_exists(assigned[0])


def test_changed_original_is_rejected_inside_the_actual_worker(tmp_path):
    path = pdf(tmp_path / "source.pdf")
    result = _extract(
        path, "application/pdf", "AE", dict(max_pages=20, max_bytes=25 * 1024 * 1024), "0" * 64
    )
    assert "result" not in result and "changed" in result["message"]


def test_hashing_and_worker_reads_remain_bounded_if_the_source_grows(tmp_path):
    path = tmp_path / "oversized.pdf"
    path.write_bytes(b"x" * 1025)
    with pytest.raises(ValueError, match="configured byte limit"):
        runtime.input_hash(path, 1024)
    result = _extract(
        path,
        "application/pdf",
        "AE",
        dict(max_pages=20, max_bytes=1024),
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    assert "result" not in result and "configured byte limit" in result["message"]


def test_oversized_receipt_is_not_published_as_a_complete_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.modules.intelligence.document_worker.MAX_RECEIPT_BYTES", 20)
    output = tmp_path / "result.json"
    with pytest.raises(ValueError, match="20 MiB"):
        write_receipt(output, {"result": "x" * 100})
    assert not output.exists()
