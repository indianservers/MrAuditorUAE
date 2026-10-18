# Accessibility audit

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Automated axe evidence: accessibility-results.json (6 page/viewport observations). Login is checked at 1920x1080, 1600x900, 1440x900, 1366x768 and 390x844, plus security enrollment and keyboard tab focus. Existing regression exercises rich financial/GRC/AI views at additional tablet/desktop widths. Login contrast and mobile form overflow defects were fixed.

Target: WCAG 2.2 AA. Scope is sampled automated/keyboard verification, not a complete manual assessment or conformance declaration. Full primary route, screen reader, chart alternatives, 400% zoom, dialog focus and dense-grid keyboard audit remain acceptance work. Failure screenshots are retained by Playwright; final screenshots live in screenshots/. See defect register rather than interpreting an absent automated finding as complete accessibility.
