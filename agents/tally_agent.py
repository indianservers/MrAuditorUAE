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

from app.modules.connectors.tally import export_request, parse_export

SERVICE = "AuditOS-Tally-Agent"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--set-refresh-token", action="store_true")
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
                package_path = args.resume or args.config.with_suffix(".tally.json")
                if not args.resume:
                    exports = {}
                    for kind in ["companies", "groups", "ledgers", "vouchers"]:
                        response = client.post(
                            tally,
                            content=export_request(
                                config["company"],
                                kind,
                                date.fromisoformat(config["start_date"]),
                                date.fromisoformat(config["end_date"]),
                            ),
                            headers={"Content-Type": "text/xml; charset=utf-8"},
                        )
                        response.raise_for_status()
                        parse_export(
                            response.content,
                            config["company"],
                            date.fromisoformat(config["start_date"]),
                            date.fromisoformat(config["end_date"]),
                        )
                        exports[kind] = base64.b64encode(response.content).decode()
                    with package_path.open("x", encoding="utf-8") as file:
                        json.dump(
                            {"company": config["company"], "exports": exports, "synthetic": False},
                            file,
                        )
                state_path = package_path.with_suffix(".resume.json")
                sha = hashlib.file_digest(package_path.open("rb"), "sha256").hexdigest()
                if state_path.exists():
                    state = json.loads(state_path.read_text())
                    if state["sha256"] != sha:
                        raise SystemExit("Resume package changed")
                    upload_id = state["id"]
                else:
                    options = {
                        "client_id": config["client_id"],
                        "entity_id": config["entity_id"],
                        "period_id": config["period_id"],
                        "kind": "gl",
                        "source_system": "tally",
                        "currency": config["currency"],
                        "tally_company": config["company"],
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
                    state_path.write_text(json.dumps({"id": upload_id, "sha256": sha}))
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
                                server + f"/api/v1/accounting/uploads/{upload_id}/chunks/{index}",
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
