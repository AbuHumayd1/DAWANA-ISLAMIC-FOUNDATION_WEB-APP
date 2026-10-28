# DIC Camper Portal — mobile-first presentation

Implemented frontend-only. No backend models, authentication contracts, scoring rules,
registration availability, prices, payments, records or migrations were changed.

## Changes

- Dedicated portal route shell without duplicate public header/footer navigation.
- Five destinations stored in the URL `view` query: Home, My Points, Houses, Camp,
  Profile. Browser back/forward works; navigation returns to the top of the document.
- Fixed safe-area-aware mobile bottom navigation; desktop sidebar and constrained main.
- Emerald/off-white/gold visual system, house accent from validated assigned-house colour,
  responsive cards, short restrained transitions, keyboard focus and reduced motion.
- Home uses authenticated name/edition, personal points/rank, current house, latest
  contributions and actual house standings. Unknown values are shown as unavailable.
- My Points retains backend totals, activity names, reversals and paginated history.
- Houses shows backend ranks/ties/negative totals and only the permitted individual list.
- Camp uses the selected booking's edition and public camp details only when its name
  matches; otherwise it links to official published activities and feedback, without
  inventing schedules or announcements.
- Profile displays the selected camper, booking, payment, house and arrival state, existing
  ID eligibility/authorised download entry, refresh and secure logout.
- Compact 440px maximum authentication form; existing OTP requirements/resend retained,
  with expiry countdown from backend `expires_in` and existing delivery/error states.
- Registration confirmation offers a portal link carrying only booking UUID in router
  state. The UUID is syntax-checked before prefill; contact verification remains required.
  No OTP, session/bearer credential or contact information is placed in URLs. Direct
  visits still accept manual booking entry. No cross-device handoff or auto-login added.

## Files in this change

Created:
- dawana-platform/src/components/dic/CamperExperience.jsx
- dawana-platform/src/components/dic/CamperExperience.css
- dawana-platform/src/services/camperExperience.test.js
- scripts/CAMPER_PREMIUM_UI.md

Modified:
- dawana-platform/src/pages/ParticipantPortal.jsx
- dawana-platform/src/pages/DIC.jsx (confirmation handoff link only)
- dawana-platform/src/components/dic/CamperScores.jsx (reuse fetch through render callback)
- dawana-platform/src/components/layout/SiteChrome.jsx (portal chrome/reveal exclusion only)

Reused endpoints: participant auth options/me/challenges/verify/logout, enrollments,
participant scoring, authorised enrollment ID/card downloads, and public registration-options.
No endpoint was created or modified. No notifications, data charts or artificial scores.

## Verification

The initial existing frontend suite passed 118 tests. Ten additional rendered-component
and routing/structure tests cover the five destinations, authenticated personal data,
unpaid ID denial, eligible ID entry, no retained previous camper, zero/unavailable/error
states, original scoring/reversal values, backend tie/negative ranks, camp sources,
credential-free handoff, safe areas and reduced-motion/document-flow safeguards.
One test initially matched min-height as a fixed height; that test regex was corrected.
All ten then passed. Full suite: 128 passed, zero failed/skipped. Final lint is clean;
production build passes with the existing >500 kB bundle warning (about 576 kB).

Backend database-free execution was attempted and stopped before Django with existing
Python base-interpreter Access is denied. No backend or database pass is claimed.
Browser inventory exposed no browser automation surface; Chrome access was previously
rejected and was not requested again. No visual acceptance, live OTP or authenticated
viewport test is claimed. The requested 320/375/390/430px, tablet and desktop visual
checks remain manual, including keyboard, back navigation, long house names, normal
scrolling, safe-area bar clearance and the real unpaid session. No fixture DB changes
were made for this redesign.

## Local preview

From repository root, with the isolated fixture already provisioned as documented in
PORTAL_OTP_TEST_BOOKING.md (do not run creation/migration again merely for this UI):

```powershell
& .\backend\.venv\Scripts\python.exe -B scripts/portal_test_booking.py serve
```

In a second terminal, using the same .env and no conflicting process overrides:

```powershell
while ($true) {
  & .\backend\.venv\Scripts\python.exe -B scripts/portal_test_booking.py worker --confirm-database test_dic_portal_2026_local
  if ($LASTEXITCODE -ne 0) { throw 'Worker stopped' }
  Start-Sleep -Seconds 5
}
```

Frontend terminal:

```powershell
npm.cmd --prefix dawana-platform run dev -- --host 127.0.0.1
```

Visit http://127.0.0.1:5173/dic/participant and verify the authorised fixture booking
with its real delivered OTP. Never use the local-preview launcher for real OTP delivery.
No paid-only ID/house/scoring data is fabricated for acceptance. Pending scoring storage
remains explicitly unavailable; `dic.0027_feedback_welfare` stays unapplied.
