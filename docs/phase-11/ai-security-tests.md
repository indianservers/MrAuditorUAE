# Security verification

Tests cover strict unknown input rejection; unsupported SQL/shell/exfiltration/training intents; unknown/cyclic/disconnected tool graphs; client-role denial; unrelated engagement denial; self-approval denial; changed hash/stale approval denial; execution before approval; duplicate execution; immutable event history; quarantined uploads; source reopen; extraction correction and stale citation rejection. Indirect injection text in a synthetic CSV remains literal source content and cannot select executable tools.

Hard authorization and typed-plan boundaries provide the deterministic protection. They do not prove a live LLM will never produce misleading narrative. The mock gateway's strict output and supplied-citation enforcement are tested; live model red-teaming remains outstanding. AI tools cannot perform unrestricted network requests, arbitrary SQL, code execution, external communication or training.

The application does not claim comprehensive malicious PDF parser isolation or malware-scanner validation. Clean real-world files require a working scanner. Resource limits reduce extraction exposure but do not replace sandboxed document-processing operations in production. A malicious file/parser corpus and multiple-user production load tests remain required.
