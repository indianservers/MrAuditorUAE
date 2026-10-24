"""25 independently versioned full-population rules on a temporary DuckDB dataset.
Amounts remain DECIMAL. Floating point is confined to statistical distribution tests.
"""

import csv
import tempfile
import time
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from app.modules.audit_analytics.schemas import AnalyticsRequest

RULES = [
    ("J01", "Weekend postings", "posting_date"),
    ("J02", "Configured public holidays", "holiday calendar"),
    ("J03", "After-hours postings", "reliable timestamp, timezone, business hours"),
    ("J04", "Round amounts", "amount"),
    ("J05", "Duplicate journals", "journal/account/amount"),
    ("J06", "Near-duplicate journals", "journal/account/date/amount"),
    ("J07", "Unusual descriptions", "description"),
    ("J08", "High-value entries", "amount"),
    ("J09", "Materiality exceedance", "materiality"),
    ("J10", "Manual year-end entries", "manual flag, year end"),
    ("J11", "Post-year-end reversals", "reversal reference, year end"),
    ("J12", "Unusual debit/credit combinations", "normal account classification"),
    ("J13", "Rare accounts", "account frequency"),
    ("J14", "Unexpected account pairings", "approved expected pairings"),
    ("J15", "Dormant accounts reactivated", "prior last activity"),
    ("J16", "Suspense postings", "approved suspense mapping"),
    ("J17", "Unexpected negative balance", "normal account classification"),
    ("J18", "Large activity changes", "prior activity"),
    ("J19", "Voucher sequence gaps", "confirmed numeric sequence"),
    ("J20", "Posting/document date gap", "document date"),
    ("S21", "Benford first digit", "suitable natural monetary population"),
    ("S22", "Amount frequency", "amount"),
    ("S23", "Amount outliers", "amount"),
    ("S24", "Unusual daily velocity", "posting_date"),
    ("S25", "Counterparty/user concentration", "counterparty or user"),
]
VERSION = "2.1.0"
COLUMNS = [
    "id",
    "account_code",
    "journal_ref",
    "posting_date",
    "document_date",
    "posting_timestamp",
    "debit",
    "credit",
    "amount",
    "description",
    "counterparty",
    "user",
    "manual",
    "reversal_ref",
    "category",
    "contra",
    "source_group",
]


def quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def risk_score(factors: list[str], weights: dict[str, Decimal]) -> dict:
    used = {f: weights.get(f, Decimal(10)) for f in sorted(set(factors))}
    if any(v < 0 or v > 100 for v in used.values()):
        raise ValueError("Invalid risk weight")
    score = min(Decimal(100), sum(used.values(), Decimal(0)))
    band = (
        "Low" if score < 25 else "Moderate" if score < 50 else "High" if score < 75 else "Critical"
    )
    return {
        "score": score,
        "band": band,
        "factors": {key: str(value) for key, value in used.items()},
        "ruleset_version": VERSION,
        "explanation": "Deterministic weighted indicators; not a fraud probability",
    }


class AnalyticsEngine:
    def __init__(self, population: Iterable[dict]):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        file = self.path / "population.csv"
        with file.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            for row in population:
                data = {key: row.get(key) for key in COLUMNS}
                data["amount"] = str(
                    abs(Decimal(str(row.get("debit", 0))) - Decimal(str(row.get("credit", 0))))
                )
                writer.writerow(data)
        self.db: Any = duckdb.connect(str(self.path / "analytics.duckdb"))
        self.db.execute("SET memory_limit='1GB'")
        self.db.execute("SET threads=2")
        self.db.execute("SET preserve_insertion_order=false")
        self.db.execute("SET temp_directory=" + quote(self.path / "spill"))
        self.db.execute(
            "CREATE TABLE p AS SELECT * EXCLUDE (posting_date,document_date,posting_timestamp,debit,credit,amount,manual,contra),try_cast(posting_date AS DATE) posting_date,try_cast(document_date AS DATE) document_date,try_cast(posting_timestamp AS TIMESTAMPTZ) posting_timestamp,cast(debit AS DECIMAL(28,8)) debit,cast(credit AS DECIMAL(28,8)) credit,cast(amount AS DECIMAL(28,8)) amount,(manual IS NOT NULL) manual_known,coalesce(try_cast(manual AS BOOLEAN),false) manual,coalesce(try_cast(contra AS BOOLEAN),false) contra FROM read_csv(?,all_varchar=true)",
            [str(file)],
        )
        self.db.execute("CREATE TABLE flags(rule VARCHAR,id VARCHAR,evidence VARCHAR)")
        count_row = self.db.execute("SELECT count(*) FROM p").fetchone()
        assert count_row is not None
        self.count = count_row[0]
        # Ordered string aggregates allocate per journal and cannot reliably spill.
        # Hash-partition whole journals, retaining exact canonical signatures while
        # bounding the number of aggregate states alive at once on large populations.
        partitions = max(1, min(64, (self.count + 24999) // 25000))
        signature = "SELECT journal_ref, string_agg(DISTINCT account_code, '|' ORDER BY account_code) accounts, min(posting_date) posting_date, sum(debit) debit, string_agg(account_code||':'||cast(debit AS VARCHAR)||':'||cast(credit AS VARCHAR),'|' ORDER BY account_code,debit,credit) sig FROM p"
        self.db.execute(
            "CREATE TABLE signatures AS " + signature + " WHERE false GROUP BY journal_ref"
        )
        for partition in range(partitions):
            self.db.execute(
                "INSERT INTO signatures "
                + signature
                + " WHERE hash(journal_ref) % ? = ? GROUP BY journal_ref",
                [partitions, partition],
            )

    def close(self):
        self.db.close()
        self.directory.cleanup()

    def evaluate(self, config: AnalyticsRequest) -> list[dict]:
        # Findings belong to this configuration. Re-evaluation must not retain
        # flags from a previous calendar, threshold or prerequisite assessment.
        self.db.execute("DELETE FROM flags")
        p = config
        end = quote(p.year_end) if p.year_end else "NULL"
        window = p.year_end_window
        sql = {
            "J01": f"SELECT id FROM p WHERE ((isodow(posting_date)+6)%7) IN ({','.join(str(d) for d in p.weekend_days) or '-1'})",
            "J02": "SELECT id FROM p WHERE posting_date IN ("
            + (",".join(quote(d) for d in p.holidays) if p.holidays else "NULL")
            + ")",
            "J03": f"SELECT id FROM p WHERE posting_timestamp IS NOT NULL AND (extract(hour FROM timezone({quote(p.timezone or 'UTC')},posting_timestamp)) < {(p.business_hours or (0, 24))[0]} OR extract(hour FROM timezone({quote(p.timezone or 'UTC')},posting_timestamp)) >= {(p.business_hours or (0, 24))[1]})",
            "J04": f"SELECT id FROM p WHERE amount >= {p.round_unit} AND amount % {p.round_unit}=0",
            "J05": "SELECT p.id FROM p JOIN signatures s USING(journal_ref) WHERE s.sig IN (SELECT sig FROM signatures GROUP BY sig HAVING count(*)>1)",
            "J06": f"SELECT p.id FROM p JOIN (SELECT *, lag(debit) OVER w prev_debit,lag(posting_date) OVER w prev_date,lag(sig) OVER w prev_sig FROM signatures WINDOW w AS (PARTITION BY accounts ORDER BY debit,posting_date,journal_ref)) s USING(journal_ref) WHERE s.debit>0 AND abs(s.debit-s.prev_debit)<=s.debit*{p.near_duplicate_ratio} AND abs(date_diff('day',s.posting_date,s.prev_date))<={p.near_duplicate_days} AND s.sig<>s.prev_sig",
            "J07": "SELECT id FROM p WHERE "
            + (
                " OR ".join(
                    "contains(lower(coalesce(description,''))," + quote(w.lower()) + ")"
                    for w in p.unusual_words
                )
                or "false"
            ),
            "J08": f"SELECT id FROM p WHERE amount >= {p.high_value}",
            "J09": f"SELECT id FROM p WHERE amount > {p.materiality}",
            "J10": f"SELECT id FROM p WHERE manual AND posting_date BETWEEN cast({end} AS DATE)-{window} AND cast({end} AS DATE)",
            "J11": f"SELECT id FROM p WHERE reversal_ref IS NOT NULL AND posting_date>cast({end} AS DATE) AND posting_date<=cast({end} AS DATE)+{window}",
            "J12": "SELECT id FROM p WHERE (category IN ('Assets','Expenses') AND NOT contra AND credit>0) OR (category IN ('Liabilities','Equity','Income') AND NOT contra AND debit>0) OR (category IN ('Assets','Expenses') AND contra AND debit>0) OR (category IN ('Liabilities','Equity','Income') AND contra AND credit>0)",
            "J13": f"SELECT id FROM p WHERE account_code IN (SELECT account_code FROM p GROUP BY account_code HAVING count(*)<={p.rare_count})",
            "J14": "SELECT id FROM p WHERE false",
            "J15": "SELECT id FROM p WHERE false",
            "J16": "SELECT id FROM p WHERE lower(coalesce(source_group,''))='suspense'",
            "J17": "SELECT id FROM p WHERE account_code IN (SELECT account_code FROM p GROUP BY account_code HAVING (bool_or(category IN ('Assets','Expenses') AND NOT contra) AND sum(debit-credit)<0) OR (bool_or(category IN ('Liabilities','Equity','Income') AND contra) AND sum(debit-credit)<0))",
            "J18": "SELECT id FROM p WHERE false",
            "J19": "SELECT p.id FROM p JOIN (SELECT journal_ref,try_cast(journal_ref AS BIGINT) n,lag(try_cast(journal_ref AS BIGINT)) OVER(ORDER BY try_cast(journal_ref AS BIGINT)) previous FROM signatures WHERE try_cast(journal_ref AS BIGINT) IS NOT NULL) gaps USING(journal_ref) WHERE gaps.n-gaps.previous>1",
            "J20": f"SELECT id FROM p WHERE document_date IS NOT NULL AND abs(date_diff('day',document_date,posting_date))>{p.date_gap_days}",
            "S22": f"SELECT id FROM p WHERE amount IN (SELECT amount FROM p WHERE amount>0 GROUP BY amount HAVING count(*)>greatest({p.frequency_min_count},{p.frequency_ratio}*{self.count}))",
            "S23": f"SELECT id FROM p WHERE amount>(SELECT quantile_cont(amount,0.75)+{p.outlier_multiple}*(quantile_cont(amount,0.75)-quantile_cont(amount,0.25)) FROM p)",
            "S24": f"SELECT id FROM p WHERE posting_date IN (SELECT posting_date FROM p GROUP BY posting_date HAVING count(*)>{p.velocity_limit})",
            "S25": f"""SELECT id FROM p WHERE counterparty IN (SELECT counterparty FROM p WHERE counterparty IS NOT NULL GROUP BY counterparty HAVING count(*)>{p.concentration}*{self.count}) OR "user" IN (SELECT "user" FROM p WHERE "user" IS NOT NULL GROUP BY "user" HAVING count(*)>{p.concentration}*{self.count})""",
        }
        if p.expected_pairs is not None:
            allowed = {tuple(sorted(pair)) for pair in p.expected_pairs if len(pair) == 2}
            allowed_sql = (
                " OR ".join(
                    f"(a.account_code={quote(a)} AND b.account_code={quote(b)})" for a, b in allowed
                )
                or "false"
            )
            sql["J14"] = (
                f"SELECT DISTINCT a.id FROM p a JOIN p b ON a.journal_ref=b.journal_ref AND a.account_code<b.account_code WHERE NOT ({allowed_sql})"
            )
        if p.last_activity:
            terms = [
                f"(account_code={quote(code)} AND posting_date>cast({quote(last)} AS DATE)+{p.dormant_days})"
                for code, last in p.last_activity.items()
            ]
            sql["J15"] = "SELECT id FROM p WHERE " + " OR ".join(terms)
        if p.prior_activity:
            terms = [
                f"account_code={quote(code)}"
                for code, prior in p.prior_activity.items()
                if prior == 0
            ]
            for code, prior in p.prior_activity.items():
                if prior > 0:
                    terms.append(
                        f"account_code={quote(code)} AND account_code IN (SELECT account_code FROM p GROUP BY account_code HAVING sum(amount)>{prior}*{p.activity_multiple})"
                    )
            sql["J18"] = "SELECT id FROM p WHERE " + (
                " OR ".join("(" + term + ")" for term in terms) or "false"
            )

        def available(field):
            return self.db.execute(f"SELECT count(*) FROM p WHERE {field} IS NOT NULL").fetchone()[
                0
            ]

        missing = {
            "J01": not p.weekend_days,
            "J02": p.holidays is None,
            "J03": not (
                p.timestamps_reliable
                and p.timezone
                and p.business_hours
                and available("posting_timestamp")
            ),
            "J10": p.year_end is None
            or not self.db.execute("SELECT count(*) FROM p WHERE manual_known").fetchone()[0],
            "J11": p.year_end is None or not available("reversal_ref"),
            "J12": not available("category"),
            "J14": p.expected_pairs is None,
            "J15": not p.last_activity,
            "J16": not available("source_group"),
            "J17": not available("category"),
            "J18": not p.prior_activity,
            "J19": not p.voucher_sequential,
            "J20": not available("document_date"),
            "S25": not (available("counterparty") or available('"user"')),
        }
        results = []
        for code, name, requires in RULES:
            start = time.perf_counter()
            evidence = {}
            status = "passed"
            tested = self.count
            eligible_fields = {
                "J03": "posting_timestamp",
                "J11": "reversal_ref",
                "J12": "category",
                "J16": "source_group",
                "J17": "category",
                "J20": "document_date",
            }
            if code in eligible_fields:
                tested = available(eligible_fields[code])
            if not self.count or missing.get(code, False):
                status = "not_testable"
                tested = 0
                evidence = {
                    "reason": "Required population, operating calendar or source fields unavailable; no clean conclusion inferred"
                }
            elif code == "S21":
                n, distinct, low, high = self.db.execute(
                    "SELECT count(*),count(DISTINCT amount),min(amount),max(amount) FROM p WHERE amount>0"
                ).fetchone()
                if (
                    not p.benford_eligible
                    or n < p.benford_min_count
                    or distinct < p.benford_min_distinct
                    or high / low < p.benford_min_span
                ):
                    status = "not_testable"
                    tested = 0
                    evidence = {
                        "reason": "unsuitable Benford population",
                        "positive_count": n,
                        "distinct": distinct,
                    }
                else:
                    tested = n
                    counts = dict(
                        self.db.execute(
                            "SELECT substr(regexp_replace(cast(amount AS VARCHAR),'[^1-9]','','g'),1,1) digit,count(*) FROM p WHERE amount>0 GROUP BY digit"
                        ).fetchall()
                    )
                    import math

                    chi = sum(
                        (counts.get(str(d), 0) - n * math.log10(1 + 1 / d)) ** 2
                        / (n * math.log10(1 + 1 / d))
                        for d in range(1, 10)
                    )
                    evidence = {
                        "chi_square": chi,
                        "threshold": str(p.benford_chi_limit),
                        "counts": counts,
                        "scope": "population",
                    }
                    status = "warning" if chi > float(p.benford_chi_limit) else "passed"
            else:
                self.db.execute(
                    "INSERT INTO flags SELECT ?,id,? FROM (" + sql[code] + ")", [code, name]
                )
            count = self.db.execute("SELECT count(*) FROM flags WHERE rule=?", [code]).fetchone()[0]
            if count:
                status = "warning"
            if code == "S21" and status == "warning":
                count = 1
            exceptions = self.db.execute(
                "SELECT id,evidence FROM flags WHERE rule=? ORDER BY id LIMIT 20", [code]
            ).fetchall()
            results.append(
                {
                    "test_name": name,
                    "rule_id": code,
                    "rule_version": VERSION,
                    "status": status,
                    "population_size": self.count,
                    "tested_population": tested,
                    "flagged_count": count,
                    "severity": "review" if count else "information",
                    "input_snapshot": str(p.snapshot_id),
                    "parameters": p.model_dump(mode="json"),
                    "calculation_evidence": {
                        "predicate": sql.get(code, "Benford population chi-square"),
                        **evidence,
                    },
                    "execution_ms": round((time.perf_counter() - start) * 1000, 3),
                    "exceptions": [{"line_id": i, "indicator": e} for i, e in exceptions],
                    "exceptions_preview_limit": 20,
                }
            )
        return results

    def flags(self):
        cursor = self.db.execute("SELECT rule,id,evidence FROM flags ORDER BY rule,id")
        while chunk := cursor.fetchmany(1000):
            yield chunk

    def scores(self, weights: dict[str, Decimal]):
        cursor = self.db.execute("SELECT id,list(DISTINCT rule) FROM flags GROUP BY id ORDER BY id")
        while chunk := cursor.fetchmany(1000):
            yield [(identifier, risk_score(factors, weights)) for identifier, factors in chunk]
