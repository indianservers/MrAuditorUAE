# Output Vat Engine

Decimal calculations use64-digit local precision and HALF_UP2-decimal AED rounding. Exclusive and inclusive consideration, discounts, original-currency FX conversion and credit-note reversal are supported. Tax is calculated from the unrounded AED net to avoid double-rounding drift. Declared AED values are independently compared with calculated net, VAT and gross.

Human-selected treatments: standard, zero, exempt, outside, reverse-charge services, customs goods imports, deemed supply and unresolved. Standard/deemed/reverse/import use the approved5% rule; zero/exempt/outside do not become taxed merely because an account name matches. Source facts include supply/issue/tax-point dates and basis, place-of-supply completeness, jurisdictions, customer registration, related-party indicator and partial payments. These indicators do not automatically establish a legal treatment or recalculate a payment-based tax point.

Exports, real estate, transport, designated zones, related-party valuation, vouchers and sector-specific place-of-supply qualifications require reviewed classification/evidence. Credit notes currently reference an approved original in the same engagement/profile and direction; prior-period originals require a supported workflow extension rather than an invented reference.
