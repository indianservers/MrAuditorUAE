import importlib.util
from pathlib import Path


def test_release_gate_fails_closed_on_missing_and_blocking_evidence():
    path = Path(__file__).resolve().parents[3] / "scripts/release_gate.py"
    spec = importlib.util.spec_from_file_location("release_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.evaluate({})) == module.REQUIRED
    gates = {
        name: {"status": "VERIFIED", "evidence": "executed-proof.json"} for name in module.REQUIRED
    }
    assert module.evaluate({"gates": gates}) == []
    gates["deployment_rollback"]["status"] = "NOT_TESTED"
    assert module.evaluate({"gates": gates}) == ["deployment_rollback"]
    gates["deployment_rollback"]["status"] = "VERIFIED"
    gates["critical_security"]["open_blocker"] = True
    assert module.evaluate({"gates": gates}) == ["critical_security"]
