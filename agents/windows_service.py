"""Tally service source. Run under the Windows account enrolled in the credential vault."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil


class TallyReaderService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AuditOSTallyReader"
    _svc_display_name_ = "AuditOS Tally accounting reader"

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        root = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "AuditOS" / "Tally"
        configuration = root / "config.json"
        while True:
            try:
                config = json.loads(configuration.read_text(encoding="utf-8"))
                interval = max(300, min(int(config.get("interval_seconds", 3600)), 86400))
                run_dir = root / "runs" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                run_dir.mkdir(parents=True, exist_ok=False)
                run_config = run_dir / "config.json"
                run_config.write_text(json.dumps(config), encoding="utf-8")
                # No shell, inherited credentials or logged API bodies. Evidence and
                # resume state remain in this service account's protected directory.
                result = subprocess.run([config["python_executable"], str(Path(__file__).with_name("tally_agent.py")),
                    str(run_config)], capture_output=True, timeout=3600, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                servicemanager.LogInfoMsg("AuditOS Tally extraction completed" if result.returncode == 0 else "AuditOS Tally extraction failed; inspect preserved package and sync diagnostics")
            except Exception:
                interval = 3600
                servicemanager.LogErrorMsg("AuditOS Tally service failed; check configuration, local Tally and vault enrollment")
            if win32event.WaitForSingleObject(self.stop_event, interval * 1000) == win32event.WAIT_OBJECT_0:
                return


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(TallyReaderService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(TallyReaderService)
