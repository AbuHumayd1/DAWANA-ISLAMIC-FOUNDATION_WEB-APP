# Dawana visual regression restoration

Status: confirmed CSS defects corrected; browser visual acceptance remains pending.

## Baseline and scope

Compared the current working tree with `fb24dfa` (Milestone 1K/theme checkpoint) and `604261e` (public design before the broad theme conversion). Inspected `stitch-designs/home.zip.zip` and `stitch-designs/dic.zip.zip` HTML references: both specify a compact horizontal header and a light surface footer with dark text. Existing layout and wording remain the source of truth; no wholesale revert was performed.

Inventoried modified/untracked files and reviewed appearance changes against those baselines. Existing participant routes, staff ID permissions, API additions, models, migration 0014 and untracked 1L-A files were retained. No backend or business-logic files were changed in this restoration.

## Confirmed causes and corrections

| Regression | Cause and timing | Correction |
| --- | --- | --- |
| Three-row navbar | The 1K theme stylesheet allowed the header, links and actions to wrap inside the original 1116px content container. Enlarged text and the new header switch increased width pressure. | Keep header groups on one row, retain the brand at left, and give the header a maximum 1600px content width. Crowded viewports use the existing menu through 1600px; full links appear above that breakpoint. Announcement strip and all destinations remain. |
| Missing hamburger panel at intermediate widths | App.css hid the panel/backdrop with `!important` above 1100px while theme-polish.css hid desktop links through 1400px. Present in 1K. | Align panel visibility and the hamburger with the 1600px navigation breakpoint; remove the conflicting important declaration. Existing close, Escape, animation and scrolling handlers remain. |
| Intrusive login notice | Disabled placeholder text was rendered in both navigation presentations before this restoration. | Remove the placeholder markup from both; retain Donate. No login route or authentication rule was enabled. Remove the obsolete first-action selector so Donate retains dark text on its gold background in both themes. |
| DIC registration heading | An earlier explicit green `strong` color survived beneath the later dark-green registration banner. Present in 1K and the pre-theme design. | Explicitly pair the banner heading with `--on-brand` white. Supporting text remains translucent white on `--brand-deep`. Registration availability and disabled-button rules remain untouched. |
| White footer text on a light surface | App.css intentionally restyled the original dark footer to a light surface; the later 1K theme stylesheet forced white foreground without changing that surface. | Remove the conflicting white override. Restore inherited `--ink` on `--surface`, retain themed gold headings and green Arabic/brand text. Scope the muted label to `--text-muted` instead of translucent white. All public routes share this footer. |
| Watchword panel Arabic | The theme conversion replaced the original pale-green text with the generic heading color on a dark-green panel. | Restore the original `#83bda2` from 604261e. |

The 16.5px root font, removed reading-size selector, compact accessible light/dark switch, saved theme, reduced motion and restored home hero green/gold remain intact. Shared appearance.js, theme.css and AppearanceControls.jsx needed no further changes in this restoration. Logo source and artwork were unchanged.

## Platform-wide source inspection

These are source/cascade findings, not rendered browser passes. All public routes use SiteChrome; Operations uses its separate shell.

| Page / local URL path | Scope inspected |
| --- | --- |
| `/` | Shared header/footer, green/gold hero, watchword panel, cards, dark bands and responsive rules |
| `/#who-we-are` (About) | Existing section target, heading/body surfaces and shared navigation; no separate About route was introduced |
| `/programs` | Public hero, catalog cards, filters, green CTA, mobile grid rules |
| `/events` | Public hero, event/annual cards, filters, responsive grid rules |
| `/projects` | Public hero, project cards, support panel, responsive grid rules |
| `/dic` | Hero, information card, registration banner, disabled registration controls, FAQ and shared footer |
| `/dic/participant` | Public shell, access panel, form/status colors, responsive participant cards and print suppression; no OTP/identity logic edited |
| `/media` | Hero, archive cards, dark media surfaces, filters and responsive rules |
| `/contact` | Hero, information cards, form surfaces, two-column/mobile rules |
| `/get-involved` | Dark hero and closing band, cards, community links and mobile rules |
| `/donate` | Hero, donation detail cards, contact CTA and responsive rules |
| `/faq` | Hero, category navigation, question/answer states and mobile rules |
| `/dic/operations` | Separate header/sidebar/login shell, themed cards/tables, overflow and responsive rules; existing service and permission tests pass |

No additional confirmed page-specific defects were established by this source review beyond those listed above. It does not establish absence of overflow, awkward wrapping or interaction defects in a browser.

## Validation

- Frontend tests: 15 passed, including theme persistence, blocked storage, tab sync, service permissions and participant access behavior.
- Extended existing contrast checks to white on dark green, footer surface pairs and dark text on bright gold; both palettes pass the checked WCAG AA token pairs. This is not a full rendered contrast audit.
- Frontend lint: passed.
- Frontend production build: passed.
- `git diff --check`: passed (existing LF/CRLF advisory only).
- `.vscode/settings.json` SHA-256 remains `77E594534D02F33D324DBF54097A13EE3F5E3028E6410B3FB119347C2B714E12`.
- No commit, push, deployment, new account, dependency, backend configuration or registration/payment change.

## Manual acceptance checklist

Frontend preview: http://127.0.0.1:5173/ (Vite started for this review). Use the established Django development backend at port 8000 for API-dependent pages. Vite proxies API requests there; backend availability was not revalidated in this CSS-only task.

Visit every URL in the table in both light and dark themes. Check at 1920x1080, 1601x900, 1600x900, 1440x900, 1024x768, 768x1024, 390x844 and 320x740; also check 200% browser zoom.

- [ ] Main header remains a compact single row: brand left, controls right; links appear only where they fit. Announcement strip remains above it.
- [ ] At widths through 1600px, open the hamburger. Every original destination plus Participant portal is reachable. Test link close, backdrop close and Escape focus return, especially 1100-1400px.
- [ ] Switch themes with mouse/touch and keyboard Space/Enter. Check sun/moon state, focus, reload persistence, route persistence and another tab.
- [ ] Homepage hero retains green/gold; watchword Arabic is readable; logo remains unchanged and loads externally.
- [ ] DIC registration banner heading/support copy are readable; registration stays closed and its register action unavailable.
- [ ] Footer description, headings, links, muted notice, Arabic and copyright are readable on its light/dark surface on every public route.
- [ ] Scroll every page normally. Check menu scrolling on short screens and horizontal overflow, overlapping controls, wrapping, card/button text and spacing.
- [ ] Check reduced motion and keyboard focus. Check Operations login/authorized shell using an existing authorized account; no account was created for this review.

Managed browser inventory was empty. The installed Chrome headless launch was rejected by execution policy. No browser screenshots, rendered viewport tests or live click-through checks were completed. Visual acceptance must remain pending until these checklist items are reviewed.

## Files changed in this restoration

- dawana-platform/src/App.css
- dawana-platform/src/theme-polish.css
- dawana-platform/src/components/layout/SiteChrome.jsx
- dawana-platform/src/services/appearance.test.js
- VISUAL_REGRESSION_RESTORATION.md
