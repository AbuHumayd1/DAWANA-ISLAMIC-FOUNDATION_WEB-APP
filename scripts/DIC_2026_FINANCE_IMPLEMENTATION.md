# DIC 2026 — Finance implementation

## Delivery and release boundary

The approved `dic_finance` supporting app and Finance interface are implemented for controlled operational validation. This is not a claim of backend runtime acceptance or production deployment. No databases were created, migrated, flushed or changed; no email, worker, Paystack or live payment request was executed. Registration, payment settlement, camper authentication, scoring and the house ledger were not rewritten. The new app fails closed with a 503 setup-pending response until its schema is separately approved and applied. Missing schema never appears as zero revenue.

## Features and navigation

Existing Operations sidebar → **Finance** (`/dic/operations/finance`), under Finance & Reports. Seven in-page sections:

1. Overview: backend-derived verified registration receipts after adjustments, approved other income, paid expenditure, approved unpaid commitments, edition budget, remaining budget, recorded net position and pending/failed/exception counts.
2. Registration revenue: existing payment attempts, booking/payment status, verified amount, discrepancies and record detail; no duplicate registration-income ledger.
3. Other income: configurable edition-specific categories, dated NGN drafts, method/reference, description, responsible official, private evidence and approval workflow.
4. Expenses: draft → submitted → approved → paid; rejection/cancellation, explicit audited reversal, original record retained. Creator cannot approve their own record. Approval is distinct from cash payment confirmation. Stale versions are rejected.
5. Budgets: edition/category allocations, immutable revision history, approving official, actual paid spend, remaining allocation, utilisation and over-budget indicators. The latest revision replaces the allocation; revisions are not summed as extra budgets.
6. Reconciliation: manually supplied provider evidence, amount/reference/reason, matched/exception/refund/reversal records and history. No provider network calls, payment verification, successful-attempt fabrication or eligibility changes.
7. Reports: registration revenue, other income, expenses, budget versus actual, reconciliation and consolidated summary. Excel-compatible UTF-8 CSV with BOM and shared spreadsheet-formula protection; exports are permission-checked and audited.

Search, edition/category/date/status filters, paginated transaction lists, detail panels, loading/empty/error/retry states, confirmation before mutations, responsive tables and compact forms are included. Budget comparisons explicitly remain edition-wide. No fabricated categories or balances are seeded.

Drafts can receive a private PDF/PNG/JPEG receipt up to 2 MB. The server checks the signature, stores bytes in the database (no public media URL), restricts attachment to the draft creator, and delivers downloads as attachments under Finance detail permission. This is a small supporting-evidence facility, not a malware-scanning/document-management service. Evidence references can also point to documents retained under existing authorised procedures. Evidence is not automatically treated as independent proof that money moved.

## Backend files

New:

- `backend/dic_finance/__init__.py`
- `backend/dic_finance/apps.py`
- `backend/dic_finance/models.py`
- `backend/dic_finance/services.py`
- `backend/dic_finance/api.py`
- `backend/dic_finance/migrations/__init__.py`
- `backend/dic_finance/migrations/0001_initial.py`
- `backend/dic_finance/tests.py`
- `backend/dic_finance/test_integration.py`

Modified integration points:

- `backend/config/settings/base.py`: register the app.
- `backend/dic/urls.py`: existing Operations Finance endpoint.
- `backend/dic/operations_api.py`: expose explicit Finance action permission flags in staff session metadata. Existing reporting/payment functions are unchanged by this implementation.

Models:

| Model | Purpose |
|---|---|
| Category | Edition-specific, named income/expense categories; no official categories invented |
| Entry | Other income or expense; exact NGN kobo, workflow/version, creator/approver, private receipt and references |
| BudgetRevision | Append-only allocation revisions per edition/expense category |
| Reconciliation | Append-only evidence attached to an existing payment attempt; no duplicate transaction record |

All relationships protect their source records. No default model CRUD permissions are granted. There is no Finance delete API or automatic permission assignment. Commands lock the edition and the entry where relevant, and use the existing `DICAdminAuditEvent` inside the same transaction. Creation, approval, payment confirmation, reversal, reconciliation, budget/category changes, receipt attachment/download and exports are audited. Budget/reconciliation records have no edit/delete endpoint. Corrections retain original entries and require explicit cancel/reverse followed by a new reference.

### API

`GET /api/v1/dic/operations/finance/?metadata=1`: authorised edition choices, available even before schema preparation.

`GET /api/v1/dic/operations/finance/?edition=<id>`: summary, permitted detail, categories, budget/history and permissions. Optional `date_from`, `date_to`, `category` (registration), `finance_category`, `status`, `payment_status`, `q`, `page`. Lists are paginated at 50; exports use the full filtered calculation with a 5,000-row ceiling.

`GET .../finance/?edition=<id>&export=registration|income|expenses|budgets|reconciliation|summary`: protected CSV export.

`GET .../finance/?edition=<id>&receipt=<entry-uuid>`: protected attachment download.

`POST .../finance/?edition=<id>`: explicit `action` of `category`, `create`, `submit`, `approve`, `pay`, `reject`, `cancel`, `reverse`, `budget`, `reconcile` or multipart `receipt`. Justification is mandatory. Existing staff session authentication, CSRF enforcement, no-store headers and Operations access are reused.

### Permissions

Every request requires active staff, existing `dic.can_view_dic_operations` and `dic.can_view_dic_finance`. Summary access alone does not disclose transaction details. New permissions, all under `dic_finance`:

```text
can_view_details_finance
can_record_income_finance
can_submit_expense_finance
can_approve_finance
can_confirm_payment_finance
can_manage_budget_finance
can_reconcile_finance
can_export_finance
```

Exports additionally require detail permission. Categories and budget revisions require budget-management permission. Approving an entry requires an official other than the creator, including for superusers. Payment confirmation requires its own permission and supporting evidence. No roles/users were modified; authorised assignments remain an operational decision.

## Financial rules

- Amounts are positive exact NGN kobo; excess precision, non-finite values and invalid currencies are rejected. No float arithmetic is used for monetary totals. Utilisation is a display percentage only.
- Registration receipts use existing `PaymentAttempt` and registration/current-pricing records. They require confirmed/paid order state, successful verified provider evidence, matching expected and reported NGN amounts, transaction ID, accepted current price revision and the existing `_revision_is_valid_at_payment` rule. Documented refunded orders can retain trusted original-charge evidence solely for Finance adjustment calculations; participant eligibility is unchanged.
- Each order/provider transaction can contribute once. Pending, failed, duplicate-success and unresolved mismatch/reconciliation cases are not received revenue. These records remain visible. Normal pending/failed attempts are counted separately from reconciliation exceptions.
- Documented partial/full refunds and reversals reduce the verified original charge by their exact cumulative amount. Cumulative adjustments cannot exceed that charge. Their history remains even after a later matched note. A refund status without sufficient original evidence does not invent revenue. Exception notes can hold a receipt out of totals; matched notes cannot create missing verification evidence.
- “Verified receipts” means verified gross charges less documented adjustments, **not bank settlement or net proceeds after provider fees**. The recorded net position is not labelled a bank balance. There is no automatic provider fee/settlement import.
- Other income counts only when approved, after recording that funds were received. Pending approvals do not count. Known registration references/provider transaction IDs cannot be entered as manual entry references, and edition references cannot be reused. Staff must still classify sources honestly: a deliberately relabelled duplicate charge cannot be reliably recognised without independent evidence.
- Only paid expenses count as expenditure. Approved-but-unpaid commitments are shown separately. Budget allocations do not reduce cash. Reversed income/expenses leave originals and audits intact but no longer contribute; officials must use reversal only for a justified accounting correction or actual reversed movement.
- Budget remaining is latest approved edition allocations less edition-wide paid expenses, including unbudgeted categories. Negative balances/over-budget flags remain visible. No cash balance is inferred from budget values.
- Registration category filters select whole matching bookings, not an invented apportionment of group-booking revenue. Registration date uses provider completion date, falling back to attempt creation for unresolved attempts. Current evidence/adjustment state applies to the selected original receipt, rather than asserting a dated bank statement. Entry dates are recorded income/expense dates. Status/date/search filters apply to their respective transaction sources; budgets always compare edition-wide values. Do not interpret category-selected registration receipts as category-fee allocation totals.
- Finance dashboard and Finance reports use the same snapshot/calculation services. The older general Operations reports still have the audit's weaker “verified paid” labels and filter semantics; those legacy reports were not silently rewritten. Use Finance reports for the new financial definitions.

## Frontend files

New: `src/pages/Finance.jsx`, `src/pages/Finance.css`, `src/services/finance.js`, `src/services/finance.test.js` under `dawana-platform`.

Modified: `src/pages/Operations.jsx`, `src/services/operationsNavigation.js`, `src/services/campsiteModules.js`, `src/services/campsiteFoundation.test.js`, `src/services/operationsRefinement.test.js`. Finance is no longer routed to a planned-module screen; Comprehensive reporting remains planned. No new dashboard shell or camper-facing financial route was created.

## Migration preparation and graph evidence

Filename: `backend/dic_finance/migrations/0001_initial.py`.

Exact dependencies:

```python
dependencies = [
    ('dic', '0026_house_score_transaction'),
    migrations.swappable_dependency(settings.AUTH_USER_MODEL),
]
```

Source inspection before preparation confirmed that dic 0026 descends from check-in 0025 and earlier migrations, while postponed dic 0027 is its child, not its prerequisite. The configured accounts initial migration depends on auth 0012, not on feedback/welfare. The initial Finance migration was then hand-prepared and its dependencies/operations inspected. It creates only Finance tables and contains no data migration, RunSQL, seeding, replacement, merge or history rewrite. It does not depend on dic_scoring or 0027.

**No migration was applied to any database.** No runtime MigrationLoader/autodetector/schema check could run because Python is inaccessible. The static dependency conclusion is not a claimed executed Django graph check. A runtime graph and model/migration consistency check remain mandatory before application.

Safe next verification from normal PowerShell, from repository root (reads model/migration files; does not create a database or execute a migration):

```powershell
$financePython = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
@'
import runpy
ns = runpy.run_path('scripts/portal_test_booking.py', run_name='finance_graph_only')
ns['configure']()
from django.apps import apps
from django.core.management import call_command
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.state import ProjectState
loader = MigrationLoader(None)
target = ('dic_finance', '0001_initial')
plan = loader.graph.forwards_plan(target)
assert ('dic', '0027_feedback_welfare') not in plan
assert ('dic', '0026_house_score_transaction') in plan
print('Finance dependency plan:', plan)
changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
assert not changes.get('dic_finance'), 'Finance model/migration drift: stop and review.'
call_command('check', verbosity=1)
'@ | & $financePython -B -
if ($LASTEXITCODE -ne 0) { throw 'Finance graph/model validation failed; do not migrate.' }
```

Do not run unrestricted migrate, use the protected OTP fixture for integration test cleanup, or assume `--keepdb` prevents schema changes/flushes. Database-backed tests require a separately approved disposable database and constrained migration plan. No creation/application commands are authorised by this document.

## Actual validation results

- First frontend run: 141 passed, 1 failed. The failed assertion expected two planned navigation badges, including Finance. Updated it to expect only Comprehensive reporting and replaced obsolete Finance-placeholder rendering assertions.
- Final frontend run: **142 passed, 0 failed, 0 skipped** (`npm.cmd test`). Includes five new Finance utility/workflow tests and updated route/navigation/rendering coverage.
- Final lint: **passed without warnings** (`npm.cmd run lint`).
- Final production build: **passed** (`npm.cmd run build`). Vite reports the existing class of bundle-size warning; current JS chunk is approximately 593 kB minified.
- Backend interpreter probe: **access denied** to the configured Python313 base executable. No security settings, installations or virtual environment changes attempted.
- Backend Finance policy tests: **19 written, 0 executed**. Cover exact amounts, invalid values, action permissions, trusted revenue evidence, pending/failed/duplicate/refunded/mismatched payments, deduplication, documented reversals, approval separation, stale versions, audit invocation, anonymous API denial, budget/cash separation and spreadsheet escaping.
- Backend Finance integration tests: **4 written, 0 executed**. Cover persisted approval/payment/reversal/audits, budget revision totals, cross-edition rejection and stale/unauthorised mutations. Must run only through an approved constrained disposable environment.
- Django checks, model/migration autodetection, database constraints/concurrency, actual receipt uploads/downloads, role assignments and browser/mobile rendering remain **unverified**. Responsive CSS and server-rendered navigation checks are not a browser viewport pass.

## Outstanding operational decisions and blockers

1. Assign named Finance officers the approved least-privilege permissions; decide whether payment confirmers must also differ from submitters/approvers. Current mandatory separation is creator versus approver.
2. Supply authorised income/expense categories and budget allocations; none were invented or seeded. Decide approval thresholds and any escalation policy before broad use; no invented thresholds are encoded.
3. Agree evidence retention, receipt handling/scanning requirements and reversal/refund documentation procedures. Uploaded originals are private; there is no automated malware scanner or Paystack refund initiation.
4. Provide a runnable approved backend environment and approve a disposable test database/targeted migration plan before backend integration acceptance. Neither `dawana_dev` nor the existing OTP fixture is an approved disposable test target.
5. Complete runtime migration/model checks and backend tests before applying schema or claiming the module operational. The UI intentionally reports setup pending until then.

No Feedback, Certificates, Games, live-payment enablement or new House Leader Dashboard was implemented.
