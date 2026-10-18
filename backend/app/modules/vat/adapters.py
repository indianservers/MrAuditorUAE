"""No invented ASP endpoints; this adapter never sends a network request."""

from typing import Protocol


class ASPAdapter(Protocol):
    async def send(self, payload: dict, simulate: str) -> dict: ...


class SandboxASP:
    async def send(self, payload, simulate):
        errors = []
        for key in [
            "invoice_number",
            "supplier_endpoint_id",
            "buyer_endpoint_id",
            "currency",
            "net",
            "tax",
            "gross",
        ]:
            if not payload.get(key) and payload.get(key) != "0.00":
                errors.append("Missing " + key)
        if simulate == "timeout":
            return {
                "state": "SANDBOX_TIMEOUT",
                "retryable": True,
                "errors": ["Simulated timeout"],
                "external_submission": False,
            }
        if errors or simulate == "reject":
            return {
                "state": "SANDBOX_REJECTED",
                "retryable": True,
                "errors": errors or ["Simulated provider business-rule rejection"],
                "external_submission": False,
            }
        return {
            "state": "SANDBOX_ACCEPTED",
            "retryable": False,
            "errors": [],
            "external_submission": False,
            "scope": "Local semantic subset, not full PINT-AE or ASP acceptance",
        }
