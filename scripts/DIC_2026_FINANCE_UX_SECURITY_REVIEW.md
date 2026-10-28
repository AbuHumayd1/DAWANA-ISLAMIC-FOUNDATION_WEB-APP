# DIC 2026 Finance UX simplification and Security Dashboard review

Date: 26 October 2026.

## Finance change

Previously, seven top-level sections, seven financial metrics, a large filter form and technical explanations competed for attention. Recording income/expenses required navigating to a subsection and passing its table before reaching a form with required and optional fields mixed together.

The default Overview now emphasizes exactly three figures:

- **Money Received:** existing backend `registration_revenue_kobo` plus `other_income_kobo`, combined only when both are safe integers. Missing/unsafe values display Unavailable rather than invented zeroes.
- **Money Spent:** unchanged backend `expenditure_kobo`.
- **Remaining Balance:** unchanged backend `net_position_kobo`. This remains recorded receipts minus paid expenditure, not a reconciled bank balance.

**Add Money In** and **Record Expense** are visible on the overview, enabled only with the relevant recording and detail permissions. They open the existing income/expense sections and clear transaction filters/page state. The recording form now precedes the list. Required fields have plain labels: category, what it is for, NGN amount, date, payment method, payment/document reference and reason. Optional notes, payee/responsible official and evidence references are under an expandable section. Missing authorized categories disable saving and explain the prerequisite. Saving remains a draft operation, explicitly described as requiring the existing subsequent review/payment steps.

Recent transactions show source, amount, date, status and a link to the original detail panel. Registration rows use backend-verified amounts after adjustments, with unresolved/excluded receipts labelled Not received. Entry rows retain their original amount and workflow status. This is a presentation of existing authorized response rows, not a second ledger. **Limitation:** the current API paginates its source lists; the overview sorts at most ten records from the loaded pages, not a guaranteed globally latest ten. The UI states this and directs operators to the source sections to browse more. No backend pagination semantics were changed.

All seven existing sections remain under **More Finance tools**: Overview, Registration revenue, Other income, Expenses, Budgets, Reconciliation and Reports. Search/filters and technical calculation semantics are collapsed by default. Budget/commitment/payment exception information remains in an expandable overview section. Active filters are identified even when collapsed; figures continue to follow existing filter semantics, while budgets remain edition-wide. Summary-only users do not see transaction rows; unavailable actions remain disabled with a permission explanation.

## Financial safeguards preserved

No backend files changed. The same Finance GET snapshot and existing POST `create`/workflow commands are used, with the selected edition still in the request URL. Online registration payments continue to arrive automatically from trusted backend PaymentAttempt evidence. The manual-income form explicitly tells operators not to re-enter them.

Backend positive exact-kobo validation, approved other-income inclusion, paid-expense inclusion, self-approval denial, separate approval/payment permissions and transitions, evidence requirements, edition/category checks, optimistic versions, locks, audit records, private receipts, reconciliation and exports remain unchanged. Existing action/receipt controls were retained. No new account, grant, financial transaction, database operation, migration or credential change was performed.

## Security Dashboard investigation

No Security Dashboard implementation was found in the available checkout. Searches inspected React application/Operations routes, Django project/DIC routes, dashboard/security filenames and code/documentation references to security dashboards/routes/permissions. `backend/dic/security.py` contains order-access-token hashing/generation/expiry utilities; it is not a dashboard or login implementation.

Consequently, its actual route, login interface, authentication relationship and controlling staff permissions **cannot be established** from this checkout. There is no evidence here supporting a claim of public Security Dashboard exposure, and no verified Security exposure was corrected. A route/file/deployment URL is needed if the dashboard lives in another project, branch or external service. A clarification was requested during the task; no location had been supplied when this report was prepared.

Do not treat the existing `/admin/`, Operations activity log, welfare pages or token utility as an identified Security Dashboard. No new Security page, authentication flow or permission was invented. If a compatible dashboard is subsequently identified, prefer the existing Operations session authentication plus separately authorized Security permissions enforced by its backend endpoints. Operations permission alone must not confer Security access. Any confirmed unauthenticated sensitive endpoint should then be treated as a priority defect.

## Exact files changed

1. `dawana-platform/src/pages/Finance.jsx` — simple overview, permission-aware primary actions, short draft forms, collapsible tools/filters and optional details; retains existing workflows.
2. `dawana-platform/src/pages/Finance.css` — primary-action, disclosure, optional-field and visible-focus styles using the existing Finance design.
3. `dawana-platform/src/services/finance.js` — safe receipt-total presentation and bounded sorting/mapping of loaded transaction rows; original records are retained for details.
4. `dawana-platform/src/services/finance.test.js` — exact receipt aggregation, unavailable/overflow handling and transaction mapping/status/immutability coverage.
5. `dawana-platform/src/services/financePresentation.test.js` — new SSR checks for three figures, permissions/privacy, required form fields and draft messaging.
6. `dawana-platform/src/services/campsiteFoundation.test.js` — replace an obsolete prohibition of the previously approved public Staff Login link with assertions permitting that footer entry while retaining workspace isolation checks. No public-page source changed in this task.
7. `scripts/DIC_2026_FINANCE_UX_SECURITY_REVIEW.md` — this implementation and acceptance record.

## Focused verification executed

```text
node --test src/services/finance.test.js src/services/financePresentation.test.js src/services/campsiteFoundation.test.js
15 passed, 0 failed, 0 skipped

oxlint src/pages/Finance.jsx src/services/finance.js src/services/finance.test.js src/services/financePresentation.test.js src/services/campsiteFoundation.test.js
Exit 0

npm.cmd run build
Passed; existing bundle-size warning, JS approximately 597 kB minified.
```

The first focused run had two failures: an obsolete Staff Login prohibition from the prior entry-point change, and a new test assuming HTML attribute order. The former was aligned with the authorized footer behavior; the latter now verifies required controls independently of attribute order. The final run above passed. No completed backend suite or full frontend suite was repeated.

Test financial values exist only in database-free fixtures for presentation checks. They are not seeded in the application or development database. SSR checks demonstrate rendered markup and utility behavior; they do not execute browser interactions, API mutations or authenticate real staff. Backend safeguards are preserved by leaving backend code unchanged and by the prior confirmed Finance test evidence, not by new backend execution here.

## Browser acceptance checklist — still required

The previously documented Finance API source/runtime mismatch must be resolved using the targeted routing procedure before authenticated acceptance. This UX task does not establish that it has been fixed. Browser tools previously failed initialization; no new browser verification is claimed.

1. With an existing authorized Finance account, load Overview. Verify exactly three main figures against the same backend summary; online income appears without manual entry. Missing data must remain Loading/Unavailable, and a negative remaining balance must remain visible.
2. At 1440px desktop and 390px/360px mobile widths, verify the two primary actions, normal page scrolling, wrapping layout, table horizontal scroll, keyboard focus, expandable tools and Operations hamburger. Check no page scroll lock.
3. Open both primary actions. Confirm the short form appears before records, optional fields expand, no authorized category disables saving, and labels/NGN precision are understandable. **In isolation only**, save a draft, submit it, approve as another official and confirm payment with the separate permitted account. Saving/approval must not mark expenses paid; own approval must fail. Do not perform these actions in `dawana_dev`.
4. Use a summary-only account: no recent transaction details, no enabled recording controls. A creator-only or approver-only account must not gain the other's actions. Direct API permission enforcement remains subject to the existing backend matrix acceptance procedure; button state alone is not security evidence.
5. Confirm recent rows show source/date/status and adjusted verified online amounts, detail opens the original row, and the loaded-page limitation is visible. Test unpaid/draft/reversed statuses without interpreting them as cash totals.
6. Open every secondary section. Confirm existing submission/approval/payment controls, receipt attachment/download, budget revisions, reconciliation and CSV reports remain available only under their existing permissions. **Downloads/exports and all writes must use isolation**, since successful Finance downloads/exports also write audit events.
7. Apply/clear filters, switch editions and simulate delayed/failed metadata/data requests. Confirm active-filter indication, no stale edition detail/totals, loading/error/Retry recovery and success notices after isolated successful actions. Do not retry a lost-response financial write without checking current record state.

Finance is **not declared production-ready** by this simplification. Runtime routing, authenticated browser acceptance and the prior download/permission/reconciliation gaps remain separate gates. Security Dashboard review remains incomplete pending its actual location.
