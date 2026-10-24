import io
import json
import uuid
from decimal import Decimal

import pytest

from app.modules.audit_execution.evidence import validate_file
from app.modules.country_workflows.calculations import calculate
from app.modules.country_workflows.native_sources import formats, parse_native
from app.modules.country_workflows.schemas import SourceInput, WorkflowInput
from tests.unit.native_source_examples import CAMT, MT940, SIF, SIF_FILENAME, iban


def options(file_format="camt053", **changes):
    return SourceInput(
        evidence_version_id=uuid.uuid4(),
        file_format=file_format,
        table_type="obligations" if file_format == "uae-wps-sif" else "transactions",
        label="SYNTHETIC native source",
        expected_rows=2,
        control_totals={"AED": "1500" if file_format == "uae-wps-sif" else "95"},
        **changes,
    )


@pytest.mark.parametrize(
    "file_format,content,filename",
    [("camt053", CAMT, "bank.xml"), ("swift-mt940", MT940, "bank.mt940")],
)
def test_native_booked_amounts_controls_and_original_evidence(file_format, content, filename):
    data = options(file_format)
    result = parse_native(content, data, "AE", filename)
    assert [Decimal(r["amount"]) for r in result["rows"]] == [Decimal("100"), Decimal("-5")]
    assert result["native_metadata"]["opening"] == "0.00"
    assert result["native_metadata"]["closing"] == "95.00"
    assert result["native_metadata"]["bank_identity_verified"] is False
    assert result["row_count"] == 2 and result["review_status"] == "UNVERIFIED"
    assert result["native_controls_verified"] is True
    assert validate_file(io.BytesIO(content), filename) in {"application/xml", "text/plain"}
    # CAMT transaction details must not be added a second time to entry amounts.
    assert Decimal(result["control_totals"]["AED"]) == Decimal("95")


@pytest.mark.parametrize(
    "old,new,error",
    [
        (b"95.00", b"96.00", "closing balance"),
        (b"<Cd>BOOK</Cd>", b"<Cd>PDNG</Cd>", "Only booked"),
        (b"<NbOfNtries>2", b"<NbOfNtries>3", "entry-count"),
        (b"<Cd>OPBD</Cd>", b"<Cd>OPAV</Cd>", "OPBD"),
        (b"<Cd>CLBD</Cd>", b"<Cd>CLAV</Cd>", "CLBD"),
        (b'<Amt Ccy="AED">5.00', b'<Amt Ccy="USD">5.00', "currency"),
        (b"2026-06-02", b"2026-07-02", "outside"),
        (b"camt.053.001.08", b"camt.052.001.08", "namespace"),
        (b"camt.053.001.08", b"camt.053.001.99", "namespace"),
    ],
)
def test_camt_no_partial_or_silently_dropped_native_rows(old, new, error):
    with pytest.raises(ValueError, match=error):
        parse_native(CAMT.replace(old, new), options(), "AE", "bank.xml")


def test_camt_explicit_multi_statement_selection_and_conflicting_account():
    statement = CAMT.split(b"<Stmt>", 1)[1].split(b"</Stmt>", 1)[0]
    multi = CAMT.replace(
        b"</BkToCstmrStmt>",
        b"<Stmt>"
        + statement.replace(b"SYNTHETIC-STMT", b"SYNTHETIC-OTHER").replace(b"BANK-1", b"BANK-2")
        + b"</Stmt></BkToCstmrStmt>",
    )
    with pytest.raises(ValueError, match="unambiguous"):
        parse_native(multi, options(), "AE", "bank.xml")
    selected = parse_native(
        multi,
        options(statement_identifier="SYNTHETIC-OTHER", account_identifier="BANK-2"),
        "AE",
        "bank.xml",
    )
    assert selected["native_metadata"]["file_statement_count"] == 2
    assert selected["rows"][0]["account"] == "BANK-2"
    with pytest.raises(ValueError):
        parse_native(
            multi,
            options(statement_identifier="SYNTHETIC-OTHER", account_identifier="BANK-1"),
            "AE",
            "bank.xml",
        )


@pytest.mark.parametrize(
    "content",
    [
        b'<!DOCTYPE Document [<!ENTITY private SYSTEM "file:///not-to-be-read">]><Document>&private;</Document>',
        b"<Document><unclosed>",
        b"<Document>\x00</Document>",
    ],
)
def test_xml_rejects_unsafe_or_malformed_evidence_before_processing(content):
    with pytest.raises(ValueError):
        parse_native(content, options(), "AE", "bank.xml")
    with pytest.raises(ValueError):
        validate_file(io.BytesIO(content), "bank.xml")


def test_paged_camt_cannot_claim_a_complete_statement():
    content = CAMT.replace(
        b"</GrpHdr>", b"<MsgPgntn><PgNb>1</PgNb><LastPgInd>false</LastPgInd></MsgPgntn></GrpHdr>"
    )
    with pytest.raises(ValueError, match="complete-page"):
        parse_native(content, options(), "AE", "bank.xml")


def test_native_bank_controls_cannot_be_overridden_by_a_matching_offset():
    source = parse_native(CAMT, options(), "AE", "bank.xml")
    source_ids = {"books": uuid.uuid4(), "statement": uuid.uuid4()}
    data = WorkflowInput(
        workflow="bank-brs",
        source_ids=source_ids,
        as_of="2026-06-30",
        title="SYNTHETIC controlled BRS",
        rationale="Synthetic native balances cannot be overridden",
        account="BANK-1",
        currency="AED",
        book_opening="0",
        book_closing="95",
        statement_opening="0",
        statement_closing="95",
    )
    result = calculate(data, "AE", {"books": source, "statement": source})
    assert result["blocked"] is False and result["exception_count"] == 0
    tampered = data.model_copy(
        update={"statement_opening": Decimal("100"), "statement_closing": Decimal("195")}
    )
    with pytest.raises(ValueError, match="original native"):
        calculate(tampered, "AE", {"books": source, "statement": source})


@pytest.mark.parametrize(
    "old,new,error",
    [
        (b"AED95,00", b"AED94,00", "closing balance"),
        (b":60F:", b":60M:", "Partial"),
        (b":62F:", b":62M:", "Partial"),
        (b":28C:1/1", b":28C:1/2", "Multi-page"),
        (b"2606010601", b"2607010701", "outside"),
        (b":62F:C260630AED", b":62F:C260630USD", "currencies"),
    ],
)
def test_mt940_rejects_incomplete_or_inconsistent_statements(old, new, error):
    with pytest.raises(ValueError, match=error):
        parse_native(MT940.replace(old, new), options("swift-mt940"), "IN", "bank.sta")


def test_mt940_reversal_directions_and_fin_envelope():
    reversal = MT940.replace(b"0601C100", b"0601RD100").replace(b"0602D5", b"0602RC5")
    content = b"{1:F01SYNTHETIC}{2:I940SYNTHETIC}{4:\n" + reversal + b"-}"
    result = parse_native(content, options("swift-mt940"), "AE", "bank.sta")
    assert [r["is_reversal"] for r in result["rows"]] == [True, True]
    assert [Decimal(r["amount"]) for r in result["rows"]] == [Decimal("100"), Decimal("-5")]


def test_wps_embedded_employee_controls_and_no_invented_payment_execution():
    result = parse_native(
        SIF, options("uae-wps-sif", obligation_due_date="2026-07-01"), "AE", SIF_FILENAME
    )
    assert result["control_totals"] == {"AED": "1500.00"}
    assert all(r["payment_date"] is None and r["due_date"] == "2026-07-01" for r in result["rows"])
    assert [r["amount"] for r in result["rows"]] == ["1100.00", "400.00"]
    assert result["native_metadata"]["payment_execution"] == "NOT_EVIDENCED_BY_INSTRUCTION_FILE"
    assert result["native_metadata"]["employee_count"] == 2
    assert iban() not in json.dumps(result["rows"])
    assert len(result["rows"][0]["employee_account_sha256"]) == 64
    assert validate_file(io.BytesIO(SIF), SIF_FILENAME) == "text/csv"


@pytest.mark.parametrize("native_role", ["payroll", "bank", "channel"])
def test_wps_instruction_cannot_establish_payroll_expectation_or_bank_settlement(native_role):
    native = parse_native(
        SIF, options("uae-wps-sif", obligation_due_date="2026-07-01"), "AE", SIF_FILENAME
    )
    # Separate synthetic schedules isolate the role restriction from amount matching.
    schedules = {
        role: {
            "table_type": "obligations",
            "control_totals": {"AED": "1500"},
            "rows": [
                {**row, "id": role + ":" + row["id"], "payment_date": "2026-07-01"}
                for row in native["rows"]
            ],
        }
        for role in ("payroll", "channel", "bank")
    }
    schedules[native_role] = native
    request = WorkflowInput(
        workflow="payroll-settlement",
        source_ids={role: uuid.uuid4() for role in schedules},
        as_of="2026-07-31",
        currency="AED",
        title="Synthetic WPS source-role separation",
        rationale="An instruction is neither independent payroll nor executed bank settlement",
    )
    if native_role != "channel":
        with pytest.raises(ValueError, match="return/channel role"):
            calculate(request, "AE", schedules)
    else:
        result = calculate(request, "AE", schedules)
        assert result["exception_count"] == 0


@pytest.mark.parametrize(
    "old,new,error",
    [
        (b",2,1500.00,AED", b",3,1500.00,AED", "employee-count"),
        (b",2,1500.00,AED", b",2,1499.99,AED", "total salary"),
        (b"12345678901235", b"12345678901234", "duplicated employee"),
        (b"2026-06-30,30,400", b"2026-06-30,29,400", "wage dates"),
        (b"2026-06-30,30,400", b"2026-07-30,30,400", "wage dates"),
        (b",30,400.00,0.00,2", b",30,400.00,0.00,31", "unpaid leave"),
        (b",1000.00,100.00,", b",-1000.00,100.00,", "decimal amount"),
        (b",1500.00,AED", b",1500.00,USD", "payment currency"),
    ],
)
def test_wps_corrupt_controls_cannot_publish_a_source(old, new, error):
    with pytest.raises(ValueError, match=error):
        parse_native(SIF.replace(old, new), options("uae-wps-sif"), "AE", SIF_FILENAME)


def test_wps_strict_profile_country_iban_filename_and_trailer():
    with pytest.raises(ValueError, match="engagement country"):
        parse_native(SIF, options("uae-wps-sif"), "IN", SIF_FILENAME)
    with pytest.raises(ValueError, match="filename"):
        parse_native(SIF, options("uae-wps-sif"), "AE", "renamed.sif")
    with pytest.raises(ValueError, match="employer"):
        parse_native(SIF, options("uae-wps-sif", employer_registration="OTHER"), "AE", SIF_FILENAME)
    with pytest.raises(ValueError, match="checksum"):
        parse_native(
            SIF.replace(iban().encode(), b"AE00" + iban()[4:].encode()),
            options("uae-wps-sif"),
            "AE",
            SIF_FILENAME,
        )
    lines = SIF.splitlines()
    with pytest.raises(ValueError, match="SCR trailer"):
        parse_native(
            b"\n".join([lines[-1], *lines[:-1]]), options("uae-wps-sif"), "AE", SIF_FILENAME
        )


def test_native_populations_require_external_control_agreement():
    for field, value in [("expected_rows", 1), ("control_totals", {"AED": Decimal("96")})]:
        changed = options().model_copy(update={field: value})
        with pytest.raises(ValueError, match="control"):
            parse_native(CAMT, changed, "AE", "bank.xml")
    assert not next(f for f in formats("IN") if f["id"] == "uae-wps-sif")["available"]


def test_native_validation_messages_do_not_echo_bank_identifiers():
    private_identifier = b"PRIVATE-ACCOUNT-" + b"X" * 150
    with pytest.raises(ValueError) as exc:
        parse_native(CAMT.replace(b"BANK-1", private_identifier), options(), "AE", "bank.xml")
    assert "PRIVATE-ACCOUNT" not in str(exc.value)
