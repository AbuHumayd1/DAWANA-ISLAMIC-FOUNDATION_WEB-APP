# Milestone 1K final acceptance report

18 October 2026. Functional acceptance checks passed. Visual acceptance remains pending because no browser or Word renderer is available in this session.

## Running local application

The existing Django development server is running at `http://127.0.0.1:8000/`, and the existing Vite frontend at `http://127.0.0.1:5173/`. They were started using the existing development configuration. No production settings were changed.

| Purpose | Local URL |
| --- | --- |
| Operations login/dashboard | http://127.0.0.1:5173/dic/operations |
| Registrations | http://127.0.0.1:5173/dic/operations/registrations |
| Participants | http://127.0.0.1:5173/dic/operations/participants |
| Finance | http://127.0.0.1:5173/dic/operations/payments |
| Houses | http://127.0.0.1:5173/dic/operations/houses |
| Reports | http://127.0.0.1:5173/dic/operations/reports |
| Audit activity | http://127.0.0.1:5173/dic/operations/activity |
| Django Admin through same origin | http://127.0.0.1:5173/admin/ |
| Django Admin directly | http://127.0.0.1:8000/admin/ |
| Health | http://127.0.0.1:8000/api/v1/health/ |

The portal HTML, backend health, frontend-proxied health, CSRF initialization and direct Admin login returned HTTP 200. These are HTTP smoke checks, not rendered browser tests.

The existing virtualenv executable still cannot launch its original Python. Backend startup reused PostgreSQL pgAdmin's installed Python with the project's existing packages:

```powershell
# From backend, if restarting is needed
& 'C:\Program Files\PostgreSQL\17\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv/Lib/site-packages'); sys.path.insert(0,'.'); sys.argv=['manage.py','runserver','127.0.0.1:8000','--noreload']; runpy.run_path('manage.py',run_name='__main__')"
# From dawana-platform
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## Verified functionality

- Three new transactional acceptance tests passed: expired-session rejection; zero metrics/empty directories for an edition without registrations; representative reports and export-permission restrictions.
- All six reports were downloaded from the actual Django export view using isolated test accounts and data in the existing configured test database, never in `dawana_dev`.
- Word and CSV row counts match for every sample. Word branding text, repeating table-header XML, PAGE field and portrait/landscape section dimensions were verified structurally.
- Finance downloads are denied to ordinary operators in both formats; both formats are denied without general export permission.
- Existing backend tests cover shared login/logout, CSRF, granular permissions, multi-participant counts, search/filter/pagination, trusted payments, recovery, early-bird pricing, allocation eligibility, Admin safeguards and export auditing.
- Frontend session tests passed: credentials included, rotated CSRF refreshed, expired-session notifications and permission-denial behavior. Lint and production build passed.
- Migration history remains consistent, 0013 remains applied, system checks report zero issues and migration drift reports no changes.

## Genuine defect corrected

The Vite development proxy forwarded `/admin` but not `/static`. Consequently `http://127.0.0.1:5173/static/admin/css/base.css` returned the React HTML document with `text/html`, leaving proxied Django Admin unstyled. Added a `/static` proxy to the same existing backend target in `dawana-platform/vite.config.js`. Rechecking returned HTTP 200 with `text/css`. Production settings and the existing interfaces were preserved.

Added `backend/dic/test_acceptance.py` for reproducible isolated acceptance fixtures and checks. No redesign was undertaken without rendered evidence.

## Visual review status

**Visually verified functionality: none in this session.** Browser inventory returned `apps: []` and `browsers: []`. No desktop, tablet or mobile viewport was rendered or interacted with. HTTP 200 responses and source review do not establish visual acceptance.

Source review found existing green/gold/cream tokens, branded lockups, refined heading typography, responsive card/chart/table layouts, mobile navigation rules, hover transitions, focus outlines, touch-target rules, normal document layout, horizontal table scrolling and reduced-motion overrides. These remain implemented but their actual appearance and behavior require browser review. No fictional dashboard statistics were introduced.

## Representative Word and CSV reports

`acceptance-artifacts/dawana-acceptance-reports.zip` contains the six DOCX samples, six matching CSV samples and a manifest. Every document contains clearly named synthetic acceptance fixtures; none is a real operational report.

| Report | Records | Columns | Word orientation |
| --- | ---: | ---: | --- |
| Registrations | 34 | 14 | Landscape |
| Participants | 35 | 11 | Landscape |
| Payments | 17 | 10 | Landscape |
| Categories | 33 | 5 | Portrait |
| Houses | 32 | 5 | Portrait |
| Attention | 17 | 3 | Portrait |

Samples are also available individually under `acceptance-artifacts/reports/acceptance-<report>.docx` and `.csv`. They include long names, descriptions, UUID identifiers and enough rows to exercise wrapping and pagination in the wider/larger reports. Actual page counts and page breaks are unverified.

The Documents renderer was attempted and failed at import with `ModuleNotFoundError: No module named 'pdf2image'`. No `soffice`/`pdftoppm` command was found, and LibreOffice was absent from the standard Windows installation paths checked. No rendering software was installed. Therefore table clipping, long-text wrapping, repeated headings on subsequent pages, page-number display, multipage behavior and footer placement still require visual inspection in Word or LibreOffice.

## Official logo

Searched project assets, reference folders and design ZIP entries. No approved standalone local Dawana logo was found. The frontend still references the same external Google-hosted logo as `SiteChrome.jsx`; it was not replaced with a generated graphic, screenshot crop or starter icon. The existing favicon is a Vite starter asset and is not evidence of an approved Dawana logo.

Supply the approved original PNG at **`backend/dic/assets/dawana-logo.png`** for the existing Word exporter. A lossless copy of that same approved asset should also be placed in the frontend's public/assets directory and referenced by the brand lockups when local branding is available. Logo appearance and external availability remain unverified.

## Concise manual browser procedure

1. Open the operations URL above. Test at **1440×900**, **768×1024** and **390×844** in browser responsive mode. Use an existing authorized staff account; no new development accounts were created for this session.
2. Sign in, verify the real draft edition and zero operational counts. Open every permitted section. Confirm helpful empty states, no console errors and no invented activity. Use slow-network throttling to inspect loading states, then restore normal networking.
3. Review logo loading, typography, spacing, cards, charts, table alignment and filter controls. Tab through controls and check visible focus. Enable reduced motion and confirm animations are restrained.
4. Scroll long pages and navigate between sections. Confirm one primary document scrollbar, top positioning after navigation and horizontal scrolling only within wide tables. On mobile, open/close the hamburger, choose a link and press Escape; confirm closure and usable focus.
5. Search/filter the empty directories; results must remain empty with no errors. Populated search/filter/pagination is covered by backend tests; rendered populated-table acceptance is still pending and should be done against a separately configured isolated test environment, never by inserting synthetic registrations into development.
6. With appropriately authorized existing accounts, confirm finance/audit/contact/export access. Attempt direct restricted URLs as an operator. Confirm Django Admin uses the same credentials and retains its staff restrictions; inspect its styles through the frontend URL.
7. Download Word and CSV from Reports and Admin. Inspect the supplied populated samples separately: Print Layout, headings, branding, table boundaries, UUID/long-text wrapping, orientation, repeated headers, page numbers, footer clearance and page breaks. Compare rows with CSV. Mark a sample visually accepted only after inspecting every page.
8. Delete only the `sessionid` cookie in browser developer tools and trigger a fresh data request. Confirm return to sign-in. Sign in again and sign out; confirm private data is inaccessible afterward.

No fixture passwords are provided because the test accounts exist only within rolled-back test transactions and cannot sign in to the running development server.

## State preservation and checks

- Development database remains `dawana_dev`; DIC 2026 is **draft**, 23 December 2026–1 January 2027, Faisal Omar Memorial School.
- Development category/order/participant/payment/house/allocation counts remain zero. Acceptance account names are absent from development.
- Paystack mode remains **test**. No payment settlement code, registration status, camp configuration or production settings were changed.
- `.vscode/settings.json` SHA-256 before and after: `77E594534D02F33D324DBF54097A13EE3F5E3028E6410B3FB119347C2B714E12`.
- No real accounts were created. No commits, pushes or deployments were performed. Existing uncommitted work is preserved.

Final results: **153 backend tests passed in 118.432 seconds**, including the three new acceptance tests; **3 frontend service tests passed**; frontend lint/build, Django system checks, migration drift and `git diff --check` passed. Browser and Word visual acceptance remain the outstanding acceptance gates. The external logo download was retried and again failed to connect.
