# CP-2 — Participant session and shared-device safety

CP-2 only. No backend authentication, cookie/CSRF policy, OTP throttle, model, migration, database, payment, scoring, permissions or welfare changes. CP-3 is not implemented.

## Files changed

- `dawana-platform/src/services/participantSession.js` (new): participant-only BroadcastChannel with storage-event fallback; closure marker, subscription cleanup and testable logout outcome orchestration.
- `dawana-platform/src/services/participantSession.test.js` (new): seven focused regression tests.
- `dawana-platform/src/pages/ParticipantPortal.jsx`: immediate local/cross-tab clearing; retained generation/expiry guards; confirmed-versus-unconfirmed server logout messages and retry; avoid automatic session restoration after local closure.
- `dawana-platform/src/pages/CamperFeedback.jsx`: same participant-only closure subscription, clear camper choices, abort outstanding option/submission requests, skip restoration after closure.
- `dawana-platform/src/pages/ParticipantPortal.css`: scoped wrapping/max-width rules for participant session and ID controls on narrow screens.
- `backend/dic/CAMPER_PORTAL_CP2.md`: this handover.

## Security behaviour

Closing participant access broadcasts only the constant `closed` message on `dawana-participant-session-v1` and writes a non-sensitive changing marker under `dawana.participant.session-closed.v1`. No booking references, names, OTPs, cookies or credentials enter browser storage. Both mechanisms are used so browsers without one can still clear other tabs; duplicate clear notifications are idempotent. Neither Operations nor Admin subscribes or has its cookies changed by this mechanism.

Logout first invalidates outstanding requests and clears profile, orders, camper selection, ID, challenge, code, contact and reference. Other open participant/feedback tabs clear promptly on notification. The normal server logout remains the authoritative grant-revocation call and still uses the existing CSRF client. Success is shown only after a successful server response. Network/CSRF/session rejection produces a generic unconfirmed-sign-out warning and retry, never a false server-revocation claim. A server-rejected retry remains unconfirmed rather than assuming what happened remotely.

The marker prevents automatic `/auth/me/` restoration in participant/feedback pages after local closure, including a reload following failed logout. Successful existing OTP verification removes the marker. The marker is not authentication: deleting it does not grant access, and it cannot revoke a server grant. A new OTP login still goes through production verification/throttles.

The existing 30-minute server session remains unchanged. The portal retains deadline checks before/after asynchronous work and expiry-event clearing. Camper selection invalidates old request generations; late responses cannot repopulate another camper's card. Logout completion callbacks likewise require the current request generation; unmount/cross-tab invalidation prevents late callback state updates. Feedback option loading checks abort state, and its submission transport now uses the same lifecycle AbortSignal.

Listeners and BroadcastChannels are removed/closed on cleanup; feedback expiry timers are cleared. No tokens are copied between tabs and no second authentication system is introduced.

## Mobile and scrolling

Portal content remains in the public site's normal document flow with responsive camper grids and no new fixed-height shell, nested content scrollbar or body scroll locking. Long ID links/buttons and session controls can wrap within the viewport. Branding and typography are unchanged.

The existing shared public menu already closes on navigation/Escape, cleans its listeners/timers and does not mutate body overflow. It retains its pre-existing bounded mobile popup scrolling for small viewports; CP-2 did not redesign shared navigation or claim that the popup has no scrollbar. Main portal content uses normal document scrolling.

## Verification actually executed

- Frontend suite: **107 passed, zero failed** (seven new session tests).
- Lint: passed without warnings after moving the closure-restoration initial state out of an effect.
- Production build: passed; existing >500 kB bundle warning remains (about 547 kB).
- Targeted `git diff --check`: passed; existing line-ending warnings only.
- Backend attempt: existing venv Python fails before Django starts with base-interpreter Access is denied. No backend test or database operation executed.
- Browser attempt: CUA initialization fails with kernel-assets path error, OS error 3. **No real cross-tab, desktop/mobile or navigation acceptance pass is claimed.**

New automated cases exercise multiple-tab notifications, marker-only storage, channel/listener cleanup, storage fallback, blocked-storage broadcast fallback, Operations/Admin-key isolation, failed/successful logout ordering, expiry invalidation, camper-switch/stale-response protection and integration-source assertions. Browser-native transport tests use a simulated browser harness; they are not substitutes for real multi-tab browser testing.

## Local validation

Existing activated PowerShell, repository root:

```powershell
python -B scripts\validate_dic_backend.py --ids-only
Set-Location .\dawana-platform
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run dev
```

The backend runner uses its unique isolated PostgreSQL database and never migrates/flushes development. No migration is necessary for CP-2.

## Manual acceptance still required

At 1440×900, 768×1024, 390×844 and 360×800:

1. Verify an authorised synthetic booking and open the portal in two tabs, plus feedback and a separate Operations/Admin tab.
2. Logout in one portal tab: other participant tabs should clear promptly; staff sessions should remain unaffected.
3. Block the logout request/network: participant data must disappear immediately, no confirmed-server-sign-out message should appear, and retry should work after connectivity returns. Reload must not silently restore the dashboard while the closure marker remains.
4. Exercise server expiry/revocation and expiry during a delayed ID request; no late card/dashboard data may reappear. Switch campers around delayed responses and verify names, house, arrival and ID remain consistent.
5. Check existing OTP, recovery, ID formats/downloads, activities and feedback. Feedback choices/forms should disappear after cross-tab closure, including while loading.
6. Open/close hamburger navigation with links, Escape, orientation changes and back/forward; verify usable controls, normal page scrolling and no persistent lock/overflow. Existing mobile-menu popup may scroll independently while open.
7. Repeat in browser privacy modes and with storage or BroadcastChannel unavailable.

## Limits and risks

Cross-tab UI clearing is best effort if both browser messaging/storage facilities are blocked; server revocation/expiry still enforce access. Clearing storage manually can remove the local barrier but cannot bypass server authorisation. Notifications cannot retract previously downloaded or separately rendered ID artifacts, screenshots or printed copies.

Failed logout can leave the server grant active until a successful retry, fresh verification rotation or expiry. The UI explicitly reports that uncertainty. Aborting a request cannot guarantee it was not already processed server-side. Concurrent login/logout across tabs still needs browser acceptance; no stronger claim about browser cookie response ordering is made. No offline revocation capability was added.

CP-3 individual scores/ranks, new accounts, payment changes and further phases remain outside scope. Stop for review.
