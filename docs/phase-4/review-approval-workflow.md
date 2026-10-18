# Review and approval

Engagement policies configure role chains, with Audit Manager then Audit Partner as the default paper/planning/program/testing chain. Approval requires live engagement permission, current status, expected version, matching chain stage and separation from all preserved preparers. The same reviewer cannot satisfy multiple stages in one cycle.

Every action stores actor, timestamp, target document version, stage, decision, comments and prior status. Review decisions, record revisions and evidence versions have database mutation-rejection triggers. Duplicate/stale approvals are rejected by locks, workflow state, versions and unique constraints.

Open notes block approval. Staff can resolve a note; the assigned reviewer clears it. An authorized independent reviewer can return/reopen approved work with a recorded reason. The approved version remains in history. Completion checks reject outstanding documents and unresolved findings; accepted-unresolved findings require an independent recorded resolution path before closure.

Testing approval checks that every selected sampling item has a documented outcome, observations and reviewed supporting evidence. It rejects duplicate or out-of-population test items. Selection and professional assurance conclusions remain separate.

Human actions through test clients are explicit test decisions, not production audit approvals. AI suggestions have no authority to sign, approve, close findings or issue an opinion.
