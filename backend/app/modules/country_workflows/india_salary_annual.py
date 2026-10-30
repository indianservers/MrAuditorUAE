"""Controlled historical annual salary observations, not salary-tax or FVU qualification."""

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.modules.country_workflows.india_withholding_native import Money
from app.modules.jurisdictions.profiles import Strict

PROFILE = "india-24q-regular-q4-v7.5"
SPEC_SHA256 = "085268dd1be1685ba23e6aa147bed7cedf114a635463c4ca6e917062eed9706f"
TAGS = ("SD", "S16", "C6A", "94P", "P16", "P6A")
Count = Annotated[int, Field(ge=0, le=5000, strict=True)]
SignedMoney = Annotated[Decimal, Field(max_digits=28, decimal_places=2, allow_inf_nan=False)]


class SalaryAnnualControls(Strict):
    record_counts: dict[Literal["SD", "S16", "C6A", "94P", "P16", "P6A"], Count]
    salary_gross_income: Money
    salary_taxable_income: Money
    salary_net_tax_payable: Money
    salary_tax_deducted: Money
    salary_shortfall: SignedMoney
    pension_gross_income: Money
    pension_taxable_income: Money
    pension_net_tax_payable: Money
    assessment: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def explicit_population(self):
        if set(self.record_counts) != set(TAGS):
            raise ValueError("Declare all six annual record counts, including explicit zeros")
        if not self.record_counts["SD"] + self.record_counts["94P"]:
            raise ValueError("The nonempty annual profile requires a declared parent population")
        if len(self.assessment.strip()) < 10:
            raise ValueError("Assess the complete annual population and independent controls")
        return self


def annual_layout():
    raw = Path(__file__).with_name("india_salary_q4_layout.json").read_bytes()
    result = json.loads(raw)
    if result["profile"] != PROFILE or result["source_sha256"] != SPEC_SHA256:
        raise ValueError("Annual salary layout differs from its pinned original workbook")
    return result, hashlib.sha256(raw).hexdigest()


def assess_annual(records, batches, native, controls, layout, integer, calendar):
    if controls is None:
        raise ValueError("Q4 requires separate independent annual population and amount controls")
    year = int(native.financial_year[:4])
    if native.quarter != "Q4" or year < 2011:
        raise ValueError("The adopted annual Q4 profile covers FY2011-12 through FY2025-26")

    def amount(value, signed=False):
        if not re.fullmatch((r"-?" if signed else "") + r"[0-9]{1,12}\.[0-9]{2}", value):
            raise ValueError("Annual amounts require explicit two-decimal source values")
        return Decimal(value)

    def count(value):
        if not re.fullmatch(r"[0-9]{1,9}(?:\.00)?", value):
            raise ValueError("Annual child counts require explicit nonnegative whole counts")
        return int(Decimal(value))

    def pan(value):
        return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", value)) or value in {
            "PANNOTAVBL",
            "PANAPPLIED",
            "PANINVALID",
        }

    def required(f, n):
        return amount(f[n - 1], f[1] == "SD" and n in {18, 30})

    def equal(observed, expected, label):
        if observed != expected:
            raise ValueError("Annual " + label + " differs from its complete recorded components")

    def contacts(f, flag_number, count_number, first_number):
        flag = f[flag_number - 1]
        pairs = [(f[n - 1], f[n]) for n in range(first_number, first_number + 8, 2)]
        if flag not in {"", "Y", "N"}:
            raise ValueError("Annual landlord/lender flag requires an explicit supported value")
        if flag == "Y":
            declared = count(f[count_number - 1])
            if not 1 <= declared <= 4 or declared != sum(bool(p) for p, _ in pairs):
                raise ValueError("Annual landlord/lender population differs from its count")
            for identifier, name in pairs:
                if (
                    bool(identifier) != bool(name)
                    or identifier
                    and not (
                        re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", identifier)
                        or identifier in {"GOVERNMENT", "NONRESDENT", "OTHERVALUE"}
                    )
                ):
                    raise ValueError("Annual landlord/lender identity or name is incomplete")
        elif any(p or name for p, name in pairs) or (
            count(f[count_number - 1]) != 0 if flag == "N" else bool(f[count_number - 1])
        ):
            raise ValueError("Annual landlord/lender details contradict their recorded flag")

    populations: dict[str, list[dict]] = {tag: [] for tag in TAGS}
    parents = {}
    child_records: dict[tuple[str, int, int], dict[str, list[list[str]]]] = {}
    batch = None
    current = None
    annual_started = set()
    for f in records[1:]:
        tag = f[1]
        if tag == "BH":
            batch, current = integer(f[2]), None
            continue
        if tag in {"CD", "DD"}:
            if batch in annual_started:
                raise ValueError(
                    "Quarterly challan/party records cannot follow annual records in a batch"
                )
            current = None
            continue
        if tag not in TAGS:
            continue  # The shared reader rejects other record types before this assessment.
        if batch is None or integer(f[2]) != batch:
            raise ValueError("Annual record must belong to its preceding declared batch")
        annual_started.add(batch)
        for column, value in zip(layout["columns"][tag], f, strict=True):
            n, kind = column["number"], column["type"]
            if kind == "NA" and value:
                raise ValueError("Annual reserved fields must remain blank")
            if not value:
                continue
            if kind == "DATE":
                calendar(value)
            elif kind == "INTEGER":
                integer(value)
            elif kind == "DECIMAL":
                if (tag, n) in {("SD", 21), ("SD", 40), ("SD", 50), ("94P", 18)}:
                    count(value)
                elif (tag, n) == ("SD", 64):
                    if not re.fullmatch(r"[0-9]{1,3}\.[0-9]{4}", value):
                        raise ValueError("Recorded superannuation rate requires four decimals")
                else:
                    amount(value, tag == "SD" and n in {18, 30})
        serial = integer(f[3])
        if tag in {"SD", "94P"}:
            key = (tag, batch, serial)
            expected_serial = 1 + sum(row["batch"] == batch for row in populations[tag])
            if key in parents or serial != expected_serial or f[4] != "A":
                raise ValueError("Annual parent serial or regular-addition mode is inconsistent")
            if tag == "94P" and year < 2021:
                raise ValueError("The retained 194P record layout applies from FY2021-22")
            p = f[6] if tag == "SD" else f[5]
            name = f[8] if tag == "SD" else f[6]
            if not pan(p) or not name.strip():
                raise ValueError("Annual parent requires its original PAN/sentinel and name")
            if (
                tag == "SD"
                and f[9] not in {"W", "S", "O", "G"}
                or tag == "94P"
                and f[7] not in {"S", "O"}
            ):
                raise ValueError("Annual employee or specified-senior category is missing")
            if tag == "SD" and calendar(f[10]) > calendar(f[11]):
                raise ValueError("Annual employment start exceeds its recorded end date")
            parents[key] = f
            current = key
            child_records[key] = {"section": [], "chapter": []}
            parent, record_number = serial, serial
        else:
            expected_parent = "SD" if tag in {"S16", "C6A"} else "94P"
            key = (expected_parent, batch, serial)
            if current != key or key not in parents:
                raise ValueError("Annual child record differs from its preceding parent identity")
            family = "section" if tag in {"S16", "P16"} else "chapter"
            siblings = child_records[key][family]
            if (
                integer(f[4]) != len(siblings) + 1
                or not f[5].strip()
                or any(v[5] == f[5] for v in siblings)
            ):
                raise ValueError("Annual child sequence or distinct section identity differs")
            if family == "section" and f[5] not in (
                {"16(ii)", "16(iii)", "16(ia)"} if tag == "S16" else {"16(iii)", "16(ia)"}
            ):
                raise ValueError("Unsupported recorded section-16 child identifier")
            siblings.append(f)
            if family == "chapter":
                deductible = amount(f[6] if tag == "C6A" else f[8])
                gross = f[7] if tag == "C6A" else f[6]
                qualifying = f[8] if tag == "C6A" else f[7]
                if (
                    gross
                    and deductible > amount(gross)
                    or qualifying
                    and gross
                    and amount(qualifying) > amount(gross)
                ):
                    raise ValueError(
                        "Annual chapter deductible/qualifying amounts exceed recorded gross"
                    )
                if (
                    qualifying
                    and f[5]
                    in {
                        "80G",
                        "80TTA",
                        "80TTB",
                        "80DD",
                        "80EE",
                        "80EEA",
                        "80GG",
                        "80GGC",
                        "80U",
                        "OTHERS",
                    }
                    and deductible > amount(qualifying)
                ):
                    raise ValueError(
                        "Annual chapter deduction exceeds its recorded qualifying amount"
                    )
            parent, record_number = serial, integer(f[4])
            p = parents[key][6] if expected_parent == "SD" else parents[key][5]
        populations[tag].append(
            {
                "record_type": tag,
                "source_line": integer(f[0]),
                "batch": batch,
                "parent_record": parent,
                "record_number": record_number,
                "pan": p,
                "fields": list(f),
            }
        )

    if {tag: len(rows) for tag, rows in populations.items()} != controls.record_counts:
        raise ValueError("Annual record populations differ from independent six-type controls")
    for (tag, _, _), f in parents.items():
        children = child_records[(tag, integer(f[2]), integer(f[3]))]
        section, chapter = children["section"], children["chapter"]
        if tag == "SD":
            equal(count(f[14]), len(section), "salary section-16 count")
            equal(required(f, 16), sum(amount(v[6]) for v in section), "salary section-16 total")
            equal(count(f[20]), len(chapter), "salary chapter-VIA count")
            equal(required(f, 22), sum(amount(v[6]) for v in chapter), "salary chapter-VIA total")
            for n in (13, 17, 18, 19, 23, 24, 25, 26, 27, 28, 29, 30):
                required(f, n)
            for n in (34, 35, 36, 37):
                if year >= 2013:
                    required(f, n)
                elif f[n - 1]:
                    raise ValueError("Annual salary field predates its declared workbook period")
            if year >= 2013:
                equal(
                    required(f, 13),
                    required(f, 34) + required(f, 35),
                    "salary current/previous-employer total",
                )
            if year >= 2013:
                if f[37] not in {"Y", "N"} or f[58] not in {"", "Y", "N"}:
                    raise ValueError(
                        "Annual higher-rate/superannuation flags are missing or unsupported"
                    )
                if f[58] == "Y":
                    if not f[59].strip() or calendar(f[60]) > calendar(f[61]):
                        raise ValueError("Annual superannuation name or period is incomplete")
                    required(f, 63)
                    required(f, 65)
                    required(f, 66)
                    if not f[63]:
                        raise ValueError(
                            "Annual superannuation requires its recorded four-decimal rate"
                        )
                    equal(
                        required(f, 66),
                        required(f, 19) + required(f, 63),
                        "superannuation inclusive gross",
                    )
                elif any(f[59:66]):
                    raise ValueError("Annual superannuation fields contradict their recorded flag")
            elif f[37] or any(f[58:66]):
                raise ValueError("Annual flags/superannuation fields predate the adopted period")
            if year >= 2016 and f[38] not in {"Y", "N"}:
                raise ValueError("Annual rent threshold flag is required for its recorded period")
            if year < 2015 and any(f[38:58]):
                raise ValueError("Annual landlord/lender fields predate the adopted period")
            contacts(f, 39, 40, 41)
            contacts(f, 49, 50, 51)
            flag = f[78]
            if year >= 2020 and flag not in {"Y", "N"} or year < 2020 and flag:
                raise ValueError("Annual salary regime flag differs from its recorded period")
            restricted = year in range(2020, 2023) and flag == "Y" or year >= 2023 and flag == "N"
            if restricted and required(f, 18) < 0:
                raise ValueError(
                    "Recorded negative other-head income contradicts the annual regime flag"
                )
            if restricted and (
                f[69]
                or f[73]
                or any(v[5] != "80CCD(2)" for v in chapter)
                or any(year < 2023 or v[5] != "16(ia)" for v in section)
            ):
                raise ValueError("Annual children/exemptions contradict the recorded regime flag")
            if year >= 2018:
                for n in (31, 67, 68, 69, 71, 72, 73, 75, 76, 77, 78):
                    required(f, n)
                if not restricted:
                    required(f, 70)
                    required(f, 74)
                if year >= 2023:
                    required(f, 80)
                elif f[79]:
                    raise ValueError(
                        "Recorded special-allowance field is outside adopted FY2023+ scope"
                    )
                equal(
                    required(f, 34),
                    sum(required(f, n) for n in (67, 68, 69)),
                    "current-employer gross salary",
                )
                exemptions = sum(required(f, n) for n in (71, 72, 73, 75))
                exemptions += sum(required(f, n) for n in (70, 74)) if not restricted else 0
                exemptions += required(f, 80) if year >= 2023 else 0
                equal(required(f, 76), exemptions, "section-10 exemption total")
                aggregate = sum(
                    amount(v[6]) for v in chapter if v[5] in {"80C", "80CCC", "80CCD(1)"}
                )
                equal(required(f, 31), aggregate, "recorded three-section deduction aggregate")
                if aggregate > 150000:
                    raise ValueError(
                        "Recorded annual three-section aggregate exceeds the adopted layout limit"
                    )
            elif any(f[n - 1] for n in (31, *range(67, 79))):
                raise ValueError(
                    "Annual detailed salary fields are outside the adopted pre-2018 scope"
                )
            for v in section:
                if v[5] == "16(ia)":
                    cap = (
                        40000 if year == 2018 else 75000 if year >= 2024 and flag == "N" else 50000
                    )
                    if year < 2018 or amount(v[6]) > cap:
                        raise ValueError(
                            "Recorded standard deduction exceeds its adopted period/flag limit"
                        )
            exempt = required(f, 76) if year >= 2018 else 0
            equal(
                required(f, 17),
                required(f, 13) - required(f, 16) - exempt,
                "salary chargeable income",
            )
            equal(
                required(f, 19),
                required(f, 17) + required(f, 18) + (required(f, 77) if year >= 2018 else 0),
                "salary gross income",
            )
            equal(required(f, 23), required(f, 19) - required(f, 22), "salary taxable income")
            equal(
                required(f, 28),
                sum(required(f, n) for n in (24, 25, 26))
                - required(f, 27)
                - (required(f, 78) if year >= 2018 else 0),
                "salary net tax payable",
            )
            if year >= 2024:
                required(f, 81)
            elif f[80]:
                raise ValueError(
                    "Other recorded TDS/TCS field is outside the adopted FY2024+ scope"
                )
            if year >= 2013:
                super_tax = required(f, 65) if f[58] == "Y" else 0
                equal(
                    required(f, 29),
                    required(f, 36)
                    + required(f, 37)
                    + super_tax
                    + (required(f, 81) if year >= 2024 else 0),
                    "salary annual deducted tax",
                )
            equal(
                required(f, 30), required(f, 28) - required(f, 29), "signed salary shortfall/excess"
            )
            if required(f, 23) > 9999999999 or any(
                required(f, n) > required(f, 23) for n in (24, 25, 26, 27, 28)
            ):
                raise ValueError(
                    "Annual salary taxable/component amounts exceed the numbered layout bounds"
                )
        else:
            equal(count(f[10]), len(section), "pension section-16 count")
            equal(required(f, 12), sum(amount(v[6]) for v in section), "pension section-16 total")
            equal(count(f[17]), len(chapter), "pension chapter-VIA count")
            equal(required(f, 19), sum(amount(v[8]) for v in chapter), "pension chapter-VIA total")
            if f[8] not in {"Y", "N"}:
                raise ValueError("Specified-senior annual regime flag is required")
            equal(required(f, 13), required(f, 10) - required(f, 12), "pension chargeable income")
            equal(required(f, 15), required(f, 13) + required(f, 14), "pension gross income")
            equal(required(f, 20), required(f, 15) - required(f, 19), "pension taxable income")
            equal(
                required(f, 25),
                required(f, 21) + required(f, 23) + required(f, 24) - required(f, 22),
                "pension tax payable",
            )
            required(f, 26)
            required(f, 27)
            if required(f, 20) > 9999999999 or any(
                required(f, n) > required(f, 20) for n in (21, 23, 24, 26)
            ):
                raise ValueError(
                    "Annual pension taxable/component amounts exceed the numbered layout bounds"
                )
            equal(
                required(f, 17),
                sum(amount(v[8]) for v in chapter if v[5] in {"80C", "80CCC", "80CCD(1)"}),
                "pension three-section aggregate",
            )
            if required(f, 17) > 150000:
                raise ValueError(
                    "Recorded pension deduction aggregate exceeds the adopted layout limit"
                )
            restricted = year <= 2022 and f[8] == "Y" or year >= 2023 and f[8] == "N"
            if restricted and (
                any(v[5] != "80CCD(2)" for v in chapter)
                or any(year < 2023 or v[5] != "16(ia)" for v in section)
            ):
                raise ValueError("Pension deductions contradict its recorded regime flag")

    for batch_id, header in batches.items():
        salary = [row["fields"] for row in populations["SD"] if row["batch"] == batch_id]
        pension = [row["fields"] for row in populations["94P"] if row["batch"] == batch_id]
        equal(integer(header[48]), len(salary), "batch salary count")
        equal(amount(header[49]), sum(required(f, 19) for f in salary), "batch salary gross income")
        equal(
            integer(header[69]) if header[69] else 0, len(pension), "batch specified-senior count"
        )
        equal(
            amount(header[70]) if header[70] else Decimal(0),
            sum(required(f, 15) for f in pension),
            "batch specified-senior gross income",
        )
    salary = [row["fields"] for row in populations["SD"]]
    pension = [row["fields"] for row in populations["94P"]]
    totals = {
        **{
            name: sum(required(f, n) for f in salary)
            for name, n in {
                "salary_gross_income": 19,
                "salary_taxable_income": 23,
                "salary_net_tax_payable": 28,
                "salary_tax_deducted": 29,
                "salary_shortfall": 30,
            }.items()
        },
        **{
            name: sum(required(f, n) for f in pension)
            for name, n in {
                "pension_gross_income": 15,
                "pension_taxable_income": 20,
                "pension_net_tax_payable": 27,
            }.items()
        },
    }
    if any(getattr(controls, name) != value for name, value in totals.items()):
        raise ValueError("Annual amount totals differ from independent salary/pension controls")
    return {
        "contract": "historical-salary-annual-observations/1",
        "record_counts": controls.record_counts,
        "controls": controls.model_dump(mode="json"),
        "totals": {k: str(v) for k, v in totals.items()},
        "records": sorted(
            [row for tag in TAGS for row in populations[tag]], key=lambda row: row["source_line"]
        ),
        "columns": {tag: layout["columns"][tag] for tag in TAGS},
        "qualification": "RECORDED_COMPONENT_ARITHMETIC_AND_DECLARED_CONTROLS_ONLY",
        "limitations": [
            "Not tax recomputation, deduction/certificate entitlement, complete conditional FVU/CSI or annual all-quarter reconciliation",
            "Independent retained crosswalk and controls cover this exact full file; original Q4 public sample with different widths remains rejected",
            "Field80 uses the explicit FY2023+ applicability sentence despite conflicting earlier-year wording; not complete issuer qualification",
            "Specified-senior net-after-relief formula is not asserted where the numbered workbook gives no explicit formula",
            "Source observations do not establish a current filing, bank payment or tax credit",
        ],
    }
