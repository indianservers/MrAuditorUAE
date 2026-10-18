# Phase 6 role permissions

Permissions are checked against active tenant membership and live engagement assignment, including each group-member engagement. No source is exposed merely because a user knows its UUID.

## Corporate Tax Preparer

`ifrs.read`, `tax.adjustment.propose`, `tax.ai.execute`, `tax.computation.prepare`, `tax.elections.prepare`, `tax.group.manage`, `tax.interest.calculate`, `tax.losses.manage`, `tax.profile.read`, `tax.profile.write`, `tax.qfzp.assess`, `tax.return.prepare`

## Senior Tax Consultant

`ifrs.read`, `tax.adjustment.propose`, `tax.ai.execute`, `tax.computation.prepare`, `tax.elections.prepare`, `tax.group.manage`, `tax.interest.calculate`, `tax.losses.manage`, `tax.profile.read`, `tax.profile.write`, `tax.qfzp.assess`, `tax.return.prepare`

## Tax Manager

`ifrs.read`, `tax.adjustment.approve`, `tax.adjustment.propose`, `tax.ai.execute`, `tax.computation.approve`, `tax.computation.prepare`, `tax.computation.review`, `tax.elections.approve`, `tax.elections.prepare`, `tax.group.manage`, `tax.interest.calculate`, `tax.losses.manage`, `tax.profile.read`, `tax.profile.write`, `tax.qfzp.approve`, `tax.qfzp.assess`, `tax.return.approve`, `tax.return.export`, `tax.return.prepare`, `tax.rules.approve`, `tax.rules.manage`

## Tax Director

`ifrs.read`, `tax.adjustment.approve`, `tax.adjustment.propose`, `tax.ai.execute`, `tax.computation.approve`, `tax.computation.prepare`, `tax.computation.review`, `tax.elections.approve`, `tax.elections.prepare`, `tax.group.manage`, `tax.interest.calculate`, `tax.losses.manage`, `tax.profile.read`, `tax.profile.write`, `tax.qfzp.approve`, `tax.qfzp.assess`, `tax.return.approve`, `tax.return.export`, `tax.return.prepare`, `tax.rules.approve`, `tax.rules.manage`

## Tax Partner

`ifrs.read`, `tax.adjustment.approve`, `tax.adjustment.propose`, `tax.ai.execute`, `tax.computation.approve`, `tax.computation.prepare`, `tax.computation.review`, `tax.elections.approve`, `tax.elections.prepare`, `tax.group.manage`, `tax.interest.calculate`, `tax.losses.manage`, `tax.profile.read`, `tax.profile.write`, `tax.qfzp.approve`, `tax.qfzp.assess`, `tax.return.approve`, `tax.return.export`, `tax.return.prepare`, `tax.rules.approve`, `tax.rules.manage`

## Chartered Accountant

`ifrs.read`, `tax.adjustment.approve`, `tax.adjustment.propose`, `tax.ai.execute`, `tax.computation.approve`, `tax.computation.prepare`, `tax.computation.review`, `tax.elections.approve`, `tax.elections.prepare`, `tax.group.manage`, `tax.interest.calculate`, `tax.losses.manage`, `tax.profile.read`, `tax.profile.write`, `tax.qfzp.approve`, `tax.qfzp.assess`, `tax.return.approve`, `tax.return.export`, `tax.return.prepare`, `tax.rules.approve`, `tax.rules.manage`

## Independent Reviewer

`ifrs.read`, `tax.adjustment.approve`, `tax.computation.approve`, `tax.computation.review`, `tax.profile.read`, `tax.qfzp.approve`

## Client Finance User

`portal.read`, `portal.respond`

## Firm Administrator

`ifrs.read`, `tax.adjustment.approve`, `tax.adjustment.propose`, `tax.ai.execute`, `tax.computation.approve`, `tax.computation.prepare`, `tax.computation.review`, `tax.elections.approve`, `tax.elections.prepare`, `tax.group.manage`, `tax.interest.calculate`, `tax.losses.manage`, `tax.profile.read`, `tax.profile.write`, `tax.qfzp.approve`, `tax.qfzp.assess`, `tax.return.approve`, `tax.return.export`, `tax.return.prepare`, `tax.rules.approve`, `tax.rules.manage`

Final computation/return approvals require Tax Manager then Tax Partner (Tax Director can satisfy either stage; Chartered Accountant satisfies partner). Different independent reviewers are required; preparers and historical editors cannot approve their own work. Independent Reviewer permission alone does not satisfy the named final approval role. Client Finance User receives the existing restricted request/evidence portal; internal tax workpapers and tax exports are not published to clients in this phase.
