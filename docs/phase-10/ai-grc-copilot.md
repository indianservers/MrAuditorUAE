# AI GRC Copilot

Thirty task types cover universe suggestions, plan coverage, scope, risks, control mapping/design/testing, walkthroughs, SoD, exceptions, root causes, remediation, period/KRI comparison, ML explanations, alerts, management questions, missing evidence, policy/vendor review, reports, overdue actions, committee briefings, quality improvements and technical memoranda.

Retrieval accepts only approved same-engagement records authorized for the caller, with bounded source count and payload size. Sensitive owner/team fields are omitted. The existing approved-model gateway enforces external-disclosure configuration and per-user hourly limits; strict Pydantic output requires citations confined to supplied records, mandatory human review and no opinion/evidence-sufficiency conclusion. Suggestions are immutable and cannot close findings, sign reports, retrain models or change calculations.

All 30 diagnostic task paths were exercised in the real API test. The configured local provider explicitly returns MOCK DIAGNOSTIC output; no live semantic GRC reasoning or fabricated legal research is claimed. An approved external provider and separate evaluation are needed before production generative use.
