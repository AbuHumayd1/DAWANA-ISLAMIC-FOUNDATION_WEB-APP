# DIC 2026 Finance dashboard and permissions verification

Date: 26 October 2026.

## Decision

**Final acceptance recommendation: Not ready.** The running local backend returns HTML 404 for the Finance endpoint even though this checkout registers it. Browser automation cannot initialize, and no authenticated Finance HTTP matrix or receipt/CSV acceptance could be completed. Controlled acceptance testing may continue after the environment blockers below are resolved; this is not approval for real financial operations.

The user's current evidence supersedes the older preparation documents: 19 Finance policy tests and four PostgreSQL integration tests passed; Finance migration 0001 is applied to `dawana_dev`; dic 0027 remains unapplied. Those results were supplied by the user, not rerun during this verification.

## Dashboard integration

Code inspection confirms Finance under Operations → Finance & Reports at `/dic/operations/finance`, guarded by Operations/campsite and Finance access. It renders inside the existing portal shell. The seven sections cover overview, registration revenue, other income, expenses, budgets, reconciliation and reports.

Overview uses backend totals for verified registration receipts, approved other income, paid expenses, approved unpaid commitments, latest budget allocations, remaining budget and recorded net position. It explicitly distinguishes this position from a reconciled bank balance. No seeded transactions, synthetic balances or hardcoded financial amounts were found in the Finance page or services. Missing amounts display as unavailable; successful empty snapshots can legitimately show zero.

Loading, empty tables, errors, retry, action confirmation and success notices exist. Inspection found that initial metadata failure could not recover: Retry incremented the dashboard revision while the failed metadata effect ran only on mount, leaving no edition to load. The correction adds an independent metadata retry revision, initial loading and no-edition states. Edition changes now also clear old detail, errors and success notices. No backend behavior changed.

CSS provides wrapping navigation, adaptive forms/metrics, horizontally scrollable tables and stacked details below 480px. These are inspected responsive rules, **not a completed desktop/mobile browser or scrolling pass**. Runtime retry recovery and mutation success/error states still require browser acceptance.

## Authorization

Inspected `FinanceView`, Finance services/models, Operations session permission/base view, session metadata, route and navigation guards:

- Every Finance request requires authenticated, active staff with Operations and Finance permissions before Finance table inspection. Hiding navigation is not the enforcement mechanism.
- Summary access does not imply detail or mutation access. Transaction lists, budgets and revision details are removed from summary-only responses. Aggregate totals and category metadata remain available to Finance viewers by design.
- Separate backend permissions govern income recording, expense submission, approval, payment confirmation, budgets/categories, reconciliation, details and export. CSV requires both export and detail authority; receipts require detail authority.
- Approval rejects the entry creator, including a superuser. Approval moves submitted → approved; payment is a separate approved → paid expense transition with payment-confirmation authority and supporting evidence.
- Mutations use transactions, edition/entry locks, version checks and audit records. Session authentication enforces CSRF for unsafe requests; responses enforce no-store headers.
- No Finance code automatically assigns roles or grants permissions; models suppress default CRUD permissions. No assignments were changed or queried in this task.

These findings establish the intended backend rules by inspection. The supplied policy tests cover base/action permission denial, anonymous API denial and self-approval; the supplied integration tests cover unauthorized/stale mutation rejection. They do not establish a full authenticated HTTP role matrix or confirm actual named staff grants. Current grants, permission availability following the previously applied migration and deployed session behavior require authorized read-only/manual verification.

## Workflow findings

| Workflow | Inspection result | Runtime evidence / remaining gap |
| --- | --- | --- |
| Registration income | Requires successful verified NGN provider evidence, expected/reported amounts, provider ID, accepted price revision, valid payment timing and paid confirmed order. Pending/failed/inconsistent attempts do not credit receipts. Order/provider deduplication and documented adjustment handling exist. | Supplied policy passes; independent provider/bank comparison and complete refund scenarios remain manual. No Paystack calls made. |
| Other income | Edition/category scoped, positive exact kobo, draft/submitted/approved states. Only approved income counts. Known registration references are rejected. | Supplied policy evidence for totals; complete HTTP/browser workflow remains untested here. Honest source classification and evidence review remain operational responsibilities. |
| Expenses | Draft → submitted → approved → paid. Self-approval denied; approval alone has no cash effect. Evidence is required before payment confirmation. Cancellation/reversal retain originals and audits. | Supplied policy and persisted integration passes; no new transactions created. Payment evidence must be supplied when creating the draft or by attaching a receipt while it is still a draft; there is no general edit endpoint. |
| Budgets | Latest revision replaces prior allocation; edition-wide paid spending determines actual/remaining values. Budget allocations do not reduce cash. | Supplied budget integration pass; UI revision acceptance remains manual. |
| Reconciliation | Append-only evidence scoped to an edition's existing attempt. Matching cannot manufacture verification; cumulative refund/reversal amounts cannot exceed the original charge. No provider transaction is initiated. | Supplied adjustment policy evidence; real statement matching and full reconciliation endpoint acceptance outstanding. |
| Reports/CSV | Same snapshot calculations as dashboard; explicit export/detail permissions, UTF-8 BOM, shared spreadsheet-formula escaping, 5,000-row limit and audit. | Frontend utility checks and supplied escaping policy evidence; actual CSV response/download and independent total comparison outstanding. |
| Private receipts | Database bytes, no public media URL; draft creator attachment rule; PDF/PNG/JPEG signature and 2 MB check; edition-scoped authorized attachment downloads with audit and nosniff. | Inspected only; upload/download, cross-edition denial and audit acceptance require isolated testing. No malware scanner is implemented. |

Amounts are calculated as integer kobo using Decimal input validation. Relationships and Finance queries/commands scope records to the selected edition. Date/search/status filters affect their respective transaction sources; budgets remain edition-wide. Registration category selects whole matching bookings rather than allocating booking revenue. These semantics must be observed when comparing reports.

Existing general Operations payment/report pages remain separate from the new Finance calculations and use older definitions. This verification does not certify those legacy reports as interchangeable with Finance reports.

## Previous focused verification: executed checks

From `dawana-platform`:

```text
node --test src/services/finance.test.js src/services/campsiteFoundation.test.js src/services/operationsRefinement.test.js
17 passed; 0 failed; 0 skipped

.\node_modules\.bin\oxlint.cmd src/pages/Finance.jsx
Exit 0

npm.cmd run build
Passed; Vite emitted a bundle-size warning (approximately 593 kB JS).
```

The frontend checks cover Finance utility/workflow permission choices, restricted navigation, grouping, initial server rendering and existing portal integration assertions. Server rendering does not run React effects or validate interactive loading/retry, uploads, downloads or scrolling.

The backend Python version probe failed because the virtual environment's configured Python313 executable was inaccessible. No backend tests or database reads were executed in this task. The confirmed previous 19+4 passes were not repeated. No full backend/frontend suite was run.

## Files changed during previous focused verification

1. `dawana-platform/src/pages/Finance.jsx`: recover initial metadata failures; display metadata loading/empty states; clear stale edition detail/messages.
2. `scripts/DIC_2026_FINANCE_DASHBOARD_VERIFICATION.md`: this evidence and acceptance report.

The workspace contained many pre-existing modified/untracked files. Those changes are not attributed to this task. No migrations, credentials, staff grants or existing financial records were changed. No development database fixtures, transactions, payment requests or unrelated modules were started.

## Previous acceptance outline

1. In the existing approved environment, use a named authorized staff account to inspect Finance, confirm the selected camp edition and compare read-only displayed totals with approved source records. Do not execute mutations in `dawana_dev` for acceptance.
2. Check desktop and narrow mobile viewports: sidebar route, all sections, page and table scrolling, detail panels, keyboard navigation, initial loading, empty responses and retry after an intercepted metadata/dashboard failure. Use request interception or a separate mock environment for failure simulation.
3. Review existing named grants without changing them. In an isolated environment, exercise direct HTTP requests as anonymous, non-Finance staff, summary-only, detail-only and each single-action role. Include exports, receipts, CSRF failure, self-approval and cross-edition identifiers.
4. If synthetic records are needed, use a separately approved disposable PostgreSQL database and the constrained isolation procedure in `DIC_2026_FINANCE_VALIDATION_PROCEDURE.md`. Extend acceptance there for income, receipts, CSV, reconciliation, stale/concurrent requests and separate submitter/approver/payment confirmer accounts. Do not use development as a test database or invoke unrestricted migration/test commands. This task did not execute that procedure or authorize new migrations.
5. Compare exported/report totals and rounding to independently calculated expected kobo. Agree named officers, authorized categories/budgets, evidence retention and reconciliation responsibilities before real operation.

The existing passed tests and successful schema application are useful evidence, but do not replace these acceptance checks.

## Final acceptance attempt — 26 October 2026

### Executed evidence and outcome

Evidence: `output/acceptance/finance-final/anonymous-http.json`. Response bodies, cookies and credentials were not retained. Edition identifiers 1 and 2 were probe values, not confirmed editions or authorization scopes.

| Check executed | Actual result | Acceptance interpretation |
| --- | --- | --- |
| Browser-use initialization | Kernel-assets failure: `The system cannot find the path specified. (os error 3)` | Zero UI scenarios executed. |
| Computer-use skill initialization through `@oai/sky` | Same kernel-assets failure | No desktop/mobile rendering, navigation or scrolling pass. |
| Backend virtual-environment Python version probe | Configured Python313 executable inaccessible / access denied | No new backend tests, database connections or fixtures. |
| 24 anonymous Finance GET probes: metadata, editions, malformed edition, receipt identifiers and all six CSV choices, direct port 8000 and proxy port 5173 | Initial batch: 13 HTML 404 responses, nine proxy 502 responses and two connection refusals | **0/24 met expected Finance authorization denial.** These are routing/availability blockers, not evidence that Finance permissions were evaluated or bypassed. |
| Follow-up direct `GET /api/v1/dic/operations/auth/me/` | 403 JSON, only `detail`, `Cache-Control: no-store`, `Pragma: no-cache` | PASS for the anonymous Operations authentication control only. |
| Follow-up Finance metadata GET, direct and proxy | Both 404 `text/html; charset=utf-8` | Finance endpoint still unavailable. Source/runtime mismatch remains unresolved. |
| `GET http://127.0.0.1:5173/dic/operations/finance` | 200 HTML containing Vite SPA shell | Frontend document reachable; **not** proof of route authorization, React rendering or Finance data loading. |

The source route is present in `backend/dic/urls.py` and included at `api/v1/dic/` by `backend/config/urls.py`. A stale server, a different checkout or a different process/configuration could explain the runtime 404; none has been established as the cause. No speculative source correction or service restart was performed. An operator must identify the process/checkout serving port 8000 and run the current code through the existing approved local startup procedure. **Do not run migrations to fix this route mismatch.** Recheck that an anonymous Finance metadata request returns JSON 403 before accepting later permission results. A missing route returning 404 does not count as an access-control pass.

The previously confirmed 19 policy, four PostgreSQL integration and 17 focused frontend passes, lint and build remain prior evidence. No completed suite was repeated. No application source changed in this final acceptance attempt, so no new lint/build run was needed. No new implementation defect was established or corrected; the prior Retry/stale-state correction remains pending interactive acceptance.

### Complete permission matrix: expected by inspection, HTTP execution blocked

All authorized rows require an authenticated, active staff account with both `dic.can_view_dic_operations` and `dic.can_view_dic_finance`. Action permissions below are under `dic_finance` and independent. Labels describe explicit test permission sets, not existing named roles or automatic grants. No real user's grants were inspected or changed.

| Isolated test persona | Additional permissions | Expected Finance direct API behavior |
| --- | --- | --- |
| Unauthenticated | None | GET metadata/dashboard/receipt/export and POST actions: 403 with current SessionAuthentication configuration; no financial payload or mutation. Current Finance route did not reach this check. |
| Non-Finance staff | Operations only | All Finance GET/POST: 403. Also check inactive/nonstaff users and Finance without Operations: denied. |
| Finance summary viewer | None | Metadata/dashboard 200 JSON; summary and categories permitted; payments, entries, budgets and budget history empty; all POST actions, receipts and exports denied. |
| Finance detail viewer | `can_view_details_finance` | Detail lists and existing receipt GET permitted; mutation and CSV denied without their respective permissions. |
| Entry creator: income | `can_record_income_finance` | Income create/submit and own-draft receipt attachment allowed; expense create, approve, pay, budget, reconciliation and export denied. |
| Entry creator: expense | `can_submit_expense_finance` | Expense create/submit and own-draft receipt attachment allowed; income create, approve, pay, budget, reconciliation and export denied. |
| Approver | `can_approve_finance` | Approve another official's submitted entry; reject/cancel only in allowed states; own-entry approval 403; pay/create/budget/reconcile/export denied. |
| Payment recorder | `can_confirm_payment_finance` | Pay an approved expense with supporting evidence; no approval, creation, budget, reconciliation or export. Submitted expense and income payment attempts rejected with 400. |
| Budget manager | `can_manage_budget_finance` | Category creation and budget revision permitted; other actions remain denied. This permission alone is not a Finance administrator. |
| Reconciler | `can_reconcile_finance` | Reconciliation and allowed entry reversal permitted; approve/pay/create/budget/export remain denied. |
| Exporter | `can_export_finance` | Export still 403 without detail permission; adding detail permits supported CSV exports, not mutations. |
| Finance administrator test persona | All eight explicit Finance permissions | All valid workflows permitted; self-approval, invalid states, wrong-edition IDs and stale versions still rejected. Superuser self-approval must also fail. |

For UI workflow checks, add detail permission to the creator/approver/payment/budget/reconciler test personas explicitly **in isolation only**; the current UI nests workflow controls under detail access. Backend action authorization does not require detail authority. Verify single-action backend permissions independently before using these combined UI personas.

Direct HTTP acceptance steps, **not executed**:

1. Use existing approved isolated accounts or a separately provisioned disposable environment. Do not create users, grants or records in `dawana_dev`. No verified reusable authenticated fixture/disposable facility was available to this attempt; the inaccessible interpreter also prevents safely running the constrained helper here. The user prohibits migrations in this task, so do not invoke that helper's schema-creating integration action. Any new disposable provisioning/migration needs a separate approved run.
2. Log in normally as each persona. Use a fresh session per persona, verify `/operations/auth/me/`, and use the same origin's `/operations/auth/csrf/` token for POSTs. Capture status, response shape and audit deltas in the isolated environment. Do not mistake a CSRF 403 for an action-permission denial: first demonstrate a valid-CSRF allowed request for the persona.
3. Let `A`/`B` be two actual disposable edition primary keys, `E` an entry UUID and `P` a payment-attempt ID from A. Call `GET /api/v1/dic/operations/finance/?edition=A`, `?metadata=1`, `?edition=A&receipt=E` and every `?edition=A&export=registration|income|expenses|budgets|reconciliation|summary` independently of visible buttons. Use `export=unknown`, an unknown edition and a valid but absent receipt UUID too.
4. POST JSON directly to `.../finance/?edition=A` with valid isolated payloads: `category`, `create`, `submit`, `approve`, `pay`, `reject`, `cancel`, `reverse`, `budget`, `reconcile`; test multipart `receipt` separately. Expected allowed command response is 201 JSON. Permission denials must be 403; validly authorized invalid workflow/version/input requests must be 400. A missing CSRF token must fail. Each denied request must leave entries, revisions, reconciliation and audit unchanged.
5. Replay A's category, entry, attempt and receipt identifiers against B. No A data may be returned or changed. Missing/wrong-edition receipts and command identifiers currently return 400 JSON by design, not 404. Assert no audit event for a rejected download/action. This does not assert per-user edition restrictions: authorized Finance staff can choose editions; the enforced boundary is consistency with the requested edition.

### Minimal browser checklist — not executed

Use `http://127.0.0.1:5173/dic/operations/finance` after the runtime route is fixed. Use an approved existing Finance session for read-only development views; use an isolated environment with intercepted requests for all failure/mutation scenarios. No successful download/export or mutation should be performed against development during this acceptance, because those downloads also write audit events.

| Step | Exact action | Expected result |
| --- | --- | --- |
| Route and sidebar | Log in normally, choose Finance under Finance & Reports, then reload the URL; repeat anonymously and as non-Finance staff in separate sessions. | Authorized Finance renders inside Operations; unauthorized users get login/access-required UI and direct API denial; no financial content appears. |
| Initial loading | In DevTools Network, disable cache, use Slow 3G and reload. | Loading status while metadata/data are pending; no invented zero balances before the snapshot. |
| Metadata Retry | Before reload, block `*finance/?metadata=1*` in DevTools Request Blocking; reload, wait for the error, unblock, click Retry. | Metadata is requested again, edition options load and the snapshot follows; error clears. |
| Dashboard Retry | Block only the selected edition's dashboard GET, reload, wait for error, unblock and click Retry. | Data request repeats; a successful response clears error and renders the correct edition. |
| Edition switch/race | With two isolated editions having different known totals, throttle requests, open A detail and switch A → B → A rapidly. | Old totals/detail disappear while loading; final response and totals belong to the final selected edition, even if an earlier response arrives late. |
| Empty states | In isolated interception, return `{ "editions": [] }` for metadata; then use an edition with no transactions. | No-edition message in the first case; genuine zero totals/empty tables in the second; no fabricated transactions. |
| Seven sections | Open Overview, Registration revenue, Other income, Expenses, Budgets, Reconciliation, Reports; open/close available details and use table pagination/filter controls. | Correct section, permission-gated controls, totals and empty states; no hidden stale detail or console errors. |
| Desktop/mobile | At 1440×900, 390×844 and 360×800, open/close hamburger, choose Finance, visit each section, scroll page down/up and each wide table left/right; use Tab to reach controls. | Menu opens/closes normally; content remains reachable, no page scroll lock, forms/buttons fit, table overflow stays within its scroll region and keyboard focus is visible. |
| Success/failure | **Isolated only:** submit a valid draft, approve as a different official, record payment with its authorized persona; then intercept a POST with 400/500 and retry after restoring service. | Confirmation precedes action; successful notice and refreshed data; failures produce an error without a success notice or duplicate write. Retrying a lost-response mutation must verify current state first. |

### Receipt and CSV acceptance — inspected expectations, execution blocked

- Existing authorized receipt: 200 `application/octet-stream`, attachment filename with PDF/PNG/JPEG extension, `X-Content-Type-Options: nosniff`, no-store/no-cache; compare bytes to the isolated upload. Octet-stream is intentional, not an inline PDF/image content type. Detail permission is mandatory; own-draft creation permission is additionally required for upload. Test other creator, submitted draft, oversize and invalid signature uploads: denied/400 with no change. Missing/invalid/wrong-edition UUID or entry without bytes: 400 JSON. Unauthorized access: 403 before private bytes. Successful downloads create audit events, so do not test them on development.
- Each supported CSV: 200 `text/csv; charset=utf-8`, attachment filename containing edition/report, UTF-8 BOM bytes `EF BB BF`; parse with a CSV parser rather than splitting on commas. All nonempty rows must belong to the selected edition. Empty reports contain the no-matching-records header, not invented transactions; unknown reports return 400. More than 5,000 matching rows must return 400 rather than silently truncate. Exports write an audit event and require both detail and export permission.
- **Isolated only:** use text cells beginning with `=`, `+`, `-`, `@`, tab, CR/LF and leading whitespace before `=`; exported top-level cells must have a leading apostrophe. Include quotes, commas, line breaks and Unicode, and confirm round-trip content. Existing shared escaping policy passes are prior evidence; actual response-byte/Excel behavior was not executed here. Negative monetary CSV values are also escaped by the shared formatter; strip only the protective apostrophe when independently comparing integer kobo.
- For unchanged filters, compare dashboard summary to summary CSV, and source-row kobo sums to each report. CSV uses the full filtered snapshot rather than the visible 50-row page. Budgets always compare edition-wide paid actuals; registration category includes whole matching bookings. Use Finance reports for this comparison, not legacy Operations reports with different definitions.

### Minimal isolated reconciliation oracle — not executed

Use an already approved disposable schema, never development; do not contact Paystack. Fixture evidence must be synthetic and clearly isolated. Exact expected values below are test inputs, not real financial figures:

1. A trusted original charge of 10,000 kobo plus a duplicate of the same order/provider ID must credit 10,000 once. Pending/failed/unverified attempts credit zero. A cancelled/refunded order lacking trusted original evidence credits zero. An unresolved exception on the trusted receipt holds it out of received revenue.
2. Document a 2,000-kobo refund of that charge: received registration revenue becomes 8,000. A further documented 8,000-kobo reversal brings it to zero; adjustments exceeding the original charge must fail. A later matched note must not erase adjustment history or manufacture successful provider evidence.
3. With registration at 8,000, approved other income 3,000, submitted income 9,000, paid expense 2,000, approved unpaid expense 5,000 and category budget revisions 20,000 then 15,000: expect other income 3,000, expenditure 2,000, unpaid commitments 5,000, approved budget 15,000, remaining budget 13,000 and net position 9,000. Budgets and unpaid commitments must not reduce cash. Keep all rows in A and the expense under that budget category; seed B with different values to check isolation.
4. Capture entry/reconciliation/budget/audit rows before and after each isolated action. Assert immutable revision/evidence history, retained reversed entries, version increments, audit attribution, and unchanged PaymentAttempt/order settlement fields. An exception or refund must remain explained in the detail/export rather than silently changing source history. Concurrent/stale requests must not produce duplicate writes. Compare integer totals independently with the oracle, not by calling the same snapshot service twice.

### Final scope, files and blockers

Files changed **in this final acceptance attempt**:

1. `scripts/DIC_2026_FINANCE_DASHBOARD_VERIFICATION.md` — final recommendation, runtime findings, permission matrix and exact remaining manual procedures.
2. `output/acceptance/finance-final/anonymous-http.json` — anonymous GET results, follow-up controls and tooling failures; no financial payloads or credentials retained.

No application files changed in this attempt. The previous `Finance.jsx` correction is listed separately above. No suites were repeated, no server was started/restarted, no schema was migrated, no database transactions/fixtures/grants were intentionally created, and no provider payments were initiated. No authenticated export/download was attempted. Comprehensive Reporting was not started.

**Operational blockers:** (1) local Finance source/runtime route mismatch and intermittent backend availability; (2) browser automation kernel unavailable, with interactive checklist outstanding; (3) inaccessible backend interpreter and no verified authenticated isolated fixture facility for the complete HTTP matrix; (4) authorized receipt/CSV status, encoding, bytes, scoping, totals and audit acceptance outstanding; (5) isolated reconciliation oracle and independent bank/provider comparison outstanding; (6) named Finance officers, existing grants, evidence retention and operational reconciliation responsibilities still require owner confirmation without automatic permission changes.

**Recommendation: Not ready for operational use.** Existing automated passes support continued acceptance work, but the current local setup cannot serve the Finance API, and the remaining authorization/download/browser checks have not passed. Reclassify to Ready for controlled internal use only after the above environment and acceptance gates are satisfied and recorded. No production-readiness claim is made.

## Targeted routing/reachability diagnosis — 26 October 2026

### Exact request path and 404 origin

Failing method: **GET**. Minimal failing URLs from the recorded evidence:

```text
http://127.0.0.1:8000/api/v1/dic/operations/finance/?metadata=1
http://127.0.0.1:5173/api/v1/dic/operations/finance/?metadata=1
```

The same path with `?edition=1` also failed in the previous evidence. No request requires anonymous HTTP 200; the correct anonymous routing result with current session authentication is JSON 403.

Source trace:

1. `dawana-platform/src/services/operationsApi.js`: API base is `VITE_API_BASE_URL` or `/api/v1`; Operations appends `/dic/operations`.
2. `Finance.jsx` metadata request appends `/finance/?metadata=1`; `services/finance.js` constructs `/finance/?edition=...`. The combined URL is correct and includes the trailing slash.
3. `dawana-platform/vite.config.js`: `/api` forwards without path rewrite to `DJANGO_API_PROXY_TARGET` or `http://127.0.0.1:8000`. The existing `start-local-preview.ps1` explicitly sets `/api/v1` and backend port 8000 in the child process. No project `.env` override for these values was found by the scoped search; existing running process environment could not be inspected.
4. `backend/config/urls.py`: `api/v1/dic/` includes `dic.urls`.
5. `backend/dic/urls.py`: `operations/finance/` maps to `dic_finance.api.FinanceView.as_view()`, name `operations-finance`.
6. `FinanceView.initial()` first applies Operations/session authentication and Finance permissions. Metadata skips Finance table inspection only after authorization; it is a suitable anonymous routing probe without financial database access.

**Confirmed 404 origin: Django's URL resolver on port 8000.** The newly inspected response has server header `WSGIServer/0.2 CPython/3.13.7`, title `Page not found at /api/v1/dic/operations/finance/`, and names URLconf `config.urls`. Its enumerated runtime patterns include Operations authentication but **do not include `operations-finance`**. Through port 5173 the same Django response and route-pattern facts are returned. This is not Vite's SPA fallback or a Finance permission rejection. Proxy transport works for the probes now observed.

**Established cause at the routing layer:** the loaded backend URL table lacks the Finance route that exists in this checkout. A stale imported URLconf or a server running another source copy is the likely operational explanation; exact process command line/import path has not been established. Do not describe either explanation as proven. Adding a second URL pattern or changing the proxy prefix is not supported by this evidence.

### Service reachability findings

- `netstat -ano -p tcp` observed `127.0.0.1:8000` listening with PID 9408 and `127.0.0.1:5173` with PID 23428 during this diagnosis. These are point-in-time observations, not safe future termination targets.
- Saved `.local-preview/servers.json` identifies backend launcher 29184 and frontend 23428, with logs rooted in this checkout. The manifest is historical; listener ancestry could not be verified. It is not sufficient evidence to kill a process.
- `Get-CimInstance Win32_Process` returns access denied in Codex; `Get-NetTCPConnection` does not supply usable results here. The configured virtual environment cannot execute its base Python313 interpreter. No processes were stopped or restarted.
- The saved backend log shows StatReloader activity in this checkout before the Finance source timestamps. This supports investigating stale serving code but does not prove current listener identity. No retained log evidence was found establishing the precise reason for the earlier temporary loss of service.
- Earlier **direct** port-8000 `ECONNREFUSED` means no connection was accepted at that address during those probes. The accompanying proxy 502 responses are consistent with upstream unavailability. This is distinct from Django HTML 404 (reachable backend with missing runtime route) and JSON 403 (reachable authorization handler). The exact initiating event—restart, crash, listener replacement or another interruption—remains unconfirmed. There is no evidence justifying a port change.

### Newly executed focused HTTP check

Command from repository root:

```powershell
node .\scripts\check-finance-routing.mjs
```

Evidence: `output/acceptance/finance-routing/routing-2026-10-26T13-25-28-430Z.json`.

The new helper performs three sequential rounds of anonymous GET requests to Finance metadata and Operations auth/me, directly and through Vite. It accepts only loopback HTTP origins, sends no credentials, saves no response bodies, follows no redirects, and exits nonzero unless every response is JSON 401/403 with only a detail field and no-store/no-cache. Timestamped results preserve each attempt. Optional arguments are backend origin then frontend origin; defaults are ports 8000 and 5173.

| Endpoint | Direct backend, three rounds | Through Vite, three rounds |
| --- | --- | --- |
| Finance metadata | 404 HTML; Finance absent from runtime URL patterns | Same 404 HTML |
| Operations auth/me | 403 JSON, detail only, no-store/no-cache | Same 403 JSON |

Result: **6/12 checks passed, helper exit 1, `routingVerified: false`.** No 502, connection refusal or timeout occurred in this three-round sample. That establishes current transport reachability only, not a permanent repair of the earlier interruptions. There are **no post-restart/post-correction successful results**, because service recovery cannot be performed safely in this environment.

### Exact normal VS Code PowerShell recovery/verification

Use normal VS Code PowerShell, not the restricted Codex terminal. These steps do not invoke migrations or financial mutations. Keep the current Finance roles/authentication unchanged.

First identify the existing backend process, its parent and source path:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
.\scripts\inspect-local-preview-processes.ps1
```

Review the fresh backend listener PID, parent, command line and executable path. If they refer to another project/service, stop and identify the intended owner rather than terminating it. Stop **only the identified development backend and its autoreloader launcher**, preferably with Ctrl+C in its original terminal. If it was launched hidden, terminate only the verified backend listener/launcher using those freshly inspected identities; leave Vite and unrelated Python processes running. Do not use saved PID numbers above or kill all Python processes.

Then verify the current checkout's Python, URL resolver and configured database identity without opening a database connection:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
$financePython = (Resolve-Path -LiteralPath '.\backend\.venv\Scripts\python.exe').Path
& $financePython -B -c 'import sys; print(sys.executable); print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'Use the already approved working backend interpreter; do not reinstall or change security settings for this check.' }
Push-Location -LiteralPath '.\backend'
try {
@'
import os
from unittest.mock import patch
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
assert os.environ['DJANGO_SETTINGS_MODULE'] == 'config.settings.development'
with patch('django.db.backends.base.base.BaseDatabaseWrapper.ensure_connection', side_effect=RuntimeError('Database connections forbidden during URL inspection')):
    import django
    django.setup()
    from django.conf import settings
    from django.urls import resolve
    import dic.urls, dic_finance.api
    db = settings.DATABASES['default']
    assert db['NAME'] == 'dawana_dev', 'Unexpected configured database; stop.'
    assert db['ENGINE'] == 'django.db.backends.postgresql'
    assert db.get('HOST') in ('localhost', '127.0.0.1', '::1'), 'Unexpected database host; stop.'
    match = resolve('/api/v1/dic/operations/finance/')
    assert match.url_name == 'operations-finance'
    assert match.func.view_class is dic_finance.api.FinanceView
    print('DIC URL source:', dic.urls.__file__)
    print('Finance source:', dic_finance.api.__file__)
    print('Finance resolver: PASS; configured database dawana_dev; no DB connection opened.')
'@ | & $financePython -B -
if ($LASTEXITCODE -ne 0) { throw 'Source/import/configuration check failed; do not start the server.' }
} finally { Pop-Location }
```

Expected paths are this checkout's `backend\dic\urls.py` and `backend\dic_finance\api.py`. If the virtual environment still cannot run in normal VS Code, supply the existing working interpreter explicitly in `$financePython` and repeat the version/source checks. Do not install a replacement or change `.env` credentials as part of this repair.

In that backend terminal, start the current checkout only after the old backend has stopped:

```powershell
if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is still occupied; inspect its owner before starting another backend.'
}
& $financePython -B .\backend\manage.py runserver 127.0.0.1:8000 --noreload
```

Keep this foreground terminal open and retain startup errors. `--noreload` gives one deterministic server for this routing check; source changes subsequently require an explicit restart. Django may warn that postponed migration 0027 is unapplied. **Do not run migrate or apply 0027 to clear that warning.** Do not use `start-local-preview.ps1` as a shortcut here: its preparation path can involve migration work or reject pending migrations. This command serves current code without invoking that preparation path.

In a second terminal, reuse Vite if port 5173 is already responding. If no frontend is running, start it with process-scoped values matching the verified backend:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP\dawana-platform"
$env:DJANGO_API_PROXY_TARGET = 'http://127.0.0.1:8000'
$env:VITE_API_BASE_URL = '/api/v1'
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Do not start a second Vite on an occupied port. No frontend restart is indicated by the current proxy observations. The environment assignments above affect that terminal/child only and do not modify `.env`.

Finally, from another normal VS Code terminal:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\DA'WANA WEB--APP"
node .\scripts\check-finance-routing.mjs
if ($LASTEXITCODE -ne 0) { throw 'Routing not verified. Preserve the timestamped JSON and backend terminal errors.' }
```

Expected: **12/12 passed**, exit 0, `routingVerified: true`; Finance and Operations auth must both return JSON 403 under current configuration, directly and through Vite. This is the gate for resuming Finance acceptance. If direct Finance succeeds but the proxy fails, investigate the running Vite target/configuration; if direct Finance still lists no Finance pattern, the wrong/stale backend is still serving. If direct requests refuse connections, inspect the foreground server's startup/exit output before retrying. These local commands have been prepared, **not executed successfully by Codex**.

### Corrections and files for this targeted task

No application routing/configuration/business-logic correction was justified: the inspected source path is consistent, while the running URL table differs. Operational recovery remains pending outside Codex. No credentials, migrations, permissions or financial records were modified; no completed Finance suites or browser acceptance audit were repeated.

Files added/updated:

1. `scripts/check-finance-routing.mjs` — focused anonymous loopback HTTP verifier and timestamped evidence writer; executed against the existing services, correctly failed while Finance remained HTML 404.
2. `output/acceptance/finance-routing/routing-2026-10-26T13-25-28-430Z.json` — observed direct/proxy results and sanitized resolver diagnostics.
3. `scripts/DIC_2026_FINANCE_DASHBOARD_VERIFICATION.md` — this diagnosis and exact local recovery/verification commands.

**Finance API routing is not yet verified. Overall recommendation remains Not ready.** The 404's Django origin and loaded/source URL mismatch are established; stale-process identity and the earlier downtime trigger remain unconfirmed until the local process/source checks and targeted recovery run complete.
