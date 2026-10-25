from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.db.models.platform import FinancialPeriod, LegalEntity
from app.modules.audit_execution.access import firm_roles, role_permissions
from app.modules.audit_log.service import record
from app.modules.jurisdictions.packages import fingerprint
from app.modules.regulatory.models import RuleAction, RuleVersion
from app.modules.regulatory.schemas import Rule

OFFICIAL_HOSTS = {
    "mca.gov.in",
    "icai.org",
    "incometax.gov.in",
    "incometaxindia.gov.in",
    "cbic.gov.in",
    "gst.gov.in",
    "gstcouncil.gov.in",
    "tax.gov.ae",
    "mof.gov.ae",
    "uaelegislation.gov.ae",
    "ifrs.org",
    "oecd.org",
    "adgm.com",
    "dfsa.ae",
    "difc.com",
}


def bound_facts(binding, context, period, supplied, *, functional_currency, tax_base_currency=None):
    if context["framework"].startswith("UNCONFIGURED") or context["entity_type"].startswith(
        "UNCONFIGURED"
    ):
        raise HTTPException(
            409, "Review the engagement reporting context before regulatory assessment"
        )
    authoritative = {
        "country": binding.country,
        "entity_type": context["entity_type"],
        "reporting_framework": context["framework"],
        "period_start": period.start_date.isoformat(),
        "period_end": period.end_date.isoformat(),
        "functional_currency": functional_currency,
        "tax_base_currency": tax_base_currency or functional_currency,
    }
    if any(key in supplied and supplied[key] != value for key, value in authoritative.items()):
        raise HTTPException(422, "Supplied facts contradict the approved engagement context")
    return {**supplied, **authoritative}


async def authorize(db, ctx, permission):
    roles = await firm_roles(db, ctx.tenant_id, ctx.user_id)
    permissions = await role_permissions(db, ctx.tenant_id, [r.id for r in roles])
    if permission not in permissions:
        raise HTTPException(403, "Regulatory administration permission required")
    return roles


async def authorize_read(db, ctx):
    roles = await firm_roles(db, ctx.tenant_id, ctx.user_id)
    permissions = await role_permissions(db, ctx.tenant_id, [r.id for r in roles])
    if not {"audit.read", "tax.rules.manage", "tax.rules.approve"} & set(permissions):
        raise HTTPException(
            403, "Regulatory library access requires an audit or regulatory administration role"
        )


async def lock(db, ctx, key):
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"regulatory:{ctx.tenant_id}:{key}"},
    )


async def sequence(db, ctx, key):
    return (
        await db.scalar(
            select(func.max(RuleAction.sequence)).where(
                RuleAction.tenant_id == ctx.tenant_id, RuleAction.rule_key == key
            )
        )
        or 0
    )


async def get(db, ctx, identifier):
    obj = await db.scalar(
        select(RuleVersion).where(
            RuleVersion.tenant_id == ctx.tenant_id, RuleVersion.id == identifier
        )
    )
    if not obj:
        raise HTTPException(404, "Regulatory version not found")
    return obj


async def state(db, ctx, obj):
    return await db.scalar(
        select(RuleAction)
        .where(RuleAction.tenant_id == ctx.tenant_id, RuleAction.version_id == obj.id)
        .order_by(RuleAction.sequence.desc())
        .limit(1)
    )


async def action(db, ctx, obj, status, comments, request_id, source_receipts=None):
    item = RuleAction(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        rule_key=obj.rule_key,
        version_id=obj.id,
        sequence=(await sequence(db, ctx, obj.rule_key)) + 1,
        state=status,
        body={
            "comments": comments,
            "version_sha256": obj.sha256,
            **({"verified_source_copies": source_receipts} if source_receipts is not None else {}),
        },
    )
    db.add(item)
    await db.flush()
    record(
        db,
        ctx,
        "regulatory." + status.lower(),
        obj.id,
        request_id,
        {"sequence": item.sequence, "sha256": obj.sha256},
    )
    return item


async def propose(db, ctx, data, request_id):
    await authorize(db, ctx, "tax.rules.manage")
    await lock(db, ctx, data.rule_key)
    if await sequence(db, ctx, data.rule_key) != data.expected_sequence:
        raise HTTPException(409, "Rule library changed; reload before proposing")
    if data.reverts_version_id:
        prior = await get(db, ctx, data.reverts_version_id)
        body = data.model_dump(
            mode="json", exclude={"expected_sequence", "amendment_reason", "reverts_version_id"}
        )
        historical = Rule.model_validate(prior.body).model_dump(
            mode="json", exclude={"expected_sequence", "amendment_reason", "reverts_version_id"}
        )
        if prior.rule_key != data.rule_key or body != historical:
            raise HTTPException(
                422, "Revert must copy the selected historical rule content exactly"
            )
    version = (
        await db.scalar(
            select(func.max(RuleVersion.version)).where(
                RuleVersion.tenant_id == ctx.tenant_id, RuleVersion.rule_key == data.rule_key
            )
        )
        or 0
    )
    body = data.model_dump(mode="json")
    obj = RuleVersion(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        rule_key=data.rule_key,
        country=data.country,
        version=version + 1,
        body=body,
        sha256=fingerprint(body),
    )
    db.add(obj)
    await db.flush()
    await action(db, ctx, obj, "DRAFT", data.amendment_reason, request_id)
    return obj


def validation_blockers(rule):
    blockers = []
    if rule.method == "flat_rate" and not rule.calculation_currency:
        blockers.append("A rate-based rule requires an explicit calculation currency")
    if rule.validation_status != "VALIDATED" or rule.professional_review_status != "REVIEWED":
        blockers.append("Technical validation and professional content review must be documented")
    if not rule.last_reviewed or rule.last_reviewed > date.today():
        blockers.append("A valid content review date is required")
    for citation in rule.citations:
        if citation.source_document_id is None:
            blockers.append("A retained regulatory source copy is required for every citation")
        if citation.url.scheme != "https":
            blockers.append("Published citations require HTTPS official sources")
        host = citation.url.host or ""
        if not any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS):
            blockers.append("Source authority is not in the approved source-domain registry")
        if (
            citation.retrieval_status != "RETRIEVED"
            or not citation.document_sha256
            or not citation.retrieved_on
            or citation.retrieved_on > date.today()
        ):
            blockers.append("Source retrieval date and retained-document hash must be attested")
    return sorted(set(blockers))


async def decide(db, ctx, obj, data, request_id):
    roles = await authorize(db, ctx, "tax.rules.approve")
    await lock(db, ctx, obj.rule_key)
    if await sequence(db, ctx, obj.rule_key) != data.expected_sequence:
        raise HTTPException(409, "Rule action sequence changed")
    latest = await db.scalar(
        select(func.max(RuleVersion.version)).where(
            RuleVersion.tenant_id == ctx.tenant_id, RuleVersion.rule_key == obj.rule_key
        )
    )
    if latest != obj.version and data.action != "withdraw":
        raise HTTPException(409, "Only the latest proposal may be reviewed or published")
    previous = await state(db, ctx, obj)
    if data.action == "withdraw":
        if not any(r.name == "Firm Administrator" for r in roles):
            raise HTTPException(
                403, "Only an authorized firm regulatory administrator may withdraw"
            )
        if not previous or previous.state != "PUBLISHED":
            raise HTTPException(409, "Only a published rule version can be withdrawn")
        status = "WITHDRAWN"
    elif data.action == "publish":
        if not any(r.name == "Firm Administrator" for r in roles):
            raise HTTPException(403, "Only an authorized firm regulatory administrator may publish")
        if not previous or previous.state != "APPROVED":
            raise HTTPException(409, "Independent approval required before publication")
        status = "PUBLISHED"
    else:
        if obj.created_by == ctx.user_id:
            raise HTTPException(403, "A proposer cannot review their own rule")
        if not previous or previous.state != "DRAFT":
            raise HTTPException(409, "Only a draft proposal can be reviewed")
        status = "APPROVED" if data.action == "approve" else "REJECTED"
    source_receipts = None
    if status in {"APPROVED", "PUBLISHED"}:
        blockers = validation_blockers(Rule.model_validate(obj.body))
        if blockers:
            raise HTTPException(409, {"regulatory_validation_blockers": blockers})
        from app.modules.regulatory.source_documents import verify_rule_sources

        source_receipts = await verify_rule_sources(db, ctx, Rule.model_validate(obj.body))
        if status == "APPROVED" and str(ctx.user_id) in {
            source["created_by"] for source in source_receipts
        }:
            raise HTTPException(
                403, "A source uploader cannot independently approve a rule using that source"
            )
    return await action(db, ctx, obj, status, data.comments, request_id, source_receipts)


async def selection(db, ctx, key, period_start, period_end, transaction_date=None):
    rows = (
        await db.scalars(
            select(RuleVersion)
            .join(RuleAction, RuleAction.version_id == RuleVersion.id)
            .where(
                RuleVersion.tenant_id == ctx.tenant_id,
                RuleVersion.rule_key == key,
                RuleAction.state == "PUBLISHED",
            )
            .order_by(RuleVersion.version.desc())
        )
    ).all()
    for obj in rows:
        rule = Rule.model_validate(obj.body)
        selected = {
            "period_start": period_start,
            "period_end": period_end,
            "transaction_date": transaction_date,
        }[rule.period_basis]
        if (
            selected
            and rule.effective_from <= selected
            and (not rule.effective_to or selected <= rule.effective_to)
        ):
            latest_action = await state(db, ctx, obj)
            if latest_action is None or latest_action.state != "PUBLISHED":
                raise HTTPException(
                    409,
                    {
                        "code": "withdrawn_rule",
                        "rule_id": str(obj.id),
                        "rule_key": obj.rule_key,
                        "message": "The selected published rule was withdrawn; publish an independently reviewed replacement before reuse",
                    },
                )
            blockers = validation_blockers(rule)
            if blockers:
                raise HTTPException(
                    409,
                    {
                        "code": "unverified_rule",
                        "rule_id": str(obj.id),
                        "blocking_issues": blockers,
                    },
                )
            from app.modules.regulatory.source_documents import verify_rule_sources

            await verify_rule_sources(db, ctx, rule)
            return obj
    return None


async def assess(db, ctx, eng, data, request_id):
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved
    from app.modules.regulatory.evaluation import evaluate

    period = await db.get(FinancialPeriod, eng.period_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    binding, context = await resolved(db, ctx, eng)
    outputs, dependencies = [], []
    base_currency = entity.functional_currency
    expected_base = None
    if data.source_event_id:
        source = await intelligence.event(db, ctx, eng.id, data.source_event_id, True)
        if source.kind != "lead" or source.body.get("review_status") != "REVIEWED":
            raise HTTPException(409, "A current independently reviewed lead schedule is required")
        dependencies.append(intelligence.event_receipt(source))
        expected_base = source.body["totals"]["closing"]
    if data.conversion_event_id:
        conversion = await intelligence.event(db, ctx, eng.id, data.conversion_event_id, True)
        if (
            conversion.kind != "regulatory-conversion"
            or conversion.body.get("conversion_contract") != "reviewed-rate-conversion/1"
            or conversion.body.get("review_status") != "REVIEWED"
        ):
            raise HTTPException(
                409, "A current independently reviewed currency conversion is required"
            )
        if (
            conversion.body.get("source_event_id") != str(data.source_event_id)
            or conversion.body.get("source_currency") != entity.functional_currency
        ):
            raise HTTPException(
                422, "Conversion does not originate from the selected reviewed schedule"
            )
        base_currency = conversion.body["target_currency"]
        expected_base = conversion.body["converted_amount"]
        dependencies.append(intelligence.event_receipt(conversion))
    facts = bound_facts(
        binding,
        context,
        period,
        data.facts,
        functional_currency=entity.functional_currency,
        tax_base_currency=base_currency,
    )
    for identifier in data.rule_ids:
        obj = await get(db, ctx, identifier)
        rule = Rule.model_validate(obj.body)
        if rule.method == "benefit_profile":
            raise HTTPException(
                422, "Use the employee-level UAE benefit workflow for a benefit profile"
            )
        if rule.method == "payroll_profile":
            raise HTTPException(
                422, "Use the India payroll contribution workflow for a payroll profile"
            )
        if rule.country != binding.country or rule.framework != context["framework"]:
            raise HTTPException(
                422, "Rule country/framework does not match the approved reporting context"
            )
        current = await selection(
            db, ctx, obj.rule_key, period.start_date, period.end_date, data.transaction_date
        )
        if not current or current.id != obj.id:
            raise HTTPException(409, "Select the current published rule for this reporting period")
        if rule.method == "flat_rate":
            from decimal import Decimal, InvalidOperation

            if not data.source_event_id:
                raise HTTPException(
                    422, "A reviewed source schedule and documented tax-base selection are required"
                )
            if rule.calculation_currency != base_currency:
                raise HTTPException(
                    422,
                    "Rule calculation currency differs from the reviewed source currency; an explicit conversion workflow is required",
                )
            try:
                agrees = Decimal(str(data.facts.get("tax_base"))) == Decimal(str(expected_base))
            except (InvalidOperation, KeyError):
                agrees = False
            if not agrees:
                raise HTTPException(
                    422,
                    "Tax base must agree exactly to the reviewed source balance or its reviewed conversion",
                )
        provenance_missing = await validate_fact_sources(
            db,
            ctx,
            eng,
            rule,
            facts,
            data.fact_sources,
            dependencies,
            {"tax_base"} if rule.method == "flat_rate" and data.source_event_id else set(),
        )
        evaluated = evaluate(rule, facts, period.start_date, period.end_date, data.transaction_date)
        if provenance_missing:
            evaluated.pop("calculation", None)
            evaluated.update(applicability="PENDING", missing_fact_provenance=provenance_missing)
        outputs.append(
            {
                "rule_id": str(obj.id),
                "rule_key": obj.rule_key,
                "rule_version": obj.version,
                "selection_explanation": {
                    "policy": "Highest independently approved and published version of the same stable rule key covering the selected date",
                    "period_basis": rule.period_basis,
                    "effective_from": rule.effective_from.isoformat(),
                    "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
                    "entity_facts_evaluated_separately": True,
                },
                "sha256": obj.sha256,
                "citations": obj.body["citations"],
                **evaluated,
            }
        )
        dependencies.append(
            {
                "type": "regulatory",
                "id": str(obj.id),
                "rule_key": obj.rule_key,
                "sha256": obj.sha256,
                "transaction_date": data.transaction_date.isoformat()
                if data.transaction_date
                else None,
            }
        )
    result = await intelligence.append(
        db,
        ctx,
        eng,
        "regulatory-assessment",
        {
            "title": "Reviewed-rule applicability assessment",
            "rows": outputs,
            "facts": facts,
            "fact_sources": {
                key: value.model_dump(mode="json") for key, value in data.fact_sources.items()
            },
            "rationale": data.rationale,
            "review_status": "UNVERIFIED",
            "contributors": [str(ctx.user_id)],
            "source_warning": "Applicability facts and tax-base selection are professional inputs. Source hashes and content validation are attestations; publication is not government approval or filing.",
        },
        dependencies,
        request_id,
    )
    return result


async def checklist(db, ctx, eng, data, request_id):
    from app.modules.audit_execution import service as audit
    from app.modules.audit_execution.models import EvidenceVersion
    from app.modules.intelligence import service as intelligence
    from app.modules.jurisdictions.workspace import resolved
    from app.modules.regulatory.evaluation import evaluate

    binding, context = await resolved(db, ctx, eng)
    expected_country = (
        "IN"
        if data.area.startswith("india-") or data.area in {"companies-act", "caro"}
        else "AE"
        if data.area in {"uae-disclosures", "qfzp-assessment", "dmtt-applicability"}
        else binding.country
    )
    if binding.country != expected_country:
        raise HTTPException(422, "This specialist checklist does not match the engagement country")
    period = await db.get(FinancialPeriod, eng.period_id)
    entity = await db.get(LegalEntity, eng.entity_id)
    if len({i.clause for i in data.items}) != len(data.items):
        raise HTTPException(422, "Clause identifiers must be unique")
    rows: list[dict] = []
    dependencies: list[dict] = []
    if sum(len(i.fact_sources) for i in data.items) > 100:
        raise HTTPException(422, "A checklist is limited to 100 explicit fact-source bindings")
    for item in data.items:
        obj = await get(db, ctx, item.rule_id)
        rule = Rule.model_validate(obj.body)
        selected = await selection(db, ctx, obj.rule_key, period.start_date, period.end_date)
        if (
            not selected
            or selected.id != obj.id
            or rule.country != binding.country
            or rule.framework != context["framework"]
        ):
            raise HTTPException(
                409,
                "Every clause requires a current published rule matching the engagement framework and period",
            )
        applicability = evaluate(
            rule,
            bound_facts(
                binding, context, period, item.facts, functional_currency=entity.functional_currency
            ),
            period.start_date,
            period.end_date,
        )
        provenance_missing = await validate_fact_sources(
            db, ctx, eng, rule, item.facts, item.fact_sources, dependencies
        )
        if provenance_missing:
            applicability.pop("calculation", None)
            applicability.update(
                applicability="PENDING", missing_fact_provenance=provenance_missing
            )
        if item.state == "NOT_APPLICABLE" and (
            len(item.conclusion.strip()) < 10 or applicability["applicability"] != "NOT_APPLICABLE"
        ):
            raise HTTPException(
                422, "Not-applicable decisions require consistent facts and a documented conclusion"
            )
        if item.state in {"PREPARED", "EXCEPTION_IDENTIFIED"}:
            if (
                applicability["applicability"] != "APPLICABLE"
                or not item.evidence_ids
                or len(item.procedure.strip()) < 10
                or len(item.conclusion.strip()) < 10
            ):
                raise HTTPException(
                    422,
                    "Prepared clause conclusions require resolved applicability, actual evidence and performed procedures",
                )
        for identifier in item.evidence_ids:
            evidence = await audit.get_record(db, ctx, eng.id, identifier, lock=False)
            if (
                evidence.kind not in {"evidence", "working-papers", "findings"}
                or evidence.status == "ARCHIVED"
            ):
                raise HTTPException(
                    422, "Evidence must be an active audit evidence, working paper or finding"
                )
            if item.state == "PREPARED" and evidence.status not in {
                "APPROVED",
                "LOCKED",
                "RESOLVED",
                "CLOSED",
            }:
                raise HTTPException(409, "Prepared clause evidence needs professional review")
            if evidence.kind == "working-papers":
                from app.modules.lineage.working_papers import require_current

                await require_current(db, ctx, evidence)
            dependencies.append(
                {"type": "record", "id": str(evidence.id), "version": evidence.version}
            )
            if evidence.kind == "evidence":
                version = await db.scalar(
                    select(EvidenceVersion)
                    .where(
                        EvidenceVersion.tenant_id == ctx.tenant_id,
                        EvidenceVersion.record_id == evidence.id,
                    )
                    .order_by(EvidenceVersion.number.desc())
                    .limit(1)
                )
                if not version or version.scan_status != "CLEAN":
                    raise HTTPException(
                        409, "Supporting document must be retained and malware-cleared"
                    )
                dependencies.append(
                    {
                        "type": "evidence",
                        "id": str(version.id),
                        "record_id": str(evidence.id),
                        "number": version.number,
                        "sha256": version.sha256,
                    }
                )
        dependencies.append(
            {
                "type": "regulatory",
                "id": str(obj.id),
                "rule_key": obj.rule_key,
                "sha256": obj.sha256,
            }
        )
        rows.append(
            {
                **item.model_dump(mode="json"),
                "applicability_result": applicability,
                "rule_version": obj.version,
                "citations": obj.body["citations"],
                "prepared_by": str(ctx.user_id),
            }
        )
    prior = None
    if data.prior_id:
        prior = await intelligence.event(db, ctx, eng.id, data.prior_id)
        if (
            prior.kind != "statutory-checklist"
            or prior.body["area"] != data.area
            or prior.version != data.expected_version
        ):
            raise HTTPException(409, "Specialist checklist version conflict")
    elif data.expected_version != 0:
        raise HTTPException(409, "New checklist must start with version zero")
    return await intelligence.append(
        db,
        ctx,
        eng,
        "statutory-checklist",
        {
            "title": data.title,
            "area": data.area,
            "items": rows,
            "rationale": data.rationale,
            "review_status": "UNVERIFIED",
            "contributors": sorted(
                {str(ctx.user_id), *(prior.body.get("contributors", []) if prior else [])}
            ),
            "professional_conclusion": "Draft clause decisions; no compliance certification or statutory filing is represented",
        },
        dependencies,
        request_id,
        prior,
    )


async def validate_fact_sources(
    db, ctx, eng, rule, facts, bindings, dependencies, already_grounded=()
):
    from decimal import Decimal, InvalidOperation

    from app.modules.audit_execution import service as audit
    from app.modules.intelligence import service as intelligence

    numeric = {p.field for p in rule.applicability if p.operator in {"gte", "gt", "lte", "lt"}}
    if rule.method == "flat_rate":
        numeric.add("tax_base")
    missing = sorted(numeric - set(bindings) - set(already_grounded))
    for field, binding in bindings.items():
        if field not in facts or facts[field] is None:
            raise HTTPException(422, "A fact-source binding must name a supplied fact")
        if binding.kind == "intelligence":
            source = await intelligence.event(db, ctx, eng.id, binding.id, True)
            if source.body.get("review_status") != "REVIEWED":
                raise HTTPException(409, "Numeric fact sources require independent review")
            dependencies.append(intelligence.event_receipt(source))
        else:
            source = await audit.get_record(db, ctx, eng.id, binding.id, lock=False)
            if source.status not in {"APPROVED", "LOCKED"}:
                raise HTTPException(
                    409, "Numeric fact source records require professional approval"
                )
            from app.modules.lineage.working_papers import require_current

            await require_current(db, ctx, source)
            dependencies.append({"type": "record", "id": str(source.id), "version": source.version})
        value = source.body
        try:
            for segment in binding.path:
                if isinstance(segment, int) and (segment < 0 or segment > 10000):
                    raise ValueError("Index bound")
                value = value[segment]
            left, right = Decimal(str(facts[field])), Decimal(str(value))
            if not left.is_finite() or not right.is_finite() or left != right:
                raise ValueError("Source value mismatch")
        except (KeyError, IndexError, TypeError, InvalidOperation, ValueError):
            raise HTTPException(
                422, "Numeric applicability fact does not agree to the selected source field"
            ) from None
    return missing
