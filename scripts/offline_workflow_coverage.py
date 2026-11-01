"""Pytest observer for actual country-workflow execution in passing test cases.

Use --offline-workflow-coverage PATH. This records execution, not legal coverage.
It never captures client inputs or calculation output values.
"""

import json
import sys
import threading
from collections import defaultdict
from pathlib import Path

import pytest

events = defaultdict(set)
passed = defaultdict(lambda: defaultdict(set))
active = None
target = None
previous = None
previous_thread = None


def pytest_addoption(parser):
    parser.addoption("--offline-workflow-coverage", default=None)


def pytest_configure(config):
    global target, active
    target, active = None, None
    events.clear()
    passed.clear()
    if config.getoption("--offline-workflow-coverage"):
        from app.modules.country_workflows.calculations import calculate

        target = calculate.__code__


def observe(frame, event, result):
    if event == "return" and frame.f_code is target and active:
        data = frame.f_locals.get("data")
        country = frame.f_locals.get("country")
        workflow = getattr(data, "workflow", None)
        if isinstance(workflow, str) and isinstance(country, str):
            events[active].add((workflow, country, isinstance(result, dict)))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    global active, previous, previous_thread
    if target is not None:
        active = item.nodeid
        previous, previous_thread = sys.getprofile(), threading.getprofile()
        sys.setprofile(observe)
        threading.setprofile(observe)
    try:
        yield
    finally:
        if target is not None:
            sys.setprofile(previous)
            threading.setprofile(previous_thread)
            active = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if target is not None and report.when == "call" and report.passed:
        for workflow, country, calculated in events.pop(item.nodeid, set()):
            passed[(workflow, country)]["calculated" if calculated else "rejected"].add(item.nodeid)


def pytest_sessionfinish(session, exitstatus):
    output = session.config.getoption("--offline-workflow-coverage")
    if not output:
        return
    from app.modules.country_workflows.catalogue import WORKFLOWS, catalogue

    rows = [
        {
            "workflow": workflow,
            "country": country,
            "calculated_in_passing_tests": sorted(kinds["calculated"]),
            "rejected_in_passing_tests": sorted(kinds["rejected"]),
        }
        for (workflow, country), kinds in sorted(passed.items())
    ]
    uae = {x["id"] for x in catalogue("AE") if x["available"]}
    calculated = {r["workflow"] for r in rows if r["calculated_in_passing_tests"]}
    calculated_uae = {
        r["workflow"] for r in rows if r["country"] == "AE" and r["calculated_in_passing_tests"]
    }
    report = {
        "dataset_kind": "SYNTHETIC_REGRESSION_EXECUTION_COVERAGE",
        "suite_exit_code": int(exitstatus),
        "uae_available_count": len(uae),
        "uae_calculated_in_passing_tests": sorted(uae & calculated_uae),
        "missing_uae_calculations": sorted(uae - calculated_uae),
        "missing_any_country_workflows": sorted(set(WORKFLOWS) - calculated),
        "observations": rows,
        "limits": "Only actual calls returning from the common country-workflow calculate function inside passing tests. Rejections are separate. Does not prove all branches, external services, physical procedures or legal qualification. Standalone retained-workpaper APIs are verified separately.",
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
