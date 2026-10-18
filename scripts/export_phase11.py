"""Download application-generated synthetic draft exports through authenticated HTTP."""

import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads(
        (ROOT / "docs/phase-7/demo-manifest.json").read_text(encoding="utf-8")
    )
    proof = json.loads(
        (ROOT / "docs/phase-11/verification.json").read_text(encoding="utf-8")
    )
    demo = json.loads(
        (ROOT / "docs/phase-11/demo-verification.json").read_text(encoding="utf-8")
    )
    if demo.get("synthetic") is not True or proof.get("synthetic") is not True:
        raise ValueError("Explicit synthetic export fixtures required")
    credentials = json.loads(
        (ROOT / ".local-runtime/phase7/demo-login.local.json").read_text(
            encoding="utf-8"
        )
    )
    data = urllib.parse.urlencode(
        {"username": manifest["users"][1]["email"], "password": credentials["password"]}
    ).encode()
    origin = "http://127.0.0.1:58006/api/v1"
    request = urllib.request.Request(
        origin + "/auth/login",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)["access_token"]
    folder = ROOT / "docs/phase-11/exports"
    folder.mkdir(exist_ok=True)
    for kind in ["pdf", "docx"]:
        request = urllib.request.Request(
            origin
            + f"/ai/engagements/{demo['engagement_id']}/investigations/{proof['export_run_id']}/export/{kind}",
            headers={
                "Authorization": "Bearer " + token,
                "X-Tenant-ID": "8733db06-81bc-59b3-afcc-bf0f4c0cd8a2",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        (folder / f"synthetic-investigation-draft.{kind}").write_bytes(data)
        print(kind, len(data), "bytes from authorized application export")


if __name__ == "__main__":
    main()
