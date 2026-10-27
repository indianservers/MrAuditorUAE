"""Stop only the extraction process tree, including Windows venv redirectors."""

import ctypes
import os
import signal
import subprocess
import sys
import time

import psutil

if sys.platform == "win32":

    class WindowsJob:
        def __init__(self):
            from ctypes import wintypes as w

            class Limits(ctypes.Structure):
                _fields_ = [
                    ("process_time", ctypes.c_int64),
                    ("job_time", ctypes.c_int64),
                    ("flags", w.DWORD),
                    ("min_ws", ctypes.c_size_t),
                    ("max_ws", ctypes.c_size_t),
                    ("processes", w.DWORD),
                    ("affinity", ctypes.c_size_t),
                    ("priority", w.DWORD),
                    ("scheduling", w.DWORD),
                ]

            class IO(ctypes.Structure):
                _fields_ = [
                    (name, ctypes.c_uint64)
                    for name in (
                        "read_ops",
                        "write_ops",
                        "other_ops",
                        "read_bytes",
                        "write_bytes",
                        "other_bytes",
                    )
                ]

            class Extended(ctypes.Structure):
                _fields_ = [
                    ("basic", Limits),
                    ("io", IO),
                    ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t),
                    ("peak_job", ctypes.c_size_t),
                ]

            class Accounting(ctypes.Structure):
                _fields_ = [
                    (name, ctypes.c_int64)
                    for name in ("user", "kernel", "period_user", "period_kernel")
                ] + [(name, w.DWORD) for name in ("faults", "total", "active", "terminated")]

            self.accounting = Accounting
            self.api = ctypes.WinDLL("kernel32", use_last_error=True)
            specs = {
                "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
                "SetInformationJobObject": (
                    [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD],
                    w.BOOL,
                ),
                "QueryInformationJobObject": (
                    [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p],
                    w.BOOL,
                ),
                "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
                "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
                "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
                "CloseHandle": ([w.HANDLE], w.BOOL),
            }
            for name, (args, result) in specs.items():
                function = getattr(self.api, name)
                function.argtypes = args
                function.restype = result
            self.handle = self.api.CreateJobObjectW(None, None)
            if not self.handle:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no breakaway.
            if not self.api.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                error = ctypes.WinError(ctypes.get_last_error())
                self.close()
                raise error

        def assign_and_resume(self, pid):
            handle = self.api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not self.api.AssignProcessToJobObject(self.handle, handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                self.api.CloseHandle(handle)
            psutil.Process(pid).resume()

        def terminate(self):
            if not self.api.TerminateJobObject(self.handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
            deadline = time.monotonic() + 2
            while True:
                counts = self.accounting()
                if not self.api.QueryInformationJobObject(
                    self.handle, 1, ctypes.byref(counts), ctypes.sizeof(counts), None
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not counts.active:
                    return
                if time.monotonic() >= deadline:
                    raise OSError("Extraction job termination could not be confirmed")
                time.sleep(0.01)

        def close(self):
            if self.handle:
                self.api.CloseHandle(self.handle)
                self.handle = None


def run_worker(args, **kwargs):
    payload, timeout = kwargs.pop("input"), kwargs.pop("timeout")
    kwargs.pop("check", None)
    job = None
    if sys.platform == "win32":
        job = WindowsJob()
    if job is not None:
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x4  # CREATE_SUSPENDED
    else:
        kwargs["start_new_session"] = True
    try:
        with subprocess.Popen(args, stdin=subprocess.PIPE, **kwargs) as process:
            try:
                if job is not None:
                    job.assign_and_resume(process.pid)
                stdout, stderr = process.communicate(input=payload, timeout=timeout)
                return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
            finally:
                # The venv executable may be a redirector whose Python child has
                # another PID. Killing only the redirector leaves parsing alive.
                try:
                    if job is not None:
                        job.terminate()
                    elif sys.platform != "win32":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=2)
    finally:
        if job is not None:
            job.close()
