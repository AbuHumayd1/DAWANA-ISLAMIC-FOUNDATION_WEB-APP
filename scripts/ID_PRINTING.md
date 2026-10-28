# Phase 3 — identification presentation and printing

Latest continuation: [DUAL_FORMAT_IDS.md](DUAL_FORMAT_IDS.md) documents PVC + A6,
no-write print rendering, the corrected Unicode labels and safe normal-preview
restoration. The current ID suite is 28 tests (70 combined); older counts below
describe the previous refinement. Use the latest runbook for the current workflow.

No new models, migrations, payment changes, housing-rule changes or checkpoint
functions are included. Existing uncommitted work is preserved. The previous card
template is also retained under ignored `.local-preview/identity-cards-before-refinement-*.html`.

## Validation evidence

The retained `20261024T085711Z-55def3.json` confirms **60/60 executed, zero failures,
errors, skipped or missing tests**, and migration parity through 0023 **before**
this presentation refinement. That includes the existing QR security tests.

The updated ID suite contains **22 tests** (18 existing + four print/branding tests).
The combined housing/ID suite contains 64. The replacement test now verifies the old
QR again after successfully verifying the replacement. Public/private response,
expiry, authorization, CSRF, rate-limit and no-business-state-change tests remain.
QR generation, token format, encryption, revocation and verification policy are unchanged.

This session: JavaScript and PowerShell syntax, path containment and whitespace
checks passed. The batch dimensions fit arithmetically: 177.2 × 234 mm inside
186 × 273 mm of A4 content. These are **not PDF measurements**. Python is denied
in the Codex tool process. Headless Chrome and Edge were attempted but both
terminated during GPU initialization. No successful browser render, camera scan or
print-to-PDF check is claimed for the changed design.

## Official logo — use the existing asset, not a substitute

The existing website header in `SiteChrome.jsx` references its logo on
`lh3.googleusercontent.com`; no local logo file was found. Direct retrieval failed
in the Codex environment. A favicon is not the official logo and is not substituted.

`scripts/cache-id-logo.ps1` downloads **that exact URL from the existing source**,
checks size and PNG/JPEG/WebP validity with Pillow, and retains its unmodified bytes
plus source/SHA-256 provenance at:

`backend/dic/static/dic/dawana-official-logo.img`

It preserves an existing asset and never overwrites it automatically. Card rendering
only reads the local file and embeds a data URI; it makes no remote logo request.
Downloaded HTML therefore needs no network for logo, QR, portrait or styles.

The actual logo has **not** been cached by Codex. Until the original is available,
the preview honestly shows “Logo unavailable” and a warning, rather than an invented
graphic. Final branded printing is pending this prerequisite. If the original URL
is no longer available in your own PowerShell, use an approved original local logo
at the above path; do not substitute another image. The logo loader validates its
format regardless of the `.img` extension. Keep source/provenance for review.

## One command — focused tests and isolated local preview

At the original Desktop repository root:

```powershell
.\scripts\complete-local-identification.ps1 -IdsOnly -IdDemo
```

This runs all 22 identification tests (including QR security), caches the existing
website logo, then starts the existing Django/React stack against a fresh isolated
synthetic demo database. If tests fail or the original logo cannot be obtained, it
stops before startup. No real registration records are manufactured or changed.
The synthetic Admin account is `local-id-demo`; choose its password privately in
the console. No credentials are printed or stored in manifest files.

Omit `-IdsOnly` to run all 64 focused housing/identification tests. Omit `-IdDemo`
to use the existing dawana_dev preview; its exact-target confirmation and backup
requirements remain. No additional migrations were created by this refinement.
Do not run duplicate preview servers. Stop only your existing preview processes
before restarting; the launcher refuses occupied ports and does not kill anything.

Tests alone, without preview startup, image download or application migrations:

```powershell
.\scripts\validate-dic-backend.ps1 -IdsOnly
```

The runner creates a new isolated test database, never changes `test_dawana_dev`,
and reports actual execution counts. Synthetic HTML fixtures are retained in the
run-specific directory reported as `synthetic_print_fixtures` in its JSON summary:

- Single card without a portrait and a one-card batch.
- Adult with an embedded synthetic test photograph.
- Long name with an assigned synthetic house.
- Seventeen copies for three-page layout testing; these copies do not manufacture
  extra registrations or identifiers. Existing batch tests also cover distinct IDs.

Fixtures are visibly marked SYNTHETIC. Their test tokens belong to the isolated
test database; use the running demo's real card links for live QR verification.
Unit tests use a plain synthetic image to verify logo embedding, not to claim that
image is an official logo. Cache the real logo before visual sign-off.

## Preview and print

- Directory: http://127.0.0.1:8000/admin/dic/campenrollment/
- ID history: http://127.0.0.1:8000/admin/dic/digitalidissue/
- Verification: http://127.0.0.1:8000/api/v1/dic/ids/verify/
- Frontend: http://127.0.0.1:5173/

The demo prints exact generated card URLs. **View / print** in the directory opens
one card at `/api/v1/dic/ids/cards/ENROLLMENT_UUID/`. Its `?download=1` variant
downloads self-contained HTML. `?layout=batch` uses a one-card A4 batch instead.

**Single-card printing:** one 85.6 × 54 mm card, centred horizontally and approximately
vertically on A4. A 1 mm page-height allowance avoids fractional print-engine rounding.
The card itself is never enlarged to fill the sheet.

**A4 batch:** use the directory's A4 batch action, up to 25 records. Each explicit
page group has at most eight standard cards, two per row, with 6 mm cutting gaps.
Counts 1/7/8/9/16/17/25 are covered by page-group tests. Last-page forced breaks are
disabled; cards are marked unbreakable. The batch screen remains a batch even with
one selected record. Both modes have **Download self-contained HTML**, also for
multi-page sheets, with the same embedded styles/images as the browser print view.

In Chrome or Edge choose **A4 portrait**, **100% scale**, and turn **Headers and
footers OFF**. Do not use Fit to page. The application cannot reliably change those
browser options. Save as PDF for a proof and measure the card outline before cutting.
Use actual printed output to confirm QR scanning. Retain a four-module quiet zone:
the unchanged SVG QR includes it, is black on white, and is displayed approximately
25.7 mm square without logos/text over it. No sensitive data is added to the payload.

The layout uses green/gold/cream, the actual cached logo, optional private portrait,
full name, participant number, actual/pending accommodation, active version and
validity. Long names switch to a wider text arrangement and are fitted without
ellipsis. Synthetic labels remain on the printed card. Small screens scale the
card proportions naturally; the document has no fixed-height shell or scroll lock.

Sign in as authorized staff before scanning for private details. Public verification
shows only validity and edition. Revoke/reissue in the existing controls, then
verify old → rejected, new → valid, old again → rejected. Verification does not
perform check-in, check-out, entry, exit, re-entry or movement authorization.

## Files

Modified: `backend/dic/templates/dic/identity_cards.html`, `identity_views.py`,
`identity_admin.py`, `test_identity_cards.py`; `scripts/validate_dic_backend.py`,
`complete-local-identification.ps1`.

Added: `backend/dic/identity_branding.py`, `scripts/cache-id-logo.ps1`, this runbook.
The official binary/provenance are added only when the original asset is cached.
No changes to identification database structure or the QR security implementation.
