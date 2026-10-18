# Browser visual audit

The 27 PNG screenshots in `screenshots/` are actual renders from the local application against the real Phase 4 API and a separate synthetic PostgreSQL database. `screenshot-inventory.json` maps every image to its route and purpose, including all 24 new routes plus mobile/history/denial variants.

The existing Phase 3 shell, typography, white surfaces, restrained blue/teal accents, compact grids, badges and query/error patterns were reused. Reference images for client management, risk investigation, engagement workspace and Copilot were inspected. No screenshot was cropped into an interface asset; no generated page artwork was used.

Browser QA found and fixed a missing BFF route allowlist entry and zero-height AG Grid containers. The verification then exercised actual record selection, structured preparation, submission, manager/partner approval, history, client upload/response and API denial of internal client access.

The layout has horizontally scrollable workspace tabs, resizable inspector panels and a stacked mobile workspace. Some long forms still require inspector scrolling. Source selectors and assertion controls avoid raw JSON for common links/assertions; advanced methodology, financial tables and test results still need richer editing affordances. Accessible labels are present, but a complete Phase 4 accessibility audit was not performed.

The three final Playwright scenarios pass. Production compilation passes; the optional additional production server could not be started because automatic approval review returned “blocked by policy.” Screenshots and browser claims therefore apply to the development preview, not a deployed production environment.
