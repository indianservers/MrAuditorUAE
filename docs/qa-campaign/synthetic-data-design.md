# Synthetic business and lineage

25 fictional companies span 17 industry categories, mainland/free-zone/foreign jurisdictions. Five explicit ownership relationships include parent/subsidiaries and 50%JV. Industry is a fixture attribute/name; first-class client industry fields are not implemented.

61 configured professional role users plus separately provisioned MFA operator; temporary load users are disabled after benchmark. Identifiers and domains are fictional.

Deterministic 18 transaction families, balanced two-leg journals, immutable imports/source row SHA256 lineage, actual ledger-derived TB. Stages use separate entity/year snapshots; they are not overlapping replacement snapshots. Journal currencies are AED; foreign FX metadata is not broadly populated.

20 exception labels are stored separately in exception-labels.json before detector execution. No final audit findings are inserted by the QA generator; analytics creates its own persisted findings.
