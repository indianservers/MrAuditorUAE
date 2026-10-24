"""Manual Windows Tally connector. Run using the backend uv environment.
Refresh credentials live in the OS credential vault; only non-secret resume IDs live on disk.
"""

import argparse
import base64
import getpass
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
import keyring

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.modules.connectors.tally import date_windows, export_request, parse_export

SERVICE = "AuditOS-Tally-Agent"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--set-refresh-token", action="store_true")
    parser.add_argument("--kind", choices=["gl", "coa", "tb", "all"], default="all")
    parser.add_argument("--window-days", type=int, default=31)
    parser.add_argument("--resume", type=Path, help="Previously preserved .tally.json package")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    server = config["server_url"].rstrip("/")
    if urlparse(server).scheme != "https":
        raise SystemExit("AuditOS server must use HTTPS")
    tally = config.get("tally_url", "http://127.0.0.1:9000")
    if urlparse(tally).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Tally must remain on the local computer")
    identity = server + ":" + config["tenant_id"]
    if args.set_refresh_token:
        keyring.set_password(SERVICE, identity, getpass.getpass("AuditOS refresh token: "))
        print("Refresh credential saved in OS vault")
        return
    lock = args.config.with_suffix(".lock")
    lock_handle = lock.open("x")
    with lock_handle:
        try:
            with httpx.Client(timeout=60, follow_redirects=False, verify=True) as client:
                refresh = keyring.get_password(SERVICE, identity)
                if not refresh:
                    raise SystemExit("Set a refresh token first")
                response = client.post(
                    server + "/api/v1/auth/refresh", json={"refresh_token": refresh}
                )
                response.raise_for_status()
                tokens = response.json()
                keyring.set_password(SERVICE, identity, tokens["refresh_token"])
                headers = {
                    "Authorization": "Bearer " + tokens["access_token"],
                    "X-Tenant-ID": config["tenant_id"],
                }
                package_path = args.resume or args.config.with_suffix(".tally.ndjson")
                if not args.resume:
                    from xml.etree.ElementTree import Element, tostring

                    from defusedxml.ElementTree import fromstring

                    first, last = (
                        date.fromisoformat(config["start_date"]),
                        date.fromisoformat(config["end_date"]),
                    )
                    root = Element("ENVELOPE")
                    for kind in ["companies", "groups", "ledgers"]:
                        response = client.post(
                            tally,
                            content=export_request(config["company"], kind, first, last),
                            headers={"Content-Type": "text/xml; charset=utf-8"},
                        )
                        response.raise_for_status()
                        root.append(fromstring(response.content))
                    raw_masters = tostring(root)
                    source = parse_export(
                        raw_masters,
                        config["company"],
                        first,
                        last,
                        expected_fingerprint=config.get("company_fingerprint"),
                    )
                    if not source["company_fingerprint"]:
                        raise SystemExit(
                            "Tally company GUID is unavailable; company identity cannot be bound"
                        )
                    print(
                        json.dumps(
                            {
                                "company_fingerprint": source["company_fingerprint"],
                                "status": "verify_and_pin_this_company_identity",
                            }
                        )
                    )
                    # Exclusive creation preserves earlier evidence. An interrupted file
                    # cannot be resumed until extraction completes all windows.
                    with package_path.open("x", encoding="utf-8") as file:
                        file.write(
                            json.dumps(
                                {
                                    "format": "tally-window-package/1",
                                    "company": config["company"],
                                    "start_date": str(first),
                                    "end_date": str(last),
                                    "company_fingerprint": source["company_fingerprint"],
                                    "masters_xml": base64.b64encode(raw_masters).decode(),
                                }
                            )
                            + "\n"
                        )
                        for window_start, window_end in date_windows(first, last, args.window_days):
                            response = client.post(
                                tally,
                                content=export_request(
                                    config["company"], "vouchers", window_start, window_end
                                ),
                                headers={"Content-Type": "text/xml; charset=utf-8"},
                            )
                            response.raise_for_status()
                            parse_export(
                                response.content,
                                config["company"],
                                window_start,
                                window_end,
                                master_catalog=source["masters"],
                            )
                            file.write(
                                json.dumps(
                                    {
                                        "start_date": str(window_start),
                                        "end_date": str(window_end),
                                        "xml": base64.b64encode(response.content).decode(),
                                    }
                                )
                                + "\n"
                            )
                            file.flush()
                kinds = ["coa", "gl", "tb"] if args.kind == "all" else [args.kind]
                for kind in kinds:
                    state_path = package_path.with_suffix(f".{kind}.resume.json")
                    with package_path.open("rb") as source:
                        sha = hashlib.file_digest(source, "sha256").hexdigest()
                    resume_scope = {
                        k: config[k]
                        for k in (
                            "tenant_id",
                            "client_id",
                            "entity_id",
                            "period_id",
                            "company",
                            "currency",
                        )
                    }
                    resume_scope["kind"] = kind
                    resume_scope["server_url"] = server
                    if state_path.exists():
                        state = json.loads(state_path.read_text())
                        if state["sha256"] != sha or state.get("scope") != resume_scope:
                            raise SystemExit("Resume package changed")
                        upload_id = state["id"]
                    else:
                        options = {
                            "client_id": config["client_id"],
                            "entity_id": config["entity_id"],
                            "period_id": config["period_id"],
                            "kind": kind,
                            "source_system": "tally",
                            "currency": config["currency"],
                            "tally_company": config["company"],
                            "tally_company_fingerprint": config.get("company_fingerprint"),
                        }
                        response = client.post(
                            server + "/api/v1/accounting/uploads",
                            headers=headers,
                            json={
                                "options": options,
                                "filename": package_path.name,
                                "sha256": sha,
                                "total_size": package_path.stat().st_size,
                            },
                        )
                        response.raise_for_status()
                        upload_id = response.json()["id"]
                        state_path.write_text(
                            json.dumps({"id": upload_id, "sha256": sha, "scope": resume_scope})
                        )
                    response = client.get(
                        server + "/api/v1/accounting/uploads/" + upload_id, headers=headers
                    )
                    response.raise_for_status()
                    state = response.json()
                    with package_path.open("rb") as file:
                        index = 0
                        while content := file.read(state["chunk_size"]):
                            if index not in state["received"]:
                                response = client.put(
                                    server
                                    + f"/api/v1/accounting/uploads/{upload_id}/chunks/{index}",
                                    headers=headers,
                                    content=content,
                                )
                                response.raise_for_status()
                            index += 1
                    response = client.post(
                        server + f"/api/v1/accounting/uploads/{upload_id}/complete", headers=headers
                    )
                    response.raise_for_status()
                    batch = response.json()["batch_id"]
                    response = client.post(
                        server + f"/api/v1/accounting/imports/{batch}/validate?background=true",
                        headers=headers,
                    )
                    response.raise_for_status()
                    print(
                        json.dumps(
                            {
                                "kind": kind,
                                "batch_id": batch,
                                "validation_job": response.json(),
                                "status": "uploaded; validation pending; activation requires authorized review",
                            }
                        )
                    )
        finally:
            lock_handle.close()
            lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
