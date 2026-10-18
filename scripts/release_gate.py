"""Fail closed on missing, unverified, or blocking release evidence."""

import hashlib
import json
import sys
from pathlib import Path

REQUIRED = {
    "tenant_isolation",
    "financial_accuracy",
    "professional_approvals",
    "critical_security",
    "migration",
    "recovery",
    "deployment_rollback",
    "ai_authorization",
    "audit_history",
    "demo_isolation",
}


def evaluate(data):
    gates = data.get("gates", {})
    missing = REQUIRED - gates.keys()
    blocked = {
        name
        for name, gate in gates.items()
        if gate.get("status") != "VERIFIED"
        or not gate.get("evidence")
        or gate.get("open_blocker", False)
    }
    return sorted(missing | blocked)


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    blocked = evaluate(data)
    root = Path(__file__).resolve().parents[1]
    for name, gate in data.get("gates", {}).items():
        candidate = (root / gate.get("evidence", "")).resolve()
        if (
            not candidate.is_relative_to(root)
            or not candidate.is_file()
            or (
                gate.get("evidence_sha256")
                and hashlib.sha256(candidate.read_bytes()).hexdigest() != gate["evidence_sha256"]
            )
        ):
            blocked.append(name)
    blocked = sorted(set(blocked))
    print(json.dumps({"decision": "NO-GO" if blocked else "GO", "blocked_gates": blocked}))
    raise SystemExit(1 if blocked else 0)
