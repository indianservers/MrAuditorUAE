# Role and permission catalogue

Defaults are installed in database roles/permissions. Firm-specific policies replace role permission sets without modifying shared source defaults. Multiple firm membership roles and multiple engagement-specific role grants are supported. Engagement actions use the scoped roles rather than assuming a firm title grants access to every engagement.

Platform roles have no financial-data grants. Client roles are restricted to allowlisted portal data. Firm administrators may assign teams and policies, but cannot self-approve preparation or impersonate an independent quality reviewer.

## Platform Administrator

`platform.manage`.

## Firm Administrator

`accounting.import`, `accounting.map`, `accounting.read`, `ai.audit.execute`, `ai.execute`, `ai.read`, `analytics.read`, `analytics.run`, `audit.evidence.review`, `audit.evidence.upload`, `audit.export`, `audit.finding.create`, `audit.finding.resolve`, `audit.materiality.approve`, `audit.materiality.prepare`, `audit.plan`, `audit.program.prepare`, `audit.program.review`, `audit.read`, `audit.risk.approve`, `audit.risk.prepare`, `audit.testing.execute`, `clients.read`, `clients.write`, `connectors.manage`, `engagement.accept`, `engagement.accept.prepare`, `engagement.archive`, `engagement.assign`, `engagement.create`, `engagement.finalize`, `engagement.quality_review`, `engagements.read`, `engagements.write`, `entities.read`, `entities.write`, `financial_ai.approve`, `financial_ai.execute`, `independence.declare`, `independence.review`, `jobs.execute`, `jobs.read`, `members.manage`, `methodology.manage`, `sampling.run`, `tenant.manage`, `users.assign_roles`, `users.invite`, `workingpaper.approve`, `workingpaper.create`, `workingpaper.review`.

## Audit Partner

`ai.audit.execute`, `ai.execute`, `ai.read`, `audit.evidence.review`, `audit.evidence.upload`, `audit.export`, `audit.finding.create`, `audit.finding.resolve`, `audit.materiality.approve`, `audit.materiality.prepare`, `audit.plan`, `audit.program.prepare`, `audit.program.review`, `audit.read`, `audit.risk.approve`, `audit.risk.prepare`, `audit.testing.execute`, `clients.read`, `engagement.accept`, `engagement.accept.prepare`, `engagement.archive`, `engagement.assign`, `engagement.finalize`, `engagements.read`, `engagements.write`, `entities.read`, `independence.declare`, `independence.review`, `jobs.read`, `workingpaper.approve`, `workingpaper.create`, `workingpaper.review`.

## Audit Manager

`ai.audit.execute`, `ai.execute`, `ai.read`, `audit.evidence.review`, `audit.evidence.upload`, `audit.finding.create`, `audit.finding.resolve`, `audit.materiality.prepare`, `audit.plan`, `audit.program.prepare`, `audit.program.review`, `audit.read`, `audit.risk.prepare`, `audit.testing.execute`, `clients.read`, `engagement.accept.prepare`, `engagement.assign`, `engagements.read`, `engagements.write`, `entities.read`, `independence.declare`, `workingpaper.approve`, `workingpaper.create`, `workingpaper.review`.

## Senior Auditor

`ai.audit.execute`, `ai.execute`, `ai.read`, `audit.evidence.upload`, `audit.finding.create`, `audit.materiality.prepare`, `audit.plan`, `audit.program.prepare`, `audit.read`, `audit.risk.prepare`, `audit.testing.execute`, `clients.read`, `engagement.accept.prepare`, `engagements.read`, `entities.read`, `independence.declare`, `workingpaper.create`.

## Auditor

`ai.audit.execute`, `audit.evidence.upload`, `audit.finding.create`, `audit.materiality.prepare`, `audit.plan`, `audit.program.prepare`, `audit.read`, `audit.risk.prepare`, `audit.testing.execute`, `clients.read`, `engagement.accept.prepare`, `engagements.read`, `entities.read`, `independence.declare`, `workingpaper.create`.

## Tax Manager

`clients.read`, `entities.read`, `engagements.read`, `engagements.write`, `ai.read`, `ai.execute`.

## Tax Consultant

`clients.read`, `entities.read`, `engagements.read`.

## Client Viewer

`portal.read`.

## Managing Partner

`ai.audit.execute`, `ai.execute`, `ai.read`, `audit.evidence.review`, `audit.evidence.upload`, `audit.export`, `audit.finding.create`, `audit.finding.resolve`, `audit.materiality.approve`, `audit.materiality.prepare`, `audit.plan`, `audit.program.prepare`, `audit.program.review`, `audit.read`, `audit.risk.approve`, `audit.risk.prepare`, `audit.testing.execute`, `clients.read`, `engagement.accept`, `engagement.accept.prepare`, `engagement.archive`, `engagement.assign`, `engagement.finalize`, `engagements.read`, `engagements.write`, `entities.read`, `independence.declare`, `independence.review`, `jobs.read`, `workingpaper.approve`, `workingpaper.create`, `workingpaper.review`.

## Audit Partner / Chartered Accountant

`ai.audit.execute`, `ai.execute`, `ai.read`, `audit.evidence.review`, `audit.evidence.upload`, `audit.export`, `audit.finding.create`, `audit.finding.resolve`, `audit.materiality.approve`, `audit.materiality.prepare`, `audit.plan`, `audit.program.prepare`, `audit.program.review`, `audit.read`, `audit.risk.approve`, `audit.risk.prepare`, `audit.testing.execute`, `clients.read`, `engagement.accept`, `engagement.accept.prepare`, `engagement.archive`, `engagement.assign`, `engagement.finalize`, `engagements.read`, `engagements.write`, `entities.read`, `independence.declare`, `independence.review`, `jobs.read`, `workingpaper.approve`, `workingpaper.create`, `workingpaper.review`.

## Audit Trainee

`audit.read`, `workingpaper.create`, `audit.testing.execute`, `audit.evidence.upload`, `independence.declare`, `engagements.read`.

## Quality Reviewer

`audit.read`, `engagements.read`, `engagement.quality_review`, `independence.declare`, `workingpaper.review`.

## Read-only Reviewer

`audit.read`, `engagements.read`.

## Firm Operations User

`users.invite`, `audit.read`, `engagements.read`.

## Platform Super Admin

`platform.manage`.

## Platform Support Administrator

`platform.support`.

## Client Administrator

`portal.read`, `portal.respond`.

## Client Finance Manager

`portal.read`, `portal.respond`.

## Client Accountant

`portal.read`, `portal.respond`.

## Client Document Contributor

`portal.read`, `portal.respond`.

## Context restrictions

An active identity, active tenant membership, correct tenant, assignment, access expiry, configured permission, workflow state, current version and independence/separation checks all apply. Role overrides take effect on subsequent requests; frontend menu visibility grants no authority. Client organization grants are explicit.

Full session-management UI, last-login tracking and independent platform operational tooling remain incomplete.
