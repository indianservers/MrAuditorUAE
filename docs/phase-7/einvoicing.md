# Einvoicing

Fourteen actual API-backed VAT areas include readiness and ASP sandbox pages. Readiness assesses reviewed scope, revenue, identifiers, source mapping, provider name/accreditation check, appointment and sandbox readiness. Missing facts return REVIEW_REQUIRED. Large-business threshold includes exactly AED50million; amended appointment30October2026 and implementation1January2027; smaller-business and government dates are represented with explicit human applicability assessment. Pilot dates do not imply universal mandatory adoption.

ASPAdapter is an extension interface; SandboxASP makes zero external requests. It validates a small semantic JSON subset and simulates acceptance, rejection or timeout. Idempotency keys are tenant+engagement+kind scoped, engagement-locked and payload checked; changed replay conflicts, and a retry uses a new key. Each attempt is immutable and clearly SANDBOX_*; external_submission=false.

AuditOS is not an accredited ASP. Full PINT-AE XML/UBL, XSD/Schematron, Peppol transport/discovery, certificates, provider credential lifecycle and live ASP callbacks are not implemented. A PDF is not a structured electronic invoice. MD168/2026 supersedes the old preapproval framework; historical preapproved providers must not be displayed as currently accredited without verification.
