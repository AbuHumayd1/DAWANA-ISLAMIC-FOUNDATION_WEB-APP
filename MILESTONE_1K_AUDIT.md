# Milestone 1K initial audit

Audit date: 18 October 2026. Baseline HEAD: `604261e`.

The initial worktree had 12 modified tracked files and 13 untracked paths (including `.vscode/`). Attribution to Copilot cannot be established from Git alone. All existing work is retained; `.vscode/settings.json` is untouched.

| Component | Initial classification | Evidence |
| --- | --- | --- |
| Migration 0013 | BROKEN OR BLOCKED (database verification) | `backend/dic/migrations/0013_alter_campedition_options_and_more.py` adds permissions, two provider fields and audit model; no destructive operation. Python cannot execute. |
| Staff roles | IMPLEMENTED BUT UNTESTED | `backend/dic/management/commands/setup_dic_staff_roles.py`; transactional group provisioning, no user assignment; replaces group permission sets on repeat. |
| Django Admin operations | IMPLEMENTED BUT UNTESTED | `backend/dic/admin.py`, `operations.py`, admin templates; dashboard, protected actions and read-only payments. |
| React Operations Portal | IMPLEMENTED BUT UNTESTED | `dawana-platform/src/pages/Operations.jsx`, `App.jsx`; nested operations routes. |
| Staff login/logout | PARTIALLY IMPLEMENTED | `operations_api.py`, `operationsApi.js`; session and CSRF login; cached token remains stale after login rotation. |
| Shared Django authentication | IMPLEMENTED BUT UNTESTED | Django authenticate/login/logout and SessionAuthentication; no separate identities. |
| Dashboard statistics | IMPLEMENTED BUT UNTESTED | OperationsDashboardView distinguishes orders and participants. |
| Dashboard charts | PARTIALLY IMPLEMENTED | DashboardPage renders distributions and recent activity; no dashboard filter controls. |
| Registration management | IMPLEMENTED BUT UNTESTED | Registration API/list/detail, search, filters and pagination. |
| Participant management | PARTIALLY IMPLEMENTED | Participant API/list/detail; related category/house filters may select other editions. |
| Payment monitoring | PARTIALLY IMPLEMENTED | Finance permission enforced; export status parsing incorrectly applies registration choices. |
| House oversight | IMPLEMENTED BUT UNTESTED | OperationsHouseView; eligibility uses existing allocation service. |
| Reports | BROKEN OR BLOCKED | OperationsReportView passes list into registration_export_rows, which expects queryset. |
| Word exports | PARTIALLY IMPLEMENTED | operations_exports.py; tables/footer/page field; lacks local official logo and render verification. |
| CSV exports | PARTIALLY IMPLEMENTED | Formula escaping present; registration portal export broken; admin lacks BOM. |
| Audit logging | PARTIALLY IMPLEMENTED | DICAdminAuditEvent; finance detail exposes audit history without separate audit permission; export metadata incomplete. |
| Responsive layout | IMPLEMENTED BUT UNTESTED | Operations.css breakpoints; frontend lint/build passed. |
| Mobile navigation | PARTIALLY IMPLEMENTED | Menu closes on clicked nav link; lacks Escape and route-change handling. |
| Scrolling | IMPLEMENTED BUT UNTESTED | Document layout, pathname scroll reset, horizontal table wrappers; browser QA pending. |
| Tests | PARTIALLY IMPLEMENTED | test_operations.py and test_operations_portal.py; no frontend test runner; backend execution blocked. |

Initial commands: `npm.cmd run lint` and `npm.cmd run build` passed. Existing backend virtualenv and registered Python 3.13 both fail with Access is denied. Consequently migration history, current development records, staff membership, full backend tests, checks and drift are unverified. No migrations or role commands were executed successfully. No database state is assumed from historical handover observations.

This records the initial audit, before repairs. Subsequent verification and the recovered Python runtime are documented in `MILESTONE_1K_HANDOVER.md`.
