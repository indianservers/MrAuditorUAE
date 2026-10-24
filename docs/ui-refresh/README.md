# Audit experience refresh

Implemented against the supplied competitor screenshots on 24 October 2026. Those images are visual references, not verified evidence of the competitor's complete functionality. No competitor branding, company data or undocumented claims were copied into application records.

## Delivered

- `/engagements`: responsive portfolio cards, retained financial-grid table view, server-backed name search, status filtering and pagination; each card opens the actual engagement workspace. Permission-gated creation is available directly from the portfolio.
- Three-step creation: saved legal entity, actual entity-specific financial period and scope, then review/confirmation. Successful creation uses the existing authorized API and opens the resulting engagement. Selection changes invalidate the previous period. Missing periods and backend errors are explicit. Creating an engagement grants no new permissions and approves no reporting context.
- `/engagements/{id}/workspace`: eight clickable audit stages, current reviewed record counts, stale-source states, attention filtering, an actionable blocker panel, team access and the existing functional dependency graph. State derives from authorized workspace records. Empty views do not establish that all required work is absent or complete; bounded populations are labelled. Record review is distinct from an approved opinion.
- Dashboard now leads directly to the audit portfolio and the existing country compliance workspace; removed obsolete copy claiming tax services were a future phase.
- Responsive layouts, keyboard focus outlines, labelled form controls and reduced-motion styling.

## Important distinctions

Saved company data is labelled as a firm record. No GSTIN/CIN registry verification service or live external enrichment was invented. Country/framework selection and independent approval remain in the existing reporting-context workflow. Team assignment, connector setup and accounting import use their existing controlled workspaces after creation. No approved history or financial computation was changed. The entire application has not undergone a visual redesign in this change.

## Validation

Frontend unit/component suite: 37 tests passed at the recorded run (12 files). New test proves a stale approved working paper remains in attention while a current reviewed risk record is filtered out, and the next action links to the actual blocker. Browser test creates a real synthetic engagement, exercises card/table navigation, required-field gates, period selection, review/creation, audit journey, attention filter and reviewer navigation. A narrow viewport check is included. Browser receipts and screenshots are in this directory. Final verification: browser flow passed (5.2 seconds), including the 780px viewport bound check. TypeScript, ESLint and the isolated Next.js production build passed.

No commit, push or deployment is included. Existing concurrent changes in this shared workspace were preserved.
