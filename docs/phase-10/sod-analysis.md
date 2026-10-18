# Segregation of duties

SoD evaluates incompatible ERP permission pairs for the same principal and same entity/system scope, using access validity windows at a stated assessment date. Application roles are not inferred as ERP permissions. Expired permissions and different scopes do not create conflicts. Compensating-control verification remains a separate professional assessment.

Manual typed populations and bounded CSV import are available. CSV columns are principal, permission, scope, valid_from and optional valid_to; maximum 4 MiB and 10,000 rows. Imported content must match the latest clean, independently approved evidence version by SHA-256. Duplicate assignments, invalid dates and unknown columns are rejected. There is no live ERP directory connector or automatic access revocation.
