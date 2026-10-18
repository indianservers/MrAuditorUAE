# Account mapping

Mappings reference an immutable snapshot through a reporting profile. An account may split across up to 20 statement lines; exact Decimal weights must total one. Duplicate accounts, unknown codes and conflicting definitions for a line are rejected. Section, note, IFRS 18 category, cash flag and working-capital classification are human selected.

Exactly one approved mapping per profile is required at generation. Reopen superseded mappings before approving replacements. Every nonzero opening/current/overlay account must be mapped. Comparative profiles use separate approved mappings and stable presentation line codes; comparative-only lines remain visible. The current editor uses structured JSON for bulk allocations; drag-and-drop mapping is not implemented.
