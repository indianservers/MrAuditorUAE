"""Scanner protocol tests; fake socket verdicts do not qualify a malware engine."""

import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.audit_execution import evidence


def connection(monkeypatch, replies):
    client = MagicMock()
    client.__enter__.return_value = client
    client.recv.side_effect = replies
    monkeypatch.setattr(
        evidence,
        "settings",
        lambda: SimpleNamespace(
            evidence_clamav_host="scanner.invalid",
            evidence_clamav_port=3310,
        ),
    )
    connect = MagicMock(return_value=client)
    monkeypatch.setattr(evidence.socket, "create_connection", connect)
    return client, connect


@pytest.mark.parametrize(
    "pieces",
    [
        [b"stream: OK\0"],
        [b"str", b"eam: ", b"OK", b"\0"],
        [bytes([x]) for x in b"stream: OK\0"],
    ],
)
def test_clean_requires_complete_framed_verdict(monkeypatch, pieces):
    client, connect = connection(monkeypatch, pieces)
    stream = io.BytesIO(b"synthetic content")
    assert evidence.scan(stream) == "CLEAN"
    assert stream.tell() == 0
    assert b"".join(call.args[0] for call in client.sendall.call_args_list) == (
        b"zINSTREAM\0" + len(stream.getvalue()).to_bytes(4, "big") + stream.getvalue() + b"\0\0\0\0"
    )
    connect.assert_called_once()


@pytest.mark.parametrize(
    "pieces",
    [
        [b"stream: OK", b""],
        [b"stream: O", b""],
        [b""],
        [b"stream: OK\n", b""],
        [b"stream: OK\0extra"],
        [b"stream: OK\0stream: malware FOUND\0"],
        [b"x" * 4096],
        [TimeoutError("unavailable")],
    ],
)
def test_incomplete_malformed_or_unavailable_verdict_is_quarantined(monkeypatch, pieces):
    connection(monkeypatch, pieces)
    stream = io.BytesIO(b"synthetic content")
    assert evidence.scan(stream) == "QUARANTINED"
    assert stream.tell() == 0


@pytest.mark.parametrize(
    "reply",
    [
        b"stream: Synthetic-Signature FOUND\0",
        b"INSTREAM size limit exceeded. ERROR\0",
        b"different: OK\0",
        b"stream: Synthetic ERROR: OK\0",
    ],
)
def test_other_complete_verdict_never_cleans(monkeypatch, reply):
    connection(monkeypatch, [reply])
    assert evidence.scan(io.BytesIO(b"synthetic")) == "REJECTED"


def test_slow_fragmented_reply_shares_one_deadline(monkeypatch):
    client, _ = connection(monkeypatch, [b"s", b"t", b"ream: OK\0"])
    times = iter([0, 1, 2, 3, 4, 19.5, 21])
    monkeypatch.setattr(evidence.time, "monotonic", lambda: next(times))
    stream = io.BytesIO(b"synthetic")
    assert evidence.scan(stream) == "QUARANTINED"
    assert client.recv.call_count == 2
    assert client.settimeout.call_args.args[0] == 0.5
    assert stream.tell() == 0


@pytest.mark.parametrize("failure", ["connect", "send", "unconfigured"])
def test_network_failures_and_missing_configuration_rewind(monkeypatch, failure):
    client, connect = connection(monkeypatch, [b"stream: OK\0"])
    if failure == "connect":
        connect.side_effect = OSError("synthetic unavailable scanner")
    elif failure == "send":
        client.sendall.side_effect = OSError("synthetic disconnected scanner")
    else:
        monkeypatch.setattr(evidence, "settings", lambda: SimpleNamespace(evidence_clamav_host=""))
    stream = io.BytesIO(b"synthetic")
    stream.seek(3)
    assert evidence.scan(stream) == "QUARANTINED"
    assert stream.tell() == 0


def test_multiple_payload_chunks_preserve_wire_bytes(monkeypatch):
    client, _ = connection(monkeypatch, [b"stream: OK\0"])
    stream = io.BytesIO(b"a" * 65536 + b"tail")
    assert evidence.scan(stream) == "CLEAN"
    sent = [call.args[0] for call in client.sendall.call_args_list]
    assert sent == [
        b"zINSTREAM\0",
        (65536).to_bytes(4, "big") + b"a" * 65536,
        (4).to_bytes(4, "big") + b"tail",
        b"\0\0\0\0",
    ]
