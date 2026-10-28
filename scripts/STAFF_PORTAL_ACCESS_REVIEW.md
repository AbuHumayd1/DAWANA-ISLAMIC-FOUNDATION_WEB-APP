# Dawana administrative entry-point review

26 October 2026. Scope: existing staff entry, one public footer link, focused verification.

## Existing functionality

- Operations login/portal route: `/dic/operations`. Local URL: `http://127.0.0.1:5173/dic/operations`. There is no separate `/login` page: `Operations` checks `/api/v1/dic/operations/auth/me/` and renders its existing login form when no authenticated Operations profile is available. `App.jsx` keeps this workspace outside the public layout.
- Django Admin: `/admin/`, local direct URL `http://127.0.0.1:8000/admin/`. Vite also proxies `/admin/` at `http://127.0.0.1:5173/admin/`. Project URLs register `admin.site.urls`; `django.contrib.admin`, session/authentication middleware and CSRF middleware are configured. `/admin/dic/operations/` is a separate existing admin-protected dashboard, not the React staff-login destination. Production URLs use the deployed origin; no production hostname was assumed.
- Operations authentication: username/password or unique active email/password through Django `authenticate()`; CSRF-protected, throttled login POST at `/api/v1/dic/operations/auth/login/`. Login requires an active account with `dic.can_view_dic_operations` (or superuser access). Django creates the existing session; frontend requests include cookies and refresh the CSRF token. Sessions are configured for eight hours, HttpOnly and SameSite Lax. This change adds no authentication mechanism or account.
- Existing login nuance: the login handler checks active status and Operations permission, rather than requiring `is_staff` itself. The portal's campsite-access flag additionally requires active staff; Finance independently requires active staff plus Operations and Finance permissions. No authorization rules were changed by this task.
- Successful login returns a profile and updates React state; it does not issue a server HTTP redirect. Entering from the new footer link stays at `/dic/operations` and shows the existing campsite overview for authorized staff. A direct protected subroute retains its URL and is subject to that route's permission guard. No external `next` redirect was introduced.
- Existing logout uses a CSRF-protected POST to `/api/v1/dic/operations/auth/logout/`; Django calls `logout()`, returns 204, and the client clears its profile/CSRF token and replaces the route with `/dic/operations`, displaying login again. This was inspected, not exercised with an authenticated session.
- Permission assignment uses Django's existing `AbstractUser`/`UserAdmin` infrastructure: administrators manage groups and explicit user permissions, and backend `has_perm()` checks consume those grants. No real assignments were queried or modified. Staff status alone does not confer Finance access.
- Finance is already at `/dic/operations/finance`, under **Finance & Reports**. Navigation and the route require campsite/staff access and the Finance flag derived from `dic.can_view_dic_finance`. Finance's backend checks active staff, Operations and Finance permissions, with independent `dic_finance` permissions for details, creating entries, approving, paying, budgets, reconciliation and exports. No separate Finance login is needed.
- The Operations shell already includes a conditional Django Admin link for eligible authenticated users. No Admin link was added publicly. The public header/footer previously had no Staff Login entry; other Operations links found were within the protected workspace.

## New change

Added **Staff Login** after Contact in the public footer's Engagement column. It is a normal React Router link to `/dic/operations`, using existing footer styles and layout. No header/mobile-menu, login, scrolling, CSS or protected-route code changed. Existing Dawana branding, responsive login card, theme controls and focus styling remain in use.

## Verification actually executed

- Rendered the real Footer using Vite SSR and React server rendering: exactly one Staff Login link to `/dic/operations`; no public `/admin/` link. Passed. SSR does not execute navigation or authenticate a browser.
- `node --test src/services/publicNavigation.test.js src/services/operationsRefinement.test.js`: **9 passed, 0 failed, 0 skipped**. Covers public navigation, permission-filtered Operations navigation (including Finance), and existing responsive/no-scroll-lock assertions. No full suite repeated.
- `oxlint src/components/layout/SiteChrome.jsx`: exit 0.
- Anonymous, read-only HTTP checks: Operations document on port 5173 returned **200 HTML** (SPA shell only); direct `/admin/` returned **302** to `/admin/login/?next=/admin/`; direct Operations auth/me returned **403 JSON**. No login/logout POST, credential submission or financial endpoint request was performed.
- Authentication, post-login destination, logout behavior, permission enforcement and responsive/scrolling code were inspected. These are not claimed as authenticated browser passes. The previously reported Finance API runtime route mismatch was not repaired or retested by this footer task; it remains a separate operational blocker until the targeted routing verifier passes.

## Files changed in this task

1. `dawana-platform/src/components/layout/SiteChrome.jsx` — one footer link. This file already had unrelated workspace changes; those were preserved.
2. `scripts/STAFF_PORTAL_ACCESS_REVIEW.md` — this review and verification record.

No database operations, migrations, new accounts, permission grants, credential changes or financial record changes occurred.

## Manual browser acceptance still required

1. At desktop and 390px/360px mobile widths, scroll the public page to the footer. Confirm Staff Login is visible, keyboard focusable and opens `/dic/operations` in the existing branded login interface. Check public hamburger open/close and normal page scrolling.
2. Using an existing authorized staff account, sign in normally: expect the existing Operations overview. Invalid credentials must give the existing generic error. Reload the page to verify the session; do not create accounts or change grants.
3. With existing Finance-authorized and non-Finance staff accounts, confirm Finance visibility and direct-subroute denial respectively. Complete Finance data-loading checks only after the separate routing blocker is resolved. Do not perform transactions, downloads or exports on development for this entry-point check.
4. On mobile, open the Operations hamburger, choose an allowed destination, close the menu and scroll normally. Confirm visible focus and reachable login/Sign out controls.
5. Sign out: expect the login interface at `/dic/operations`; reload and revisit a protected subroute to confirm no protected data returns. Separately visit `/admin/` and confirm its existing login/access rules; do not create a superuser or change credentials.

Browser automation previously failed initialization in this session; no new browser pass is claimed. An existing authenticated fixture was not supplied or reused. Readiness of Finance for operational use is not changed by making the staff entry discoverable.
