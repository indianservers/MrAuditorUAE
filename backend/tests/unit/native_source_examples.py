"""Synthetic native documents; no bank, employee or customer authenticity is implied."""

CAMT = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt>
<GrpHdr><MsgId>SYNTHETIC-MSG</MsgId></GrpHdr><Stmt><Id>SYNTHETIC-STMT</Id>
<Acct><Id><Othr><Id>BANK-1</Id></Othr></Id><Ccy>AED</Ccy></Acct>
<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="AED">0.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-06-01</Dt></Dt></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="AED">95.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-06-30</Dt></Dt></Bal>
<TxsSummry><TtlNtries><NbOfNtries>2</NbOfNtries></TtlNtries></TxsSummry>
<Ntry><NtryRef>R1</NtryRef><Amt Ccy="AED">100.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>2026-06-01</Dt></BookgDt>
<NtryDtls><TxDtls><Refs><EndToEndId>PAY-1</EndToEndId></Refs><Amt Ccy="AED">100.00</Amt><RltdPties><Dbtr><Pty><Nm>Customer</Nm></Pty></Dbtr></RltdPties></TxDtls></NtryDtls></Ntry>
<Ntry><NtryRef>FEE</NtryRef><Amt Ccy="AED">5.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><RvslInd>false</RvslInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>2026-06-02</Dt></BookgDt></Ntry>
</Stmt></BkToCstmrStmt></Document>"""

MT940 = b""":20:SYNTHETIC-STMT
:25:BANK-1
:28C:1/1
:60F:C260601AED0,00
:61:2606010601C100,00NTRFPAY-1//SYNTHETIC-REF1
:86:SYNTHETIC receipt
:61:2606020602D5,00NCHGFEE//SYNTHETIC-REF2
:62F:C260630AED95,00
"""


def iban(bban="0331234567890123456"):
    digits = 98 - int(bban + "101400") % 97
    return "AE" + f"{digits:02}" + bban


SIF_FILENAME = "1234567890123260630123456.sif"
SIF = (
    f"EDR,12345678901234,033000000,{iban()},2026-06-01,2026-06-30,30,1000.00,100.00,0\n"
    f"EDR,12345678901235,033000000,{iban('0331234567890123457')},2026-06-01,2026-06-30,30,400.00,0.00,2\n"
    "SCR,1234567890123,033000000,2026-06-30,1234,062026,2,1500.00,AED,SYNTHETIC\n"
).encode()
