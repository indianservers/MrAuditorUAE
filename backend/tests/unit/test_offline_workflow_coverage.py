"""The execution observer cannot turn an unexecuted/rejected workflow into coverage."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def observer():
    path = Path(__file__).resolve().parents[3] / "scripts/offline_workflow_coverage.py"
    spec = importlib.util.spec_from_file_location("synthetic_coverage_observer_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.target, module.active = object(), "synthetic-test"
    return module


def test_observer_counts_only_the_target_return_and_separates_rejection():
    module = observer()
    frame = SimpleNamespace(
        f_code=module.target,
        f_locals={"data": SimpleNamespace(workflow="bank-brs"), "country": "AE"},
    )
    module.observe(frame, "call", {})
    assert not module.events
    module.observe(frame, "return", None)
    assert module.events["synthetic-test"] == {("bank-brs", "AE", False)}
    module.observe(frame, "return", {"rows": []})
    assert ("bank-brs", "AE", True) in module.events["synthetic-test"]
    module.observe(SimpleNamespace(f_code=object()), "return", {})
    assert len(module.events["synthetic-test"]) == 2


def test_calls_inside_a_failing_test_do_not_count_as_passed_coverage():
    module = observer()
    module.events["failing"] = {("bank-brs", "AE", True)}
    hook = module.pytest_runtest_makereport(SimpleNamespace(nodeid="failing"), None)
    next(hook)
    try:
        hook.send(SimpleNamespace(get_result=lambda: SimpleNamespace(when="call", passed=False)))
    except StopIteration:
        pass
    assert not module.passed


def test_missing_workflows_stay_explicit_and_rejections_do_not_clear_them(tmp_path):
    module = observer()
    module.passed[("bank-brs", "AE")]["calculated"].add("test_matched_bank")
    module.passed[("uae-vat", "AE")]["rejected"].add("test_invalid_vat")
    output = tmp_path / "coverage.json"
    module.pytest_sessionfinish(
        SimpleNamespace(config=SimpleNamespace(getoption=lambda _: str(output))), 1
    )
    report = json.loads(output.read_bytes())
    assert report["suite_exit_code"] == 1
    assert report["uae_calculated_in_passing_tests"] == ["bank-brs"]
    assert "uae-vat" in report["missing_uae_calculations"]
    assert len(report["missing_uae_calculations"]) == report["uae_available_count"] - 1
