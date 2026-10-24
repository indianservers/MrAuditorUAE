"""Shared resumable upload for local SDK evidence; credentials stay in the OS vault."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import keyring


def upload_package(config, path: Path, kinds, source_system, service):
    server = config["server_url"].rstrip("/")
    parsed = urlsplit(server)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("The application server must be an approved HTTPS origin")
    identity = server + ":" + config["tenant_id"]
    refresh = keyring.get_password(service, identity)
    if not refresh:
        raise ValueError("Enroll this Windows user in the OS credential vault first")
    with path.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    with httpx.Client(timeout=60, follow_redirects=False, verify=True) as client:
        reply = client.post(server + "/api/v1/auth/refresh", json={"refresh_token": refresh})
        reply.raise_for_status()
        tokens = reply.json()
        keyring.set_password(service, identity, tokens["refresh_token"])
        headers = {
            "Authorization": "Bearer " + tokens["access_token"],
            "X-Tenant-ID": config["tenant_id"],
        }
        results = []
        for kind in kinds:
            options = {
                key: config[key] for key in ("client_id", "entity_id", "period_id", "currency")
            }
            options.update(kind=kind, source_system=source_system)
            state_path = path.with_suffix("." + kind + ".resume.json")
            scope = {**options, "tenant_id": config["tenant_id"], "server_url": server}
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state["scope"] != scope or state["sha256"] != fingerprint:
                    raise ValueError("Upload resume scope or source content changed")
                identifier = state["id"]
            else:
                reply = client.post(
                    server + "/api/v1/accounting/uploads",
                    headers=headers,
                    json={
                        "options": options,
                        "filename": path.name,
                        "sha256": fingerprint,
                        "total_size": path.stat().st_size,
                    },
                )
                reply.raise_for_status()
                identifier = reply.json()["id"]
                with state_path.open("x", encoding="utf-8") as state_file:
                    json.dump({"id": identifier, "scope": scope, "sha256": fingerprint}, state_file)
            reply = client.get(server + "/api/v1/accounting/uploads/" + identifier, headers=headers)
            reply.raise_for_status()
            state = reply.json()
            received = set(state["received"])
            with path.open("rb") as stream:
                index = 0
                while block := stream.read(state["chunk_size"]):
                    if index not in received:
                        reply = client.put(
                            f"{server}/api/v1/accounting/uploads/{identifier}/chunks/{index}",
                            headers={
                                **headers,
                                "Content-Type": "application/octet-stream",
                                "X-Chunk-SHA256": hashlib.sha256(block).hexdigest(),
                            },
                            content=block,
                        )
                        reply.raise_for_status()
                    index += 1
            reply = client.post(
                f"{server}/api/v1/accounting/uploads/{identifier}/complete", headers=headers
            )
            reply.raise_for_status()
            batch = reply.json()["batch_id"]
            reply = client.post(
                f"{server}/api/v1/accounting/imports/{batch}/validate", headers=headers
            )
            reply.raise_for_status()
            results.append({"kind": kind, "batch_id": batch, "validation": reply.json()})
        return results
