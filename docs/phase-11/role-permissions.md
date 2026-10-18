# Authorization and role grants

Existing professional roles with audit.read receive investigation/read/run/proposal/index permissions. Roles with workingpaper.approve also receive AI review/schedule/usage/audit-log/evaluation/knowledge permissions. Firm Administrator receives AI technical configuration. AI Administrator receives technical administration and usage/evaluation/audit-log permission names but no automatic engagement or professional source access. Platform Administrator receives no confidential data grants.

Effective rights still come from active engagement grants and tenant role-policy overrides. Resource services recheck permissions even if a caller constructs a Context with forged permission bits. Client roles are not automatically granted investigation tools. Board and narrow GRC owner roles remain limited. Investigations are private to their initiator. Reviewers independently require source and approval permissions. No credentials or hidden prompt content is exposed in metadata APIs.

Migration 0011 freezes schema/grants; runtime ROLE_PERMISSIONS provisions future installations. Inspect role-permissions.json and OpenAPI for exact current contracts. Provider inventory has its own ai.provider.manage dependency so technical administration need not be granted investigation read.
